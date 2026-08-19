from collections import defaultdict

from odoo import api, fields, models, _
from odoo.fields import Command
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    is_customer_return_for_reconditioning = fields.Boolean(
        string="Es devolución de cliente",
        compute="_compute_reconditioning_info",
    )
    reconditioning_ids = fields.One2many(
        "mrp.production",
        "return_picking_id",
        string="Reacondicionamientos",
    )
    reconditioning_count = fields.Integer(
        string="Reacondicionamientos",
        compute="_compute_reconditioning_info",
    )

    @api.depends("state", "return_id", "return_id.picking_type_id.code", "return_id.location_dest_id.usage", "reconditioning_ids")
    def _compute_reconditioning_info(self):
        for picking in self:
            picking.is_customer_return_for_reconditioning = bool(
                picking.state == "done"
                and picking.return_id
                and picking.return_id.picking_type_id.code == "outgoing"
                and picking.return_id.location_dest_id.usage == "customer"
            )
            picking.reconditioning_count = len(
                picking.reconditioning_ids.filtered("is_reconditioning")
            )

    def _check_valid_customer_return_for_reconditioning(self):
        self.ensure_one()
        if self.state != "done":
            raise UserError(_("La devolución debe estar validada antes de crear un reacondicionamiento."))
        if not self.return_id:
            raise UserError(_("Esta transferencia no corresponde a una devolución de cliente."))
        if self.return_id.picking_type_id.code != "outgoing" or self.return_id.location_dest_id.usage != "customer":
            raise UserError(_("El reacondicionamiento solo puede originarse desde una devolución de una entrega a cliente."))

        return_moves = self.move_ids.filtered(
            lambda move: move.state == "done" and move.quantity > 0
        )
        if not return_moves:
            raise UserError(_("La devolución no contiene productos con cantidades devueltas."))
        if any(not move.origin_returned_move_id for move in return_moves):
            raise UserError(_("Todos los productos a reacondicionar deben provenir de los movimientos originales de la entrega al cliente."))
        return True

    def _find_original_production(self, product, lots):
        domain = [
            ("state", "=", "done"),
            ("is_reconditioning", "=", False),
            ("product_id", "=", product.id),
        ]
        if lots:
            domain.append(("lot_producing_ids", "in", lots.ids))
        productions = self.env["mrp.production"].search(domain, order="date_finished desc, id desc", limit=2)
        return productions[:1] if len(productions) == 1 else self.env["mrp.production"]

    def _prepare_reconditioning_groups(self):
        """Agrupa la devolución para crear una REAC por producto/lote cuando aplique."""
        self.ensure_one()
        groups = defaultdict(lambda: {"quantity": 0.0, "lots": self.env["stock.lot"]})

        for move in self.move_ids.filtered(lambda m: m.state == "done" and m.quantity > 0):
            product = move.product_id
            lines = move.move_line_ids.filtered(lambda line: line.quantity > 0)

            if product.tracking in ("lot", "serial"):
                for line in lines:
                    if not line.lot_id:
                        raise UserError(
                            _("El producto %(product)s tiene seguimiento, pero la devolución contiene una línea sin lote/número de serie.", product=product.display_name)
                        )
                    key = (product.id, line.lot_id.id)
                    qty = line.product_uom_id._compute_quantity(line.quantity, product.uom_id)
                    groups[key]["quantity"] += qty
                    groups[key]["lots"] |= line.lot_id
            else:
                key = (product.id, False)
                qty = move.product_uom._compute_quantity(move.quantity, product.uom_id)
                groups[key]["quantity"] += qty

        return groups

    def action_create_reconditioning(self):
        self.ensure_one()
        self._check_valid_customer_return_for_reconditioning()

        groups = self._prepare_reconditioning_groups()
        if not groups:
            raise UserError(_("No se encontraron productos válidos para reacondicionar."))

        original_picking = self.return_id
        sale_order = original_picking.sale_id if "sale_id" in original_picking._fields else False
        created = self.env["mrp.production"]

        for (product_id, _lot_id), values in groups.items():
            product = self.env["product.product"].browse(product_id)
            lots = values["lots"]
            quantity = values["quantity"]

            if product.tracking == "serial" and quantity != 1.0:
                # Cada número de serie se procesa en una orden independiente.
                quantity = 1.0

            existing_domain = [
                ("is_reconditioning", "=", True),
                ("return_picking_id", "=", self.id),
                ("product_id", "=", product.id),
                ("state", "!=", "cancel"),
            ]
            existing = self.env["mrp.production"].search(existing_domain)
            if lots:
                existing = existing.filtered(
                    lambda production: set(production.selected_return_lot_ids.ids) == set(lots.ids)
                )
            else:
                existing = existing.filtered(lambda production: not production.selected_return_lot_ids)
            if existing:
                raise UserError(
                    _(
                        "Ya existe el reacondicionamiento %(reac)s para %(product)s%(lot)s vinculado a esta devolución.",
                        reac=existing[0].display_name,
                        product=product.display_name,
                        lot=_(" / Lote: %s") % ", ".join(lots.mapped("name")) if lots else "",
                    )
                )

            original_production = self._find_original_production(product, lots)
            production_location = product.with_company(self.company_id).property_stock_production
            returned_component_vals = {
                "description_picking": _(
                    "Producto devuelto para reacondicionamiento - %s"
                ) % product.display_name,
                "product_id": product.id,
                "product_uom_qty": quantity,
                "product_uom": product.uom_id.id,
                "location_id": self.location_dest_id.id,
                "location_dest_id": production_location.id,
                "company_id": self.company_id.id,
            }
            if product.tracking in ("lot", "serial") and lots:
                returned_component_vals["lot_ids"] = [Command.set(lots.ids)]

            vals = {
                "is_reconditioning": True,
                "product_id": product.id,
                "product_qty": quantity,
                "qty_producing": quantity,
                "product_uom_id": product.uom_id.id,
                "return_picking_id": self.id,
                "location_src_id": self.location_dest_id.id,
                "source_sale_order_id": sale_order.id if sale_order else False,
                "original_production_id": original_production.id if original_production else False,
                "selected_return_lot_ids": [Command.set(lots.ids)],
                "original_lot_id": lots[:1].id if lots else False,
                "origin": _("Reacondicionamiento desde %(devolucion)s", devolucion=self.name),
                # El producto devuelto debe nacer como componente junto con la
                # OF. Algunas personalizaciones confirman mrp.production dentro
                # de create(); si esperáramos al retorno de create(), sería tarde.
                "move_raw_ids": [Command.create(returned_component_vals)],
            }
            if product.tracking in ("lot", "serial") and lots:
                vals["lot_producing_ids"] = [Command.set(lots.ids)]

            production = self.env["mrp.production"].create(vals)
            # En algunas bases otras extensiones MRP pueden confirmar la orden
            # durante create(). Este método es idempotente: reutiliza el
            # componente si ya fue creado y solo lo crea cuando sigue en borrador.
            production.action_add_returned_product_component()
            production._prepare_reconditioning_qty_producing()
            production._apply_returned_lots()
            # La pestaña Lotes de mrp_multi_lot_distribution debe quedar
            # preparada desde la creación, no solamente al finalizar.
            production._sync_reconditioning_lot_distribution()
            if original_production:
                production.action_load_origin_traceability()
            created |= production

        action = self.env.ref("mrp_reconditioning.action_mrp_reconditioning").read()[0]
        if len(created) == 1:
            action.update({
                "view_mode": "form",
                "res_id": created.id,
                "views": [(self.env.ref("mrp.mrp_production_form_view").id, "form")],
            })
        else:
            action["domain"] = [("id", "in", created.ids)]
        return action

    def action_view_reconditionings(self):
        self.ensure_one()
        action = self.env.ref("mrp_reconditioning.action_mrp_reconditioning").read()[0]
        records = self.reconditioning_ids.filtered("is_reconditioning")
        if len(records) == 1:
            action.update({
                "view_mode": "form",
                "res_id": records.id,
                "views": [(self.env.ref("mrp.mrp_production_form_view").id, "form")],
            })
        else:
            action["domain"] = [("id", "in", records.ids)]
        return action
