# -*- coding: utf-8 -*-
from odoo import fields, models,api

class StockInvCountLine(models.Model):
    _name = 'setu.stock.inventory.count.line'
    _description = 'Stock Inventory Count Line'

    is_discrepancy_found = fields.Boolean(compute="_compute_is_discrepancy_found", store=True, depends=['counted_qty'],
                                          string="Hay discrepancia")
    user_calculation_mistake = fields.Boolean(default=False, string="Error de cálculo del usuario")
    is_multi_session = fields.Boolean(default=False, string="Es multisesión")
    is_system_generated = fields.Boolean(string="Línea generada por el sistema")

    theoretical_qty = fields.Float(string="Theoretical Qty")
    qty_in_stock = fields.Float(string="Cantidad en existencias")
    counted_qty = fields.Float(string="Cantidad contada")

    state = fields.Selection([('Pending Review', 'Pendiente de revisión'), ('Approve', 'Aprobar'), ('Reject', 'Rechazar')],
                             default="Pending Review", string="Estado")

    inventory_count_id = fields.Many2one(comodel_name="setu.stock.inventory.count", string="Inventory Count")
    product_id = fields.Many2one(comodel_name="product.product", string="Producto")
    location_id = fields.Many2one(comodel_name="stock.location", string="Ubicación")
    lot_id = fields.Many2one(comodel_name="stock.lot", string="Lote")

    session_line_ids = fields.One2many('setu.inventory.count.session.line', 'inventory_count_line_id',
                                       string="Líneas de sesión")

    new_count_lot_ids = fields.Many2many('stock.lot', 'new_count_stock_rel', string='Nuevos números de serie contados')
    serial_number_ids = fields.Many2many('stock.lot', 'setu_stock_inventory_count_line_stock_lot_rel',
                                         'setu_stock_inventory_count_line_id', 'stock_lot_id', string='Números de serie')
    not_found_serial_number_ids = fields.Many2many('stock.lot', 'not_found_stock_lot_rel', 'count_line_id', 'lot_id',
                                                   string='Números de serie no encontrados')

    tracking = fields.Selection(related="product_id.tracking", string="Tracking")
    user_ids = fields.Many2many('res.users',string='Users')
    difference_qty = fields.Float(string="Diferencia", compute="_compute_difference",
                                  help="Indica la diferencia entre la cantidad teórica del producto y la cantidad física más reciente.",
                                  readonly=True, digits="Product Unit of Measure", search="_search_difference_qty",store=True)
    discrepancy_value = fields.Float(string='Valor de discrepancia', compute='_compute_discrepancy_value', store=True)

    def change_line_state_to_approve(self):
        self.state = 'Approve'

    def change_line_state_to_reject(self):
        self.state = 'Reject'

    def _compute_is_discrepancy_found(self):
        for line in self:
            line.is_discrepancy_found = False
            if line.product_id.tracking == 'serial':
                quants = self.env['stock.quant'].sudo().search(
                    [('location_id', '=', line.location_id.id),
                     ('quantity', '=', 1),
                     ('product_id', '=', line.product_id.id)])
                if not quants:
                    line.is_discrepancy_found = True
                    continue
                additional_quants = list(set(quants.lot_id.ids) ^ set(line.serial_number_ids.ids))
                if additional_quants:
                    line.is_discrepancy_found = True
            elif line.counted_qty != line.qty_in_stock:
                line.is_discrepancy_found = True

    @api.depends('counted_qty', 'theoretical_qty')
    def _compute_difference(self):
        for line in self:
            if line.theoretical_qty < 0:
                difference = line.counted_qty
            else:
                difference = line.counted_qty - line.theoretical_qty
            line.difference_qty = difference

    @api.depends('difference_qty', 'product_id', 'lot_id', 'not_found_serial_number_ids')
    def _compute_discrepancy_value(self):
        for line in self:
            cost = line.product_id.standard_price or 0.0
            if line.product_id.tracking == 'lot' and line.lot_id and line.lot_id.purchase_order_ids:
                po_lines = line.lot_id.purchase_order_ids.mapped('order_line').filtered(
                    lambda l: l.product_id == line.product_id)
                total_qty = sum(po_lines.mapped('product_qty'))
                total_value = sum(po_lines.mapped('price_subtotal'))
                if total_qty:
                    cost = total_value / total_qty
            elif line.product_id.tracking == 'serial' and line.not_found_serial_number_ids:
                unit_prices = []
                for serial in line.not_found_serial_number_ids:
                    if serial.purchase_order_ids:
                        po_lines = serial.purchase_order_ids.mapped('order_line').filtered(
                            lambda l: l.product_id == line.product_id)
                        unit_prices += po_lines.mapped('price_unit')
                if unit_prices:
                    cost = sum(unit_prices) / len(unit_prices)
            line.discrepancy_value = line.difference_qty * cost
