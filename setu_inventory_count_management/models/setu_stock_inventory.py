# -*- coding: utf-8 -*-
from odoo import fields, models


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

    product_ids = fields.Many2many('product.product', string='Productos', check_company=True,
                                   domain="[('type', '=', 'product'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
                                   readonly=True,
                                   help="Especifique productos para limitar el inventario a esos productos.")

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

    def action_validate(self):
        serial_lot_dict = {}
        auto_inventory_adjustment = self.env['ir.config_parameter'].sudo().get_param('setu_inventory_count_management.auto_inventory_adjustment')
        for line in self.line_ids:
            if line.product_id.tracking == 'serial':
                if not serial_lot_dict.get((line.product_id, line.location_id), False):
                    serial_lot_dict.update({(line.product_id, line.location_id): line.serial_number_ids})
                else:
                    old_lots = serial_lot_dict.get((line.product_id, line.location_id), False)
                    old_lots += line.serial_number_ids
                    serial_lot_dict.update({(line.product_id, line.location_id): old_lots})
                for sr_num in line.serial_number_ids:
                    quant = self.env['stock.quant'].sudo().search(
                        [('location_id', '=', line.location_id.id), ('lot_id', '=', sr_num.id),
                         ('product_id', '=', line.product_id.id),
                         ('quantity', '>', 0)], limit=1)
                    if quant:
                        if line.product_qty == 0:
                            quant.with_context(inventory_mode=True).write({'inventory_quantity': 0})
                        continue
                    quant_on_another_location = self.env['stock.quant'].sudo().search(
                        [('lot_id', '=', sr_num.id),
                         ('product_id', '=', line.product_id.id),
                         ('location_id.usage', '=', 'internal'),
                         ('quantity', '>', 0)], limit=1)
                    if quant_on_another_location:
                        quant_on_another_location.with_context(inventory_mode=True).write({'inventory_quantity': 0})
                        if auto_inventory_adjustment:
                            quant_on_another_location.with_context(adj_context=self.id).action_apply_inventory()

                    quant = self.env['stock.quant'].with_context(inventory_mode=True).sudo().create(
                        {'product_id': line.product_id.id, 'location_id': line.location_id.id,
                         'lot_id': sr_num.id,
                         'inventory_quantity': 1})
            elif line.product_id.tracking == 'lot':
                quant = self.env['stock.quant'].sudo().search([('lot_id', '=', line.prod_lot_id.id),
                                                               ('location_id', '=', line.location_id.id),
                                                               ('product_id', '=', line.product_id.id)], limit=1)
                if quant:
                    quant.inventory_quantity = line.product_qty
                else:
                    quant = self.env['stock.quant'].with_context(inventory_mode=True).sudo().create(
                        {'product_id': line.product_id.id, 'location_id': line.location_id.id,
                         'lot_id': line.prod_lot_id.id,
                         'inventory_quantity': line.product_qty})
            else:
                quant = self.env['stock.quant'].sudo().search(
                    [('location_id', '=', line.location_id.id), ('product_id', '=', line.product_id.id)], limit=1)
                if quant:
                    quant.with_context(inventory_mode=True).write({'inventory_quantity': line.product_qty})
                else:
                    quant = self.env['stock.quant'].with_context(inventory_mode=True).sudo().create(
                        {'product_id': line.product_id.id, 'location_id': line.location_id.id,
                         'inventory_quantity': line.product_qty})
            if quant:
                line.quant_id = quant
                if auto_inventory_adjustment:
                    quant.with_context(adj_context=self.id).action_apply_inventory()

        # if serial_lot_dict:
        #     for k, v in serial_lot_dict.items():
        #         if not v:
        #             continue
        #         found_numbers = self.inventory_count_id.line_ids.filtered(
        #             lambda x: x.location_id.id == k[1].id and x.product_id.id == k[0].id).mapped('serial_number_ids')
        #         total_found_numbers = v + found_numbers
        #         if total_found_numbers:
        #             other_quant_at_the_location = self.env['stock.quant'].sudo().search(
        #                 [('location_id', '=', k[1].id), ('lot_id', 'not in', total_found_numbers.ids),
        #                  ('product_id', '=', k[0].id), ('quantity', '>', 0)])
        #             if other_quant_at_the_location:
        #                 for q in other_quant_at_the_location:
        #                     q.with_context(inventory_mode=True).write({'inventory_quantity': 0})
        #                     if auto_inventory_adjustment:
        #                         q.with_context(adj_context=self.id).action_apply_inventory()

        self.state = 'done'
        if self.inventory_count_id:
            self.inventory_count_id.state = 'Inventory Adjusted'

    def action_start(self):
        self.state = 'confirm'

    def action_check(self):
        for inventory in self.filtered(lambda x: x.state not in ('done', 'cancel')):
            inventory.with_context(prefetch_fields=False).mapped('move_ids').unlink()
            inventory.line_ids._generate_moves()
