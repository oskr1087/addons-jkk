# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import ValidationError


class StockInventory(models.Model):
    _name = 'setu.stock.inventory'
    _description = 'Setu Stock Inventory'

    name = fields.Char(string="Nombre")

    date = fields.Date(string="Fecha de inventario")

    state = fields.Selection(string='Status', selection=[
        ('draft', 'Borrador'), ('cancel', 'Cancelado'),
        ('confirm', 'En progreso'), ('done', 'Validado')], copy=False, index=True, readonly=True, default='draft')

    inventory_count_id = fields.Many2one(comodel_name="setu.stock.inventory.count", string="Inventory Count")
    location_id = fields.Many2one(comodel_name="stock.location", required=True, string="Ubicación")
    partner_id = fields.Many2one(comodel_name="res.users",
                                 string="Propietario inventariado", readonly=True,
                                 help="Especifique un propietario para limitar el inventario a dicho propietario.")
    company_id = fields.Many2one(comodel_name="res.company", string="Compañía",
                                 readonly=True, index=True, required=True, default=lambda self: self.env.company)

    line_ids = fields.One2many('setu.stock.inventory.line', 'inventory_id', string='Inventarios', copy=True,
                               readonly=False)
    move_ids = fields.One2many('stock.move', 'inventory_adj_id', readonly=True, string="Moves")
    account_move_ids = fields.Many2many(
        comodel_name="account.move",
        compute="_compute_account_move_ids",
        string="Asientos contables",
        readonly=True,
    )
    account_move_count = fields.Integer(
        compute="_compute_account_move_ids",
        string="Asientos contables",
    )

    product_ids = fields.Many2many('product.product', string='Productos', check_company=True,
                                   domain="[('type', '=', 'product'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
                                   readonly=True,
                                   help="Especifique productos para limitar el inventario a esos productos.")

    def _compute_account_move_ids(self):
        """Obtiene los asientos creados por Odoo 19 para los movimientos del ajuste.

        En Odoo 19 la trazabilidad estándar es directa:
        ``stock.move.account_move_id``. Ya no dependemos de
        ``stock.valuation.layer``.
        """
        AccountMove = (
            self.env["account.move"]
            if "account.move" in self.env.registry.models
            else False
        )

        for inventory in self:
            if not AccountMove:
                inventory.account_move_ids = False
                inventory.account_move_count = 0
                continue

            moves = inventory.move_ids.exists()
            account_moves = AccountMove.browse()

            if moves and "account_move_id" in moves._fields:
                account_moves |= moves.mapped("account_move_id")

            if moves and "account_move_ids" in moves._fields:
                account_moves |= moves.mapped("account_move_ids")

            account_moves = account_moves.exists()
            inventory.account_move_ids = account_moves
            inventory.account_move_count = len(account_moves)

    def action_open_account_moves(self):
        self.ensure_one()
        account_moves = self.account_move_ids.exists()

        if not account_moves:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Sin asiento contable"),
                    "message": _(
                        "Este ajuste no tiene asientos contables asociados. "
                        "Revise que los productos tengan valoración automática y "
                        "configuración contable válida."
                    ),
                    "type": "warning",
                    "sticky": False,
                },
            }

        if len(account_moves) == 1:
            return {
                "type": "ir.actions.act_window",
                "name": _("Asiento contable"),
                "res_model": "account.move",
                "view_mode": "form",
                "res_id": account_moves.id,
                "target": "current",
            }

        return {
            "type": "ir.actions.act_window",
            "name": _("Asientos contables"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", account_moves.ids)],
            "target": "current",
        }

    def action_cancel(self):
        if self.inventory_count_id:
            try:
                self.inventory_count_id.message_post(
                    body=f"""This count is cancelled. Please start new Inventory if you want to adjust it"""
                )
            except Exception as e:
                pass
            self.inventory_count_id = False
        self.state = 'cancel'

    def _check_odoo19_inventory_adjustment_accounting(self):
        """Valida la configuración necesaria para contabilizar ajustes en Odoo 19.

        Para valoración perpetua, ``stock.move._should_create_account_move``
        requiere que la ubicación externa (Inventory Loss) tenga
        ``valuation_account_id``.
        """
        for inventory in self:
            realtime_lines = inventory.line_ids.filtered(
                lambda line: (
                    line.product_id.is_storable
                    and getattr(line.product_id, "valuation", False) == "real_time"
                    and line.product_qty != line.theoretical_qty
                )
            )
            if not realtime_lines:
                continue

            adjustment_locations = self.env["stock.location"]
            for line in realtime_lines:
                # Faltante: interno -> Inventory adjustment.
                # Sobrante: Inventory adjustment -> interno.
                inventory_location = line.product_id.with_company(
                    inventory.company_id
                ).property_stock_inventory
                if inventory_location:
                    adjustment_locations |= inventory_location

            missing_account_locations = adjustment_locations.filtered(
                lambda location: not location.valuation_account_id
            )
            if missing_account_locations:
                raise ValidationError(
                    _(
                        "No se puede validar el ajuste porque la(s) ubicación(es) "
                        "de pérdida de inventario %(locations)s no tienen una "
                        "Cuenta de valoración configurada.\n\n"
                        "En Odoo 19, para generar el asiento de un ajuste de "
                        "inventario con valoración perpetua, configure la cuenta "
                        "en Inventario > Configuración > Ubicaciones > "
                        "Inventory adjustment / Ajuste de inventario > "
                        "Cuenta de valoración de existencias."
                    ) % {
                        "locations": ", ".join(
                            missing_account_locations.mapped("display_name")
                        )
                    }
                )

        return True

    def action_validate(self):
        """Aplica físicamente el ajuste y deja que Odoo genere valoración/contabilidad.

        La opción ``auto_inventory_adjustment`` no controla si se aplica o no el
        inventario. Controla únicamente si esta validación se ejecuta de forma
        automática al crear el ajuste desde el conteo.
        """
        self._check_odoo19_inventory_adjustment_accounting()

        for inventory in self:
            if inventory.state != 'confirm':
                continue

            quants_to_apply = self.env['stock.quant']

            for line in inventory.line_ids:
                quant = False

                if line.product_id.tracking == 'serial':
                    # Series encontradas / agregadas.
                    for sr_num in line.serial_number_ids:
                        quant = self.env['stock.quant'].sudo().search([
                            ('location_id', '=', line.location_id.id),
                            ('lot_id', '=', sr_num.id),
                            ('product_id', '=', line.product_id.id),
                            ('quantity', '>', 0),
                        ], limit=1)

                        if quant:
                            if line.product_qty == 0:
                                quant.with_context(inventory_mode=True).write({
                                    'inventory_quantity': 0,
                                })
                                quants_to_apply |= quant
                            continue

                        # Si la serie existe físicamente en otra ubicación interna,
                        # primero se elimina de allí y luego se incorpora aquí.
                        other_quant = self.env['stock.quant'].sudo().search([
                            ('lot_id', '=', sr_num.id),
                            ('product_id', '=', line.product_id.id),
                            ('location_id.usage', '=', 'internal'),
                            ('quantity', '>', 0),
                        ], limit=1)

                        if other_quant:
                            other_quant.with_context(inventory_mode=True).write({
                                'inventory_quantity': 0,
                            })
                            quants_to_apply |= other_quant

                        quant = self.env['stock.quant'].with_context(
                            inventory_mode=True
                        ).sudo().create({
                            'product_id': line.product_id.id,
                            'location_id': line.location_id.id,
                            'lot_id': sr_num.id,
                            'inventory_quantity': 1,
                        })
                        quants_to_apply |= quant

                    # Series esperadas pero no encontradas.
                    for sr_num in line.not_found_serial_number_ids:
                        missing_quant = self.env['stock.quant'].sudo().search([
                            ('location_id', '=', line.location_id.id),
                            ('lot_id', '=', sr_num.id),
                            ('product_id', '=', line.product_id.id),
                            ('quantity', '>', 0),
                        ], limit=1)
                        if missing_quant:
                            missing_quant.with_context(inventory_mode=True).write({
                                'inventory_quantity': 0,
                            })
                            quants_to_apply |= missing_quant

                elif line.product_id.tracking == 'lot':
                    quant = self.env['stock.quant'].sudo().search([
                        ('lot_id', '=', line.prod_lot_id.id),
                        ('location_id', '=', line.location_id.id),
                        ('product_id', '=', line.product_id.id),
                    ], limit=1)

                    if quant:
                        quant.with_context(inventory_mode=True).write({
                            'inventory_quantity': line.product_qty,
                        })
                    else:
                        quant = self.env['stock.quant'].with_context(
                            inventory_mode=True
                        ).sudo().create({
                            'product_id': line.product_id.id,
                            'location_id': line.location_id.id,
                            'lot_id': line.prod_lot_id.id,
                            'inventory_quantity': line.product_qty,
                        })

                    line.quant_id = quant
                    quants_to_apply |= quant

                else:
                    quant = self.env['stock.quant'].sudo().search([
                        ('location_id', '=', line.location_id.id),
                        ('product_id', '=', line.product_id.id),
                        ('lot_id', '=', False),
                    ], limit=1)

                    if quant:
                        quant.with_context(inventory_mode=True).write({
                            'inventory_quantity': line.product_qty,
                        })
                    else:
                        quant = self.env['stock.quant'].with_context(
                            inventory_mode=True
                        ).sudo().create({
                            'product_id': line.product_id.id,
                            'location_id': line.location_id.id,
                            'inventory_quantity': line.product_qty,
                        })

                    line.quant_id = quant
                    quants_to_apply |= quant

            # Este es el paso que faltaba cuando la configuración automática
            # estaba desactivada. Aquí Odoo crea los movimientos de inventario;
            # stock_account generará valoración/asientos cuando la categoría
            # tenga valoración automática y configuración contable válida.
            if quants_to_apply:
                quants_to_apply.with_context(
                    inventory_mode=True,
                    adj_context=inventory.id,
                ).action_apply_inventory()

            inventory.move_ids.invalidate_recordset(
                ["state", "account_move_id"]
                if "account_move_id" in inventory.move_ids._fields
                else ["state"]
            )
            inventory.state = 'done'

            if inventory.inventory_count_id:
                inventory.inventory_count_id.state = 'Inventory Adjusted'
                inventory.inventory_count_id.message_post(
                    body=_(
                        "Ajuste de inventario %(adjustment)s aplicado: "
                        "%(moves)s movimiento(s) de stock generado(s)."
                    ) % {
                        "adjustment": inventory.display_name,
                        "moves": len(inventory.move_ids),
                    }
                )

        return True

    def action_start(self):
        self.state = 'confirm'

    def action_check(self):
        for inventory in self.filtered(lambda x: x.state not in ('done', 'cancel')):
            inventory.with_context(prefetch_fields=False).mapped('move_ids').unlink()
            inventory.line_ids._generate_moves()
