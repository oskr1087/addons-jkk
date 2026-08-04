# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import ValidationError


class SessionCreator(models.TransientModel):
    _name = 'setu.inventory.session.creator'
    _description = 'Inventory Session Creator'

    is_multi_session = fields.Boolean(default=False, string="Is multi Session")

    inventory_count_id = fields.Many2one(comodel_name="setu.stock.inventory.count", string="Inventory Count")

    user_ids = fields.Many2many(comodel_name="res.users", string="Users",
                                domain="[('company_ids', 'in', allowed_company_ids),('share','=',False)]")
    product_ids = fields.Many2many(comodel_name="product.product", string="Products")

    parent_count_id = fields.Many2one(related='inventory_count_id.count_id', string="Parent Count")

    def confirm(self, users=False):
        if not self.user_ids:
            raise ValidationError(_("Please add User(s)."))
        else:
            count_id = self.env['setu.stock.inventory.count'].sudo().browse(self.inventory_count_id.id) or self.env[
                'setu.stock.inventory.count'].sudo().browse(self.env.context.get('active_id', False))
            if count_id.type == 'Multi Session':
                is_multi_session = True
            else:
                is_multi_session = False
            session = self.env['setu.inventory.count.session'].create({
                'is_multi_session': is_multi_session,
                'inventory_count_id': self.inventory_count_id.id,
                'location_id': self.inventory_count_id.location_id.id,
                'warehouse_id': self.inventory_count_id.warehouse_id.id,
                'use_barcode_scanner': self.inventory_count_id.use_barcode_scanner
            })
            session.user_ids = self.user_ids or users
            session_line_vals = []
            domain = [('location_id', '=', self.inventory_count_id.location_id.id)]
            locations = self.env['stock.location'].sudo().search(domain)
            if not count_id.count_id:
                for product in self.product_ids:
                    for loc in locations:
                        inv_count_line = self.inventory_count_id.line_ids.filtered(
                            lambda l: l.product_id == product and l.location_id == loc)
                        if not inv_count_line:
                            inv_count_line = self.env['setu.stock.inventory.count.line'].create({
                                'product_id': product.id,
                                'inventory_count_id': self.inventory_count_id.id,
                                'location_id': loc.id
                            })
                        session_line_vals.append((0, 0, {
                            'product_id': product.id,
                            'inventory_count_id': self.inventory_count_id.id,
                            'inventory_count_line_id': inv_count_line.id,
                            'location_id': loc.id,
                            'is_multi_session': session.is_multi_session,
                        }))
            else:
                for line in count_id.line_ids.filtered(lambda p: p.product_id in self.product_ids):
                    session_line_vals.append((0, 0, {
                        'product_id': line.product_id.id,
                        'location_id': line.location_id.id,
                        'inventory_count_id': count_id.id,
                        'inventory_count_line_id': line.id,
                        'is_multi_session': session.is_multi_session,
                    }))
            session.write({'session_line_ids': session_line_vals})
