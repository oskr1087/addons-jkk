from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tools.float_utils import float_compare


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    lot_distribution_id = fields.Many2one(
        "mrp.production.lot.distribution",
        string="Distribución de lotes",
        compute="_compute_lot_distribution_id",
        inverse="_inverse_lot_distribution_id",
        store=True,
        readonly=False,
        copy=False,
    )
    lot_distribution_line_ids = fields.One2many(
        related="lot_distribution_id.line_ids",
        string="Distribución de lotes",
        readonly=False,
    )
    lot_distribution_total_qty = fields.Float(
        related="lot_distribution_id.total_quantity",
        string="Cantidad distribuida",
        readonly=True,
    )
    lot_distribution_difference = fields.Float(
        related="lot_distribution_id.difference_quantity",
        string="Diferencia de distribución",
        readonly=True,
    )
    lot_distribution_valid = fields.Boolean(
        related="lot_distribution_id.is_valid",
        string="Distribución válida",
        readonly=True,
    )

    def _get_raw_consumption_targets(self):
        """Return the automatic raw consumption target for the current qty_producing.

        The target is rebuilt from the BoM through ``_get_moves_raw_values()`` so
        it does not depend on a previously altered ``product_uom_qty`` or
        ``unit_factor``.  Production below the planned quantity is scaled
        normally.  Production above the planned quantity is capped at 100% of
        the planned raw material demand.

        Only raw material moves of this manufacturing order are considered.
        Manual-consumption moves are intentionally excluded so Odoo can keep its
        standard warning/strict-consumption behaviour for genuinely manual
        consumption differences.
        """
        self.ensure_one()
        if not self.bom_id or not self.product_qty or self.qty_producing <= 0:
            return {}

        rounding = self.product_uom_id.rounding or 0.01
        effective_qty = self.qty_producing
        if float_compare(
            effective_qty,
            self.product_qty,
            precision_rounding=rounding,
        ) > 0:
            effective_qty = self.product_qty

        ratio = effective_qty / self.product_qty if self.product_qty else 0.0
        raw_values = self._get_moves_raw_values()

        # Prefer matching by BoM line.  Fallback to product when the value does
        # not expose bom_line_id (custom BoM/move implementations).
        by_bom_line = defaultdict(list)
        by_product = defaultdict(list)
        for vals in raw_values:
            bom_line_id = vals.get("bom_line_id")
            if bom_line_id:
                by_bom_line[bom_line_id].append(vals)
            by_product[vals.get("product_id")].append(vals)

        targets = {}
        used_value_ids = set()
        for move in self.move_raw_ids.filtered(
            lambda m: m.raw_material_production_id == self
            and m.state not in ("done", "cancel")
            and not m.manual_consumption
        ):
            candidates = []
            if move.bom_line_id:
                candidates = by_bom_line.get(move.bom_line_id.id, [])
            if not candidates:
                candidates = by_product.get(move.product_id.id, [])

            vals = next((v for v in candidates if id(v) not in used_value_ids), None)
            if not vals:
                continue
            used_value_ids.add(id(vals))

            vals_uom = self.env["uom.uom"].browse(vals["product_uom"])
            full_qty = vals_uom._compute_quantity(vals["product_uom_qty"], move.product_uom)
            targets[move.id] = move.product_uom.round(full_qty * ratio)

        return targets

    def _set_qty_producing(self, pick_manual_consumption_moves=True):
        """Keep Odoo's flow, then normalize automatic raw consumption once.

        * below/equal planned qty: proportional consumption, exactly once;
        * above planned qty: raw consumption capped at the planned quantity.

        We deliberately never rewrite ``product_uom_qty``.  This avoids
        corrupting the demand base used by backorders and later computations.
        The customization is restricted to ``move_raw_ids`` linked through
        ``raw_material_production_id``.
        """
        result = super()._set_qty_producing(
            pick_manual_consumption_moves=pick_manual_consumption_moves
        )

        for production in self:
            targets = production._get_raw_consumption_targets()
            if not targets:
                continue
            for move in production.move_raw_ids.filtered(
                lambda m: m.id in targets
                and m.raw_material_production_id == production
                and m.state not in ("done", "cancel")
            ):
                target = targets[move.id]
                if move.product_uom.compare(move.quantity, target) != 0:
                    move._set_quantity_done(target)
                if (not move.manual_consumption or pick_manual_consumption_moves) and target:
                    move.picked = True

        return result

    def _get_consumption_issues(self):
        """Evitar falsos avisos únicamente por sobreproducción.

        Odoo estándar calcula el esperado del wizard como BoM *
        qty_producing/product_qty. Para esta personalización, si se produce más
        que lo planificado, el esperado de materias primas se limita al 100% de
        la OF. Para cantidades menores o iguales se delega íntegramente a Odoo.
        """
        normal = self.filtered(
            lambda mo: mo.product_uom_id.compare(mo.qty_producing, mo.product_qty) <= 0
        )
        over = self - normal
        issues = super(MrpProduction, normal)._get_consumption_issues() if normal else []

        if self.env.context.get("skip_consumption", False):
            return issues

        for order in over:
            if order.consumption == "flexible" or not order.bom_id or not order.bom_id.bom_line_ids:
                continue

            expected_move_values = order._get_moves_raw_values()
            expected_qty_by_product = defaultdict(float)
            for move_values in expected_move_values:
                product = self.env["product.product"].browse(move_values["product_id"])
                uom = self.env["uom.uom"].browse(move_values["product_uom"])
                qty = uom._compute_quantity(move_values["product_uom_qty"], product.uom_id)
                # Sobreproducción: máximo 100% de la cantidad planificada.
                expected_qty_by_product[product] += qty

            done_qty_by_product = defaultdict(float)
            for move in order.move_raw_ids:
                quantity = move.product_uom._compute_quantity(
                    move._get_picked_quantity(), move.product_id.uom_id
                )
                if (
                    move.product_id not in expected_qty_by_product
                    and move.picked
                    and not move.product_id.uom_id.is_zero(quantity)
                ):
                    issues.append((order, move.product_id, quantity, 0.0))
                    continue
                done_qty_by_product[move.product_id] += quantity if move.picked else 0.0

            for product, expected_qty in expected_qty_by_product.items():
                consumed_qty = done_qty_by_product.get(product, 0.0)
                if product.uom_id.compare(expected_qty, consumed_qty) != 0:
                    issues.append((order, product, consumed_qty, expected_qty))

        return issues

    def _compute_lot_distribution_id(self):
        Distribution = self.env["mrp.production.lot.distribution"]
        for production in self:
            distribution = Distribution.search(
                [("production_id", "=", production.id)], limit=1
            )
            production.lot_distribution_id = distribution

    def _inverse_lot_distribution_id(self):
        # The distribution is owned by the production through its production_id.
        for production in self:
            if production.lot_distribution_id:
                production.lot_distribution_id.production_id = production.id

    @api.constrains("lot_producing_ids")
    def _check_lot_producing_ids(self):
        # Odoo standard restricts a lot-tracked MO to one lot. This module
        # intentionally removes that restriction and keeps the product/company
        # consistency checks.
        for production in self:
            if not production.lot_producing_ids:
                continue
            invalid_product_lots = production.lot_producing_ids.filtered(
                lambda lot: lot.product_id != production.product_id
            )
            if invalid_product_lots:
                raise ValidationError(
                    _("Todos los lotes de producción deben pertenecer al producto %s.")
                    % production.product_id.display_name
                )

    def _get_or_create_lot_distribution(self):
        self.ensure_one()
        distribution = self.lot_distribution_id
        if not distribution:
            distribution = self.env["mrp.production.lot.distribution"].create(
                {"production_id": self.id}
            )
            self.lot_distribution_id = distribution
        return distribution

    def _sync_lot_producing_ids_from_distribution(self):
        self.ensure_one()
        distribution = self.lot_distribution_id
        if not distribution:
            return
        lot_ids = distribution.line_ids.mapped("lot_id").ids
        self.with_context(skip_lot_distribution_sync=True).write(
            {"lot_producing_ids": [Command.set(lot_ids)]}
        )

    def _validate_lot_distribution_before_done(self):
        self.ensure_one()

        if self.product_tracking != "lot":
            return

        distribution = self.lot_distribution_id
        if not distribution or not distribution.line_ids:
            raise UserError(
                _(
                    "A lot distribution is required for this manufacturing order. "
                    "Add at least one lot and its quantity before marking the MO as done."
                )
            )

        distribution._validate_lines()

        rounding = self.product_uom_id.rounding or 0.01
        if float_compare(
            distribution.total_quantity,
            self.qty_producing,
            precision_rounding=rounding,
        ):
            raise UserError(
                _(
                    "The lot distribution must equal the quantity to produce. "
                    "Quantity to produce: %(produce)s. Distributed: %(distributed)s."
                )
                % {
                    "produce": self.qty_producing,
                    "distributed": distribution.total_quantity,
                }
            )

        self._sync_lot_producing_ids_from_distribution()

    def pre_button_mark_done(self):
        self._validate_lot_distributions_before_done()
        return super().pre_button_mark_done()

    def _validate_lot_distributions_before_done(self):
        for production in self:
            production._validate_lot_distribution_before_done()

    def action_generate_serial(self, workorder=False):
        if self.product_tracking == "lot":
            return {
                "type": "ir.actions.act_window",
                "name": _("Generar lotes"),
                "res_model": "mrp.production.lot.wizard",
                "view_mode": "form",
                "target": "new",
                "context": {
                    "default_production_id": self.id,
                    "default_workcenter_id": (
                        self.workorder_ids[:1].workcenter_id.id
                        if self.workorder_ids
                        else False
                    ),
                    "active_id": self.id,
                    "active_model": self._name,
                },
            }
        return super().action_generate_serial(workorder=workorder)

    def _prepare_finished_lot_move_line_vals(self, move, lot, quantity):
        self.ensure_one()
        return {
            "move_id": move.id,
            "picking_id": move.picking_id.id or False,
            "company_id": move.company_id.id,
            "product_id": move.product_id.id,
            "product_uom_id": move.product_uom.id,
            "location_id": move.location_id.id,
            "location_dest_id": move.location_dest_id.id,
            "lot_id": lot.id,
            "quantity": quantity,
            "picked": True,
        }

    def _apply_lot_distribution_to_finished_move(self, move, quantity):
        self.ensure_one()

        if self.product_tracking != "lot":
            return False

        distribution = self.lot_distribution_id
        if not distribution or not distribution.line_ids:
            return False

        rounding = self.product_uom_id.rounding or 0.01
        if float_compare(
            distribution.total_quantity,
            quantity,
            precision_rounding=rounding,
        ):
            raise UserError(
                _(
                    "The distribution for %s does not match the quantity being "
                    "posted. Expected %(expected)s, distributed %(distributed)s."
                )
                % {
                    "expected": quantity,
                    "distributed": distribution.total_quantity,
                }
            )

        # Keep the move itself at the total quantity, but create one operation
        # line per lot. This is what ultimately posts the separate lot quantities
        # into stock.
        move.quantity = quantity

        # Finished move lines created by a work order may exist before
        # _post_inventory. They are not done yet, so they can be replaced by
        # the explicit distribution lines.
        move.move_line_ids.filtered(lambda ml: ml.state != "done").unlink()

        vals_list = [
            self._prepare_finished_lot_move_line_vals(move, line.lot_id, line.quantity)
            for line in distribution.line_ids
        ]
        if vals_list:
            self.env["stock.move.line"].create(vals_list)

        # No asignar move.lot_ids aquí: en Odoo este campo puede regenerar
        # las líneas del movimiento y copiar la cantidad total a cada lote.
        return True

    def button_mark_done(self):
        """Validar distribución de lotes y dejar el consumo a la lógica central."""
        for order in self:
            if order.product_tracking != "lot":
                continue

            rounding = order.product_uom_id.rounding or 0.01
            distribution = order.lot_distribution_id
            if not distribution or not distribution.line_ids:
                raise UserError(
                    _(
                        "La orden de fabricación %(order)s no tiene lotes asignados. "
                        "Debe asignar al menos un lote antes de marcarla como hecha."
                    )
                    % {"order": order.display_name}
                )

            if float_compare(
                distribution.total_quantity,
                order.qty_producing,
                precision_rounding=rounding,
            ) != 0:
                raise UserError(
                    _(
                        "La distribución de lotes de %(order)s no coincide con la "
                        "cantidad producida. Cantidad producida: %(produced)s. "
                        "Cantidad distribuida: %(distributed)s."
                    )
                    % {
                        "order": order.display_name,
                        "produced": order.qty_producing,
                        "distributed": distribution.total_quantity,
                    }
                )

            distribution._validate_lines()
            order._sync_lot_producing_ids_from_distribution()

        return super().button_mark_done()

    def _post_inventory(self, cancel_backorder=False):
        # Raw-material processing remains 100% standard. We only replace the
        # finished-product lot/quantity preparation before stock.move._action_done().
        moves_to_do, moves_not_to_do, moves_to_cancel = set(), set(), set()

        for move in self.move_raw_ids:
            if move.state == "done":
                moves_not_to_do.add(move.id)
            elif not move.picked:
                moves_to_cancel.add(move.id)
            elif move.state != "cancel":
                moves_to_do.add(move.id)

        self.with_context(skip_mo_check=True).env["stock.move"].browse(
            moves_to_do
        )._action_done(cancel_backorder=cancel_backorder)
        self.with_context(skip_mo_check=True).env["stock.move"].browse(
            moves_to_cancel
        )._action_cancel()

        moves_to_do = self.move_raw_ids.filtered(
            lambda x: x.state == "done"
        ) - self.env["stock.move"].browse(moves_not_to_do)

        moves_to_do_by_order = defaultdict(
            lambda: self.env["stock.move"],
            [
                (key, self.env["stock.move"].concat(*values))
                for key, values in self._group_moves_by_raw_production(moves_to_do)
            ],
        )

        for order in self:
            finish_moves = order.move_finished_ids.filtered(
                lambda m: m.product_id == order.product_id
                and m.state not in ("done", "cancel")
            )
            for move in finish_moves:
                quantity = order.product_uom_id.round(
                    order.qty_producing - order.qty_produced,
                    rounding_method="HALF-UP",
                )

                if (
                    order.product_tracking == "lot"
                    and quantity
                    and order.lot_distribution_id
                    and order.lot_distribution_id.line_ids
                ):
                    order._apply_lot_distribution_to_finished_move(move, quantity)
                else:
                    if move.has_tracking != "none" and not move.lot_ids:
                        move.lot_ids = order.lot_producing_ids.ids
                    move.quantity = quantity

                extra_vals = order._prepare_finished_extra_vals()
                if extra_vals:
                    # The distribution already assigned the quantity of each
                    # finished move line. Do not let Odoo's standard helper
                    # overwrite those per-lot quantities with the total.
                    if order.product_tracking == "lot" and order.lot_distribution_id:
                        extra_vals = {
                            field: value
                            for field, value in extra_vals.items()
                            if field not in ("quantity", "qty_done")
                        }
                    if extra_vals:
                        move.move_line_ids.write(extra_vals)

            for workorder in order.workorder_ids:
                if workorder.state not in ("done", "cancel"):
                    workorder.duration_expected = workorder._get_duration_expected()
                if workorder.state == "cancel":
                    workorder.duration = 0.0
                elif workorder.duration == 0.0:
                    workorder.duration = workorder.duration_expected
                    workorder.duration_unit = round(
                        workorder.duration / max(workorder.qty_produced, 1), 2
                    )

            order._cal_price(moves_to_do_by_order[order.id])

        moves_to_finish = self.move_finished_ids.filtered(
            lambda x: x.state not in ("done", "cancel")
        )
        moves_to_finish.picked = True
        moves_to_finish = moves_to_finish._action_done(
            cancel_backorder=cancel_backorder
        )

        for order in self:
            consume_move_lines = moves_to_do_by_order[order.id].mapped("move_line_ids")
            order.move_finished_ids.move_line_ids.consume_line_ids = [
                (6, 0, consume_move_lines.ids)
            ]

        return True

    def _group_moves_by_raw_production(self, moves):
        grouped = defaultdict(list)
        for move in moves:
            grouped[move.raw_material_production_id.id].append(move)
        return grouped.items()

    def write(self, vals):
        res = super().write(vals)
        if (
            not self.env.context.get("skip_lot_distribution_sync")
            and "lot_producing_ids" in vals
        ):
            for production in self:
                if production.product_tracking != "lot":
                    continue
                distribution = production.lot_distribution_id
                if not distribution:
                    continue
                distribution.line_ids.filtered(
                    lambda line: line.lot_id.id not in production.lot_producing_ids.ids
                ).unlink()
        return res
