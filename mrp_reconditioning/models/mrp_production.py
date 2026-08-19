from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tools.float_utils import float_compare


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    is_reconditioning = fields.Boolean(
        string="Es reacondicionamiento", default=False, copy=False, index=True, tracking=True
    )
    reconditioning_reason_id = fields.Many2one(
        "mrp.reconditioning.reason", string="Motivo", tracking=True, ondelete="restrict"
    )
    original_production_id = fields.Many2one(
        "mrp.production",
        string="Orden de fabricación original",
        copy=False,
        tracking=True,
        check_company=True,
        domain="[('state', '=', 'done'), ('is_reconditioning', '=', False), ('product_id', '=', product_id)]",
    )
    original_lot_id = fields.Many2one(
        "stock.lot",
        string="Lote/Número de serie devuelto",
        copy=False,
        tracking=True,
        check_company=True,
        domain="[('product_id', '=', product_id)]",
    )
    returned_lot_ids = fields.Many2many(
        "stock.lot",
        string="Lotes/Números de serie devueltos",
        compute="_compute_return_information",
        compute_sudo=True,
    )
    selected_return_lot_ids = fields.Many2many(
        "stock.lot",
        "mrp_reconditioning_selected_lot_rel",
        "production_id",
        "lot_id",
        string="Lotes/Números de serie a reacondicionar",
        copy=False,
        tracking=True,
        check_company=True,
        domain="[('product_id', '=', product_id)]",
        help="Lotes o números de serie concretos de la devolución que serán reacondicionados en esta orden.",
    )
    returned_qty = fields.Float(
        string="Cantidad devuelta",
        compute="_compute_return_information",
        digits="Product Unit",
        compute_sudo=True,
    )
    selected_return_qty = fields.Float(
        string="Cantidad disponible para esta orden",
        compute="_compute_selected_return_qty",
        digits="Product Unit",
        compute_sudo=True,
    )
    return_picking_id = fields.Many2one(
        "stock.picking",
        string="Devolución de cliente",
        copy=False,
        tracking=True,
        check_company=True,
        domain="[('state', '=', 'done'), ('return_id', '!=', False), ('return_id.picking_type_id.code', '=', 'outgoing')]",
    )
    source_sale_order_id = fields.Many2one(
        "sale.order", string="Pedido de venta origen", copy=False, tracking=True, check_company=True
    )
    reconditioning_notes = fields.Text(string="Notas de reacondicionamiento")
    origin_trace_ids = fields.One2many(
        "mrp.reconditioning.trace", "reconditioning_id", string="Trazabilidad de origen", copy=False
    )
    reconditioning_result = fields.Selection(
        [
            ("pending", "Pendiente"),
            ("approved", "Reacondicionado / Aprobado"),
            ("rejected", "Rechazado"),
            ("scrap", "Desecho"),
            ("reprocess", "Requiere nuevo reproceso"),
        ],
        string="Resultado",
        default="pending",
        copy=False,
        tracking=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("is_reconditioning"):
                vals.setdefault("origin", _("Reacondicionamiento"))
                # En Odoo 19 qty_producing inicia normalmente en 0 hasta que el
                # usuario interactúa con el flujo de producción. Para un REAC
                # creado desde una devolución conocemos desde el inicio la
                # cantidad exacta que debe producirse, por lo que la dejamos
                # inicializada. mrp_multi_lot_distribution valida su
                # distribución precisamente contra este campo.
                if vals.get("product_qty") and not vals.get("qty_producing"):
                    vals["qty_producing"] = vals["product_qty"]
                if not vals.get("name") or vals.get("name") in (_("Nuevo"), _("New")):
                    vals["name"] = self.env["ir.sequence"].next_by_code("mrp.reconditioning") or _("Nuevo")

        productions = super().create(vals_list)

        # Compatibilidad explícita con mrp_multi_lot_distribution:
        # desde el mismo momento en que nace la REAC dejamos creada la
        # distribución que ese módulo utiliza como fuente de verdad para los
        # lotes terminados. No esperamos hasta ``button_mark_done``.
        for production in productions.filtered(
            lambda mo: mo.is_reconditioning
            and mo.return_picking_id
            and mo.product_tracking == "lot"
        ):
            production._sync_reconditioning_lot_distribution()

        return productions

    @api.depends(
        "return_picking_id",
        "return_picking_id.move_ids.state",
        "return_picking_id.move_ids.product_id",
        "return_picking_id.move_ids.move_line_ids.quantity",
        "return_picking_id.move_ids.move_line_ids.lot_id",
        "product_id",
        "product_uom_id",
    )
    def _compute_return_information(self):
        for production in self:
            production.returned_lot_ids = False
            production.returned_qty = 0.0
            if not production.return_picking_id or not production.product_id:
                continue
            return_moves = production.return_picking_id.move_ids.filtered(
                lambda move: move.state == "done" and move.product_id == production.product_id
            )
            move_lines = return_moves.move_line_ids.filtered(lambda line: line.quantity > 0)
            production.returned_lot_ids = move_lines.lot_id
            production.returned_qty = sum(
                line.product_uom_id._compute_quantity(line.quantity, production.product_uom_id)
                for line in move_lines
            )

    @api.depends(
        "return_picking_id",
        "selected_return_lot_ids",
        "returned_qty",
        "product_id",
        "product_uom_id",
        "return_picking_id.move_ids.move_line_ids.quantity",
    )
    def _compute_selected_return_qty(self):
        for production in self:
            production.selected_return_qty = production._get_reconditioning_return_qty()

    @api.constrains("is_reconditioning", "original_production_id", "product_id")
    def _check_reconditioning_origin_product(self):
        for production in self:
            if (
                production.is_reconditioning
                and production.original_production_id
                and production.product_id
                and production.original_production_id.product_id != production.product_id
            ):
                raise ValidationError(
                    _("La orden de fabricación original debe producir el mismo producto que se está reacondicionando.")
                )

    @api.constrains("original_lot_id", "product_id")
    def _check_original_lot_product(self):
        for production in self:
            if (
                production.original_lot_id
                and production.product_id
                and production.original_lot_id.product_id != production.product_id
            ):
                raise ValidationError(
                    _("El lote/número de serie devuelto debe pertenecer al producto que se está reacondicionando.")
                )

    @api.onchange("return_picking_id")
    def _onchange_return_picking_id(self):
        for production in self:
            picking = production.return_picking_id
            production.selected_return_lot_ids = False
            production.original_lot_id = False
            production.source_sale_order_id = False
            production.original_production_id = False
            if not picking:
                continue

            returned_products = picking.move_ids.filtered(
                lambda move: move.state == "done" and move.quantity > 0
            ).product_id
            if len(returned_products) == 1:
                production.product_id = returned_products

            original_picking = picking.return_id
            if original_picking and "sale_id" in original_picking._fields and original_picking.sale_id:
                production.source_sale_order_id = original_picking.sale_id

            production._compute_return_information()
            if len(production.returned_lot_ids) == 1:
                production.selected_return_lot_ids = production.returned_lot_ids
                production.original_lot_id = production.returned_lot_ids[:1]

            lots_for_origin = production.selected_return_lot_ids or production.returned_lot_ids
            if production.product_id and lots_for_origin:
                productions = self.env["mrp.production"].search(
                    [
                        ("id", "!=", production._origin.id or 0),
                        ("state", "=", "done"),
                        ("is_reconditioning", "=", False),
                        ("product_id", "=", production.product_id.id),
                        ("lot_producing_ids", "in", lots_for_origin.ids),
                    ],
                    limit=2,
                )
                if len(productions) == 1:
                    production.original_production_id = productions

    @api.onchange("original_production_id")
    def _onchange_original_production_id(self):
        for production in self:
            if production.original_production_id:
                production.product_id = production.original_production_id.product_id

    def _get_return_moves_for_product(self):
        self.ensure_one()
        if not self.return_picking_id or not self.product_id:
            return self.env["stock.move"]
        return self.return_picking_id.move_ids.filtered(
            lambda move: move.state == "done" and move.product_id == self.product_id
        )

    def _get_returned_product_component_moves(self):
        self.ensure_one()
        return self.move_raw_ids.filtered(lambda move: move.product_id == self.product_id)

    def _get_reconditioning_return_lots(self):
        self.ensure_one()
        return self.selected_return_lot_ids or self.returned_lot_ids

    def _get_reconditioning_return_qty(self):
        self.ensure_one()
        if not self.return_picking_id or not self.product_id or not self.product_uom_id:
            return 0.0
        if not self.selected_return_lot_ids:
            return self.returned_qty
        return sum(
            line.product_uom_id._compute_quantity(line.quantity, self.product_uom_id)
            for line in self._get_return_moves_for_product().move_line_ids.filtered(
                lambda line: line.quantity > 0 and line.lot_id in self.selected_return_lot_ids
            )
        )

    def _check_customer_return_required(self):
        """Valida que la orden esté respaldada por una devolución real y validada."""
        for production in self.filtered("is_reconditioning"):
            picking = production.return_picking_id
            if not picking:
                raise UserError(
                    _("Es obligatorio vincular una devolución de cliente antes de producir una orden de reacondicionamiento.")
                )
            if picking.state != "done":
                raise UserError(_("La devolución de cliente debe estar validada antes de reacondicionar."))
            if not picking.return_id:
                raise UserError(_("La transferencia seleccionada no es una devolución creada desde una entrega original."))
            if picking.return_id.picking_type_id.code != "outgoing" or picking.return_id.location_dest_id.usage != "customer":
                raise UserError(_("La devolución seleccionada debe originarse desde una entrega a cliente."))

            return_moves = production._get_return_moves_for_product()
            if not return_moves:
                raise UserError(_("La devolución seleccionada no contiene el producto que se desea reacondicionar."))
            if any(not move.origin_returned_move_id for move in return_moves):
                raise UserError(
                    _("El producto devuelto debe provenir de la entrega original al cliente y no de una recepción creada manualmente.")
                )

            production._compute_return_information()
            expected_lots = production._get_reconditioning_return_lots()
            if production.selected_return_lot_ids and not set(production.selected_return_lot_ids.ids).issubset(
                set(production.returned_lot_ids.ids)
            ):
                raise UserError(_("Los lotes/números de serie seleccionados deben pertenecer a la devolución vinculada."))

            available_qty = production._get_reconditioning_return_qty()
            rounding = production.product_uom_id.rounding
            if float_compare(production.product_qty, available_qty, precision_rounding=rounding) > 0:
                raise UserError(
                    _(
                        "No puede reacondicionar %(requested)s %(uom)s porque la devolución seleccionada solo contiene "
                        "%(returned)s %(uom)s de %(product)s disponibles para esta orden.",
                        requested=production.product_qty,
                        returned=available_qty,
                        uom=production.product_uom_id.display_name,
                        product=production.product_id.display_name,
                    )
                )

            if production.product_tracking in ("lot", "serial"):
                if not expected_lots:
                    raise UserError(
                        _("El producto devuelto tiene seguimiento, pero no se ha seleccionado un lote/número de serie de la devolución.")
                    )
                if production.product_tracking == "lot" and len(expected_lots) != 1:
                    raise UserError(
                        _("Una orden de reacondicionamiento de un producto con seguimiento por lote solo puede usar un lote devuelto. Cree una orden por cada lote.")
                    )
                if production.product_tracking == "serial" and float_compare(
                    production.product_qty, len(expected_lots), precision_rounding=rounding
                ) != 0:
                    raise UserError(
                        _("Para productos con número de serie, la cantidad a reacondicionar debe coincidir exactamente con los números de serie seleccionados.")
                    )
        return True

    def _apply_returned_lots(self):
        """Fuerza los lotes devueltos tanto en el componente como en el producto terminado."""
        for production in self.filtered("is_reconditioning"):
            production._check_customer_return_required()
            returned_lots = production._get_reconditioning_return_lots()

            if production.product_tracking in ("lot", "serial"):
                production.lot_producing_ids = [Command.set(returned_lots.ids)]
                production.original_lot_id = returned_lots[:1]

            component_moves = production._get_returned_product_component_moves()
            if not component_moves:
                raise UserError(
                    _("El producto devuelto debe existir como componente. Use «Agregar producto devuelto como componente» antes de confirmar.")
                )
            if len(component_moves) > 1:
                raise UserError(
                    _("Solo se permite una línea de componente para el producto terminado devuelto en cada orden de reacondicionamiento.")
                )

            component_move = component_moves[:1]
            if float_compare(
                component_move.product_uom_qty,
                production.product_qty,
                precision_rounding=production.product_uom_id.rounding,
            ) != 0:
                raise UserError(
                    _("La cantidad del producto devuelto como componente debe ser igual a la cantidad que se está reacondicionando.")
                )
            if production.product_tracking in ("lot", "serial"):
                component_move.lot_ids = [Command.set(returned_lots.ids)]

            production._sync_reconditioning_lot_distribution()
            production._sync_reconditioning_finished_product_lots(create_move_lines=False)
        return True

    def _prepare_reconditioning_qty_producing(self):
        """Prepara la cantidad real a producir antes de validar los lotes.

        Odoo 19 puede mantener ``qty_producing`` en 0.0 hasta que el usuario
        ejecuta una acción de producción. Sin embargo,
        ``mrp_multi_lot_distribution`` exige que la suma de la distribución
        sea exactamente igual a ese campo. En un reacondicionamiento la
        devolución ya determina la cantidad, así que sincronizamos
        ``qty_producing`` con la cantidad pendiente del REAC antes de cualquier
        validación de distribución.

        Después llamamos al método estándar/personalizado ``_set_qty_producing``
        para que los consumos de componentes queden coherentes con esa cantidad.
        Esta lógica se aplica exclusivamente a órdenes de reacondicionamiento.
        """
        for production in self.filtered("is_reconditioning"):
            if production.state in ("done", "cancel"):
                continue

            rounding = production.product_uom_id.rounding or 0.01
            remaining_qty = max(production.product_qty - production.qty_produced, 0.0)

            # Para un producto serializado cada REAC representa un único serial.
            if production.product_tracking == "serial" and production.selected_return_lot_ids:
                remaining_qty = float(len(production.selected_return_lot_ids))

            if float_compare(remaining_qty, 0.0, precision_rounding=rounding) <= 0:
                continue

            if float_compare(
                production.qty_producing,
                remaining_qty,
                precision_rounding=rounding,
            ) != 0:
                production.qty_producing = remaining_qty

            # En borrador basta con dejar preparado el valor. Una vez confirmada
            # la OF, _set_qty_producing sincroniza también movimientos/consumos.
            if production.state not in ("draft", "cancel", "done"):
                production._set_qty_producing()

        return True

    def _sync_reconditioning_lot_distribution(self):
        """Sincroniza la devolución con ``mrp_multi_lot_distribution``.

        El módulo de distribución de lotes considera
        ``mrp.production.lot.distribution`` como la fuente de verdad para un
        producto controlado por lote. Por ello, una REAC debe tener exactamente
        una línea de distribución con el lote devuelto y con la cantidad que se
        está produciendo.

        Esta rutina se ejecuta al crear la REAC, al confirmar, al iniciar y
        justo antes de finalizar. Así nunca dependemos únicamente de
        ``lot_producing_ids``.
        """
        Line = self.env["mrp.production.lot.distribution.line"]

        self.filtered("is_reconditioning")._prepare_reconditioning_qty_producing()

        for production in self.filtered("is_reconditioning"):
            if production.product_tracking != "lot":
                continue
            if production.state in ("done", "cancel"):
                continue

            production._check_customer_return_required()
            returned_lots = production._get_reconditioning_return_lots()
            if len(returned_lots) != 1:
                raise UserError(
                    _(
                        "El reacondicionamiento %(order)s debe tener exactamente un "
                        "lote devuelto. El módulo de distribución de lotes requiere "
                        "una distribución inequívoca antes de producir.",
                        order=production.display_name,
                    )
                )

            lot = returned_lots[:1]
            if lot.product_id != production.product_id:
                raise UserError(
                    _(
                        "El lote %(lot)s de la devolución no pertenece al producto "
                        "%(product)s.",
                        lot=lot.display_name,
                        product=production.product_id.display_name,
                    )
                )

            # mrp_multi_lot_distribution valida contra qty_producing al finalizar.
            # En borrador qty_producing puede todavía no estar inicializado, por
            # lo que usamos product_qty únicamente como respaldo.
            quantity = production.qty_producing or production.product_qty
            if float_compare(
                quantity,
                0.0,
                precision_rounding=production.product_uom_id.rounding or 0.01,
            ) <= 0:
                raise UserError(
                    _("La cantidad a distribuir en el lote devuelto debe ser mayor que cero.")
                )

            distribution = production._get_or_create_lot_distribution()

            # Para un reacondicionamiento por lote la distribución NO es libre.
            # Quitamos cualquier lote distinto y conservamos una única línea para
            # el lote recibido en la devolución.
            wrong_lines = distribution.line_ids.filtered(
                lambda line: line.lot_id != lot
            )
            if wrong_lines:
                wrong_lines.unlink()

            lot_lines = distribution.line_ids.filtered(lambda line: line.lot_id == lot)
            if len(lot_lines) > 1:
                # La restricción SQL normalmente lo evita, pero dejamos el flujo
                # defensivo para bases migradas o datos históricos.
                lot_lines[1:].unlink()
                lot_lines = lot_lines[:1]

            if lot_lines:
                line = lot_lines[:1]
                if production.product_uom_id.compare(line.quantity, quantity) != 0:
                    line.write({"quantity": quantity})
            else:
                Line.create(
                    {
                        "distribution_id": distribution.id,
                        "lot_id": lot.id,
                        "quantity": quantity,
                    }
                )

            # El propio módulo multi-lote sincroniza lot_producing_ids cuando se
            # crean/escriben líneas. Llamamos nuevamente al helper público para
            # dejar el estado consistente incluso si la línea ya existía.
            production._sync_lot_producing_ids_from_distribution()
            production.original_lot_id = lot

        return True

    def _validate_reconditioning_lot_distribution_compatibility(self):
        """Valida anticipadamente todas las reglas de mrp_multi_lot_distribution."""
        self.filtered("is_reconditioning")._prepare_reconditioning_qty_producing()

        for production in self.filtered("is_reconditioning"):
            if production.product_tracking != "lot":
                continue

            production._check_customer_return_required()
            production._sync_reconditioning_lot_distribution()

            distribution = production.lot_distribution_id
            expected_lots = production._get_reconditioning_return_lots()
            expected_lot = expected_lots[:1]

            if not distribution or not distribution.line_ids:
                raise UserError(
                    _(
                        "La orden %(order)s no tiene cargada la distribución de "
                        "lotes requerida. Debe existir el lote devuelto %(lot)s en "
                        "la pestaña Lotes.",
                        order=production.display_name,
                        lot=expected_lot.display_name,
                    )
                )

            # Reutilizamos la validación real del módulo dependiente: producto del
            # lote, duplicados, cantidad positiva y estado editable.
            distribution._validate_lines()

            if len(distribution.line_ids) != 1:
                raise UserError(
                    _(
                        "El reacondicionamiento %(order)s debe contener una sola "
                        "línea en la pestaña Lotes: %(lot)s.",
                        order=production.display_name,
                        lot=expected_lot.display_name,
                    )
                )

            line = distribution.line_ids[:1]
            if line.lot_id != expected_lot:
                raise UserError(
                    _(
                        "El lote de producción debe ser el mismo lote recibido en "
                        "la devolución. Esperado: %(expected)s. Actual: %(current)s.",
                        expected=expected_lot.display_name,
                        current=line.lot_id.display_name,
                    )
                )

            rounding = production.product_uom_id.rounding or 0.01
            if float_compare(
                distribution.total_quantity,
                production.qty_producing,
                precision_rounding=rounding,
            ) != 0:
                raise UserError(
                    _(
                        "La distribución del lote devuelto no coincide con la "
                        "cantidad a producir. A producir: %(produce)s. Distribuido: "
                        "%(distributed)s.",
                        produce=production.qty_producing,
                        distributed=distribution.total_quantity,
                    )
                )

            # Ejecuta exactamente la validación final del módulo multi-lote y
            # sincroniza lot_producing_ids desde su propia fuente de verdad.
            distribution.action_validate_distribution()

        return True

    def _sync_reconditioning_finished_product_lots(self, create_move_lines=False):
        """Sincroniza el lote devuelto con el movimiento del producto terminado.

        En Odoo 19 ``lot_producing_ids`` es la selección de lote/serie de la OF,
        pero algunas validaciones (incluidas personalizaciones de terceros) leen
        directamente ``move_finished_ids.lot_ids`` o sus ``move_line_ids``.
        Para reacondicionamientos mantenemos las tres capas alineadas.
        """
        for production in self.filtered("is_reconditioning"):
            production._check_customer_return_required()
            if production.product_tracking not in ("lot", "serial"):
                continue

            returned_lots = production._get_reconditioning_return_lots()
            if not returned_lots:
                raise UserError(_("No existen lotes/números de serie devueltos para asignar al producto terminado."))

            production.lot_producing_ids = [Command.set(returned_lots.ids)]
            production.original_lot_id = returned_lots[:1]

            finished_moves = production.move_finished_ids.filtered(
                lambda move: move.product_id == production.product_id and move.state not in ("done", "cancel")
            )
            if not finished_moves:
                continue

            for move in finished_moves:
                move.lot_ids = [Command.set(returned_lots.ids)]

                # Antes de cerrar la OF dejamos también preparada la línea real
                # del producto terminado. Esto evita que validaciones previas a
                # ``_post_inventory`` interpreten que la OF no tiene lote.
                if not create_move_lines:
                    continue

                qty_to_produce = max(production.product_qty - production.qty_produced, 0.0)
                if production.qty_producing:
                    qty_to_produce = production.qty_producing

                if production.product_tracking == "lot":
                    lot = returned_lots[:1]
                    lot_lines = move.move_line_ids.filtered(lambda line: line.lot_id == lot)
                    empty_lines = move.move_line_ids.filtered(lambda line: not line.lot_id)
                    if empty_lines:
                        empty_lines.write({"lot_id": lot.id})
                        lot_lines |= empty_lines
                    if lot_lines:
                        # La cantidad terminada se registra en una sola línea de lote.
                        first_line = lot_lines[:1]
                        first_line.quantity = qty_to_produce
                        (lot_lines - first_line).quantity = 0.0
                    else:
                        self.env["stock.move.line"].create({
                            "move_id": move.id,
                            "product_id": production.product_id.id,
                            "product_uom_id": move.product_uom.id,
                            "quantity": qty_to_produce,
                            "lot_id": lot.id,
                            "location_id": move.location_id.id,
                            "location_dest_id": move.location_dest_id.id,
                            "company_id": production.company_id.id,
                        })
                else:
                    # Cada REAC de producto serializado se crea por un único
                    # número de serie, por lo que la cantidad esperada es 1.
                    lot = returned_lots[:1]
                    serial_lines = move.move_line_ids.filtered(lambda line: line.lot_id == lot)
                    empty_lines = move.move_line_ids.filtered(lambda line: not line.lot_id)
                    if empty_lines:
                        first_empty = empty_lines[:1]
                        first_empty.write({"lot_id": lot.id, "quantity": 1.0})
                        (empty_lines - first_empty).quantity = 0.0
                    elif serial_lines:
                        serial_lines[:1].quantity = 1.0
                    else:
                        self.env["stock.move.line"].create({
                            "move_id": move.id,
                            "product_id": production.product_id.id,
                            "product_uom_id": move.product_uom.id,
                            "quantity": 1.0,
                            "lot_id": lot.id,
                            "location_id": move.location_id.id,
                            "location_dest_id": move.location_dest_id.id,
                            "company_id": production.company_id.id,
                        })
        return True

    def _check_consumed_returned_lots(self):
        """Último control: lo consumido y lo producido deben conservar los lotes de la devolución."""
        for production in self.filtered("is_reconditioning"):
            production._check_customer_return_required()
            component_moves = production._get_returned_product_component_moves()
            if len(component_moves) != 1:
                raise UserError(_("El producto terminado devuelto debe existir exactamente en una línea de componente."))

            if production.product_tracking not in ("lot", "serial"):
                continue

            consumed_lines = component_moves.move_line_ids.filtered(lambda line: line.quantity > 0)
            consumed_lots = consumed_lines.lot_id
            expected_lots = production._get_reconditioning_return_lots()
            if not consumed_lines or set(consumed_lots.ids) != set(expected_lots.ids):
                raise UserError(
                    _(
                        "El producto devuelto debe consumirse utilizando exactamente los mismos lotes/números de serie de la devolución: %(lots)s.",
                        lots=", ".join(expected_lots.mapped("name")),
                    )
                )

            if set(production.lot_producing_ids.ids) != set(expected_lots.ids):
                raise UserError(
                    _(
                        "El producto terminado reacondicionado debe conservar exactamente los lotes/números de serie devueltos: %(lots)s.",
                        lots=", ".join(expected_lots.mapped("name")),
                    )
                )
        return True

    def action_confirm(self):
        reconditionings = self.filtered("is_reconditioning")
        reconditionings._check_customer_return_required()
        reconditionings._prepare_reconditioning_qty_producing()
        reconditionings._apply_returned_lots()
        result = super().action_confirm()
        # Odoo puede recalcular qty_producing durante la confirmación. Lo
        # restablecemos después del super y luego regeneramos la distribución
        # para que ambos módulos trabajen con la misma cantidad.
        reconditionings._prepare_reconditioning_qty_producing()
        reconditionings._apply_returned_lots()
        reconditionings._sync_reconditioning_lot_distribution()
        reconditionings.action_assign()
        return result

    def action_start(self):
        reconditionings = self.filtered("is_reconditioning")
        reconditionings._check_customer_return_required()
        reconditionings._prepare_reconditioning_qty_producing()
        reconditionings._apply_returned_lots()
        result = super().action_start()
        reconditionings._prepare_reconditioning_qty_producing()
        reconditionings._sync_reconditioning_lot_distribution()
        return result

    def button_mark_done(self):
        reconditionings = self.filtered("is_reconditioning")
        reconditionings._check_customer_return_required()
        # Debe ejecutarse ANTES de validar mrp_multi_lot_distribution. De otro
        # modo la distribución puede ser 1.0 mientras Odoo todavía conserva
        # qty_producing = 0.0 y la validación bloquearía correctamente el cierre.
        reconditionings._prepare_reconditioning_qty_producing()
        reconditionings._apply_returned_lots()
        reconditionings._sync_reconditioning_lot_distribution()
        reconditionings._validate_reconditioning_lot_distribution_compatibility()

        # Para productos por lote NO fabricamos manualmente líneas terminadas:
        # mrp_multi_lot_distribution las elimina y vuelve a crear en
        # _apply_lot_distribution_to_finished_move() usando la distribución.
        # Para seriales (que ese módulo no gestiona) mantenemos nuestra lógica.
        reconditionings.filtered(
            lambda mo: mo.product_tracking == "serial"
        )._sync_reconditioning_finished_product_lots(create_move_lines=True)

        reconditionings._check_consumed_returned_lots()
        return super().button_mark_done()

    def action_load_origin_traceability(self):
        for production in self.filtered("is_reconditioning"):
            if not production.original_production_id:
                raise UserError(_("Seleccione primero la orden de fabricación original."))

            commands = [Command.clear()]
            for move in production.original_production_id.move_raw_ids.filtered(lambda m: m.state == "done"):
                move_lines = move.move_line_ids.filtered(lambda ml: ml.quantity)
                if move_lines:
                    for line in move_lines:
                        commands.append(
                            Command.create(
                                {
                                    "source_production_id": production.original_production_id.id,
                                    "product_id": line.product_id.id,
                                    "lot_id": line.lot_id.id,
                                    "quantity": line.quantity,
                                    "product_uom_id": line.product_uom_id.id,
                                    "state": "inherited",
                                }
                            )
                        )
                else:
                    commands.append(
                        Command.create(
                            {
                                "source_production_id": production.original_production_id.id,
                                "product_id": move.product_id.id,
                                "quantity": move.quantity,
                                "product_uom_id": move.product_uom.id,
                                "state": "inherited",
                            }
                        )
                    )
            production.origin_trace_ids = commands
        return True

    def action_add_returned_product_component(self):
        self.ensure_one()
        if not self.is_reconditioning:
            raise UserError(_("Esta acción solo está disponible para órdenes de reacondicionamiento."))

        self._check_customer_return_required()

        # Método idempotente: puede ser llamado desde la devolución incluso si
        # otra personalización/MRP confirmó la OF durante create(). Si el
        # componente ya existe, únicamente resincronizamos lote y distribución.
        existing_moves = self._get_returned_product_component_moves()
        if existing_moves:
            self._apply_returned_lots()
            self._sync_reconditioning_lot_distribution()
            return True

        # Las órdenes creadas desde una devolución reciben este componente
        # dentro de move_raw_ids en el mismo create(). Si por una integración
        # externa se llega aquí sin componente y la OF ya está confirmada,
        # bloqueamos para no alterar a posteriori la estructura de una OF activa.
        if self.state != "draft":
            raise UserError(
                _(
                    "La orden fue confirmada sin el producto devuelto como componente. "
                    "Este reacondicionamiento debe crearse nuevamente desde la devolución."
                )
            )

        returned_lots = self._get_reconditioning_return_lots()
        move = self.env["stock.move"].create(
            {
                "description_picking": _("Producto devuelto para reacondicionamiento - %s") % self.product_id.display_name,
                "product_id": self.product_id.id,
                "product_uom_qty": self.product_qty,
                "product_uom": self.product_uom_id.id,
                "raw_material_production_id": self.id,
                "location_id": self.location_src_id.id,
                "location_dest_id": self.product_id.with_company(self.company_id).property_stock_production.id,
                "company_id": self.company_id.id,
            }
        )
        if self.product_tracking in ("lot", "serial"):
            move.lot_ids = [Command.set(returned_lots.ids)]
            self.lot_producing_ids = [Command.set(returned_lots.ids)]
            self.original_lot_id = returned_lots[:1]
            self._sync_reconditioning_lot_distribution()
            self._sync_reconditioning_finished_product_lots(create_move_lines=False)
        return True

    def action_mark_origin_component_replaced(self):
        self.ensure_one()
        inherited = self.origin_trace_ids.filtered(lambda line: line.state == "inherited")
        if not inherited:
            raise UserError(_("No existen líneas de trazabilidad heredadas para actualizar."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Trazabilidad de origen"),
            "res_model": "mrp.reconditioning.trace",
            "view_mode": "list,form",
            "domain": [("reconditioning_id", "=", self.id)],
            "context": {"default_reconditioning_id": self.id},
        }
