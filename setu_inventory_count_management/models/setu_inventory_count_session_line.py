# -*- coding: utf-8 -*-
from email.policy import default

from odoo import fields, models, api, _
from odoo.exceptions import UserError


class InventoryCountSessionLine(models.Model):
    _name = 'setu.inventory.count.session.line'
    _description = 'Inventory Count Session Line'

    user_calculation_mistake = fields.Boolean(copy=False, default=False, string="User calculation mistake")
    product_scanned = fields.Boolean(copy=False, default=False, string="Product scanned")
    is_system_generated = fields.Boolean(string="System Generated Line")
    is_multi_session = fields.Boolean(default=False, string="Is multi session")
    is_discrepancy_found = fields.Boolean(compute="_compute_is_discrepancy_found", store=True, string="Discrepancy Found")

    scanned_qty = fields.Float(copy=False, string="Scanned quantity")
    to_be_scanned = fields.Float(string="To be quantity")
    theoretical_qty = fields.Float(string="Theoretical quantity",compute='_compute_theoretical_qty',store=True)

    date_of_scanning = fields.Datetime(string="Date of scanning", default=fields.Datetime.now)

    state = fields.Selection([('Pending Review', 'Pending Review'), ('Approve', 'Approve'), ('Reject', 'Reject')],
                             default="Pending Review", string="State")

    inventory_count_id = fields.Many2one(comodel_name="setu.stock.inventory.count", string="Inventory count")
    product_id = fields.Many2one(comodel_name="product.product", string="Product")
    session_id = fields.Many2one(comodel_name="setu.inventory.count.session", string="Session")
    inventory_count_line_id = fields.Many2one(comodel_name="setu.stock.inventory.count.line",
                                              string="Inventory count line")
    location_id = fields.Many2one(comodel_name="stock.location", string="Location")
    lot_id = fields.Many2one(comodel_name="stock.lot", string="Lot")

    serial_number_ids = fields.Many2many(comodel_name="stock.lot", string="Serial Numbers")
    not_found_serial_number_ids = fields.Many2many('stock.lot', 'session_not_found_stock_lot_rel', 'session_line_id',
                                                   'lot_id', string="Serial Numbers Not Founded")

    tracking = fields.Selection(related="product_id.tracking", string="Tracking")
    user_ids = fields.Many2many('res.users', string='Users', copy=False )
    difference_qty = fields.Float(string="Difference", compute="_compute_difference",
                                  help="Indicates the gap between the product's theoretical quantity and its newest quantity.",
                                  readonly=True, digits="Product Unit of Measure", search="_search_difference_qty",store=True)
    discrepancy_value = fields.Float(string='Discrepancy Value', compute='_compute_discrepancy_value', store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            inventory_count = self.env['setu.stock.inventory.count'].search(
                [('session_ids', 'in', vals.get('session_id'))])
            vals.update({'inventory_count_id': inventory_count.id})
            if vals.get('scanned_qty', 0) > 0:
                vals.update({'user_ids': [(6, 0, (self.user_ids | self.env.user).ids)]})
        return super(InventoryCountSessionLine, self).create(vals_list)

    @api.constrains('scanned_qty')
    def constrains_scanned_aty(self):
        for line in self:
            if line.scanned_qty < 0:
                raise UserError(_('Counted QTY cannot be less than zero.'))

    def change_line_state_to_approve(self):
        self.state = 'Approve'

    def change_line_state_to_reject(self):
        self.state = 'Reject'

    def set_theoretical(self):
        if self.tracking == 'lot':
            self.scanned_qty = self.theoretical_qty
        elif self.tracking == 'serial':
            self.write(
                {'serial_number_ids': [(6, 0, self.serial_number_ids.ids + self.not_found_serial_number_ids.ids)],
                 'not_found_serial_number_ids': [(5, 0)],
                 'scanned_qty': len(self.serial_number_ids.ids + self.not_found_serial_number_ids.ids)
                 })

    def set_mark_scanned(self):
        self.product_scanned = True

    def set_mark_unscanned(self):
        self.product_scanned = False

    @api.depends('lot_id', 'product_id', 'serial_number_ids', 'location_id')
    def _compute_theoretical_qty(self):
        for line in self:
            domain = [('location_id', '=', line.location_id.id),
                      ('product_id', '=', line.product_id.id)]
            if line.product_id and line.location_id:
                if line.lot_id:
                    domain.append(('lot_id', '=', line.lot_id.id))
                quants = self.env['stock.quant'].sudo().search(domain)
                theoretical_qty = sum(x.quantity for x in quants)
                line.theoretical_qty = theoretical_qty
                if line.product_id.tracking == 'serial':
                    line.scanned_qty = len(line.serial_number_ids)
            else:
                line.theoretical_qty = 0

    @api.onchange('product_id', 'lot_id', 'location_id', 'serial_number_ids')
    def _onchange_product_id(self):
        if self.location_id:
            allowed_location = self.env['stock.location'].sudo().search(
                [('location_id', 'child_of', self.session_id.location_id.id)])
            if self.location_id.id not in allowed_location.ids:
                raise UserError(_(
                    '{} The selected location does not belong to the warehouse of this Inventory Count. Please choose the appropriate main location or a sub-location within the main warehouse.'.format(
                        self.location_id.display_name)))
        self.scanned_qty = len(self.serial_number_ids)
        if not self.session_id.session_id and not self.session_id.inventory_count_id.count_id:
            session_lines = self.session_id.inventory_count_id.session_ids.mapped('session_line_ids')
            if self.product_id.tracking == 'lot' and self.product_id and self.location_id and self.lot_id and not self.session_id.session_id:
                if self.product_id.id in session_lines.filtered(lambda x: x.product_id == self.product_id and
                                                                          x.location_id == self.location_id and
                                                                          x.state != 'Cancel'
                                                                          and x.lot_id == self.lot_id
                                                                          and x.session_id.id == self.session_id._origin.id
                                                                          and x.session_id.inventory_count_id == self.session_id.inventory_count_id).mapped(
                    'product_id').ids:
                    raise UserError(
                        'Lot "{}" is already scanned for the same location in the same session for this Count.'.format(
                            self.lot_id.name))
            elif self.product_id.tracking == 'none' and self.product_id and self.location_id and not self.session_id.session_id:
                if self.product_id.id in session_lines.filtered(lambda x: x.product_id == self.product_id
                                                                          and x.location_id == self.location_id
                                                                          and x.session_id.id == self.session_id._origin.id
                                                                          and x.session_id.state != 'Cancel'
                                                                          and x.session_id.inventory_count_id == self.session_id.inventory_count_id).mapped(
                    'product_id').ids:
                    raise UserError(
                        'Product "{}" is already scanned for the same location in the same session for this Count.'.format(
                            self.product_id.display_name))
            elif self.product_id.tracking == 'serial' and self.location_id and not self.session_id.session_id:
                if self.product_id.id in session_lines.filtered(lambda x: x.product_id == self.product_id
                                                                          and x.session_id.state != 'Cancel'
                                                                          and (
                                                                                  x.location_id != self.location_id or x.location_id == self.location_id)
                                                                          and any(
                    b in x.serial_number_ids.ids for b in self.serial_number_ids.ids)
                                                                          and x.session_id.inventory_count_id == self.session_id.inventory_count_id).mapped(
                    'product_id').ids:
                    same_found = session_lines.filtered(lambda x: x.product_id == self.product_id
                                                                  and x.id not in self.ids
                                                                  and (
                                                                          x.location_id != self.location_id or x.location_id == self.location_id)
                                                                  and any(
                        b in x.serial_number_ids.ids for b in self.serial_number_ids.ids)
                                                                  and x.session_id.state != 'Cancel'
                                                                  and x.session_id.inventory_count_id == self.session_id.inventory_count_id)
                    if same_found:
                        same_found = list(
                            set(same_found.mapped('serial_number_ids').ids) & set(self.serial_number_ids.ids))
                        same_found = self.env['stock.lot'].sudo().browse(same_found)
                        same_found_str = ", ".join(same_found.mapped('name'))
                        raise UserError(_(f'Serial Number "{same_found_str}" is already scanned by another user '
                                          f'in another session for this Count.'))


    def _get_theoretical_qty(self, count_line_exists_already=False, location=False):
        for line in self:
            if line.product_id and line.location_id:
                domain = [('location_id', '=', location.id if location else line.location_id.id),
                          ('product_id', '=', line.product_id.id),
                          ]
                if line.product_id.tracking == 'lot':
                    domain.append(('lot_id', '=', line.lot_id.id))

                elif line.product_id.tracking == 'serial':
                    domain.append(('quantity', '>', 0))

                quants = self.env['stock.quant'].sudo().search(domain)

                theoretical_qty = sum(x.quantity for x in quants)

                if count_line_exists_already or location:
                    return theoretical_qty

                line.theoretical_qty = theoretical_qty
            else:
                line.theoretical_qty = 0

    def _get_counted_qty(self, line, count_line_exists_already=False):
        if line.product_id.tracking == 'serial':
            sessions = line.session_id.inventory_count_id.session_ids
            serial_type_session_lines = sessions.session_line_ids.filtered(
                lambda l: l.product_id.id == line.product_id.id and l.location_id.id == line.location_id.id)
            serial_numbers = serial_type_session_lines.mapped('serial_number_ids').filtered(lambda s: s.product_qty < 1)
            moves = self.env['stock.move.line'].sudo().search([('state', '=', 'done'),
                                                               ('product_id', '=', line.product_id.id),
                                                               ('move_id.picking_type_id.code', '=', 'outgoing'),
                                                               ('lot_id.id', 'in', serial_numbers.ids),
                                                               ('date', '>=', line.date_of_scanning)])
            moves.write({'count_id': line.session_id.inventory_count_id.id})
            final_serial_numbers = serial_type_session_lines.mapped('serial_number_ids') - serial_numbers
            return len(final_serial_numbers)
        elif line.product_id.tracking == 'none':
            if line.session_id.session_id:
                qty = line.scanned_qty
            else:
                qty = count_line_exists_already.counted_qty + line.scanned_qty

            moves = self.env['stock.move.line'].sudo().search([('state', '=', 'done'),
                                                               ('product_id', '=', line.product_id.id),
                                                               ('move_id.picking_type_id.code', '=', 'outgoing'),
                                                               ('date', '>=', line.date_of_scanning)])
            qty -= sum(x.quantity for x in moves)
            moves.write({'count_id': line.session_id.inventory_count_id.id})
            return qty
        elif line.product_id.tracking == 'lot':
            if line.session_id.session_id:
                qty = line.scanned_qty
            else:
                qty = count_line_exists_already.counted_qty + line.scanned_qty

            moves = self.env['stock.move.line'].sudo().search([('state', '=', 'done'),
                                                               ('product_id', '=', line.product_id.id),
                                                               ('move_id.picking_type_id.code', '=', 'outgoing'),
                                                               ('lot_id', '=', line.lot_id.id),
                                                               ('date', '>=', line.date_of_scanning)])
            qty -= sum(x.quantity for x in moves)
            moves.write({'count_id': line.session_id.inventory_count_id.id})
            return qty

    def _get_serial_number_ids(self, line):
        sessions = line.session_id.inventory_count_id.session_ids
        serial_type_session_lines = sessions.session_line_ids.filtered(
            lambda l: l.product_id.id == line.product_id.id and l.location_id.id == line.location_id.id)
        serial_numbers = serial_type_session_lines.mapped('serial_number_ids').filtered(lambda s: s.product_qty < 1)
        final_serial_numbers = serial_type_session_lines.mapped('serial_number_ids') - serial_numbers
        return [(6, 0, final_serial_numbers.ids)]

    def write(self,vals):
        if 'scanned_qty' in vals and vals['scanned_qty'] > 0:
            self.user_ids = [(6, 0, (self.user_ids | self.env.user).ids)]
        return super(InventoryCountSessionLine, self).write(vals)

    @api.depends('scanned_qty', 'theoretical_qty')
    def _compute_difference(self):
        for line in self:
            if line.theoretical_qty < 0:
                difference = line.scanned_qty
            else:
                difference = line.scanned_qty - line.theoretical_qty
            line.difference_qty = difference

    @api.depends('scanned_qty', 'theoretical_qty')
    def _compute_is_discrepancy_found(self):
        for line in self:
            if line.theoretical_qty < 0:
                line.is_discrepancy_found = False
            else:
                difference = abs(line.scanned_qty - line.theoretical_qty)
                line.is_discrepancy_found = difference > 0

    @api.depends('difference_qty', 'product_id', 'lot_id')
    def _compute_discrepancy_value(self):
        for line in self:
            cost = line.product_id.standard_price or 0.0
            if line.lot_id and line.lot_id.purchase_order_ids:
                po_lines = line.lot_id.purchase_order_ids.mapped('order_line').filtered(lambda l: l.product_id == line.product_id)
                total_qty = sum(po_lines.mapped('product_qty'))
                total_value = sum(po_lines.mapped('price_subtotal'))
                if total_qty:
                    cost = total_value / total_qty
            line.discrepancy_value = line.difference_qty * cost
