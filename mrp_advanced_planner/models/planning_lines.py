from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PlanningPlanLine(models.Model):
    _name = 'mrp.planning.plan.line'
    _description = 'Planning Product Summary'
    _order = 'date_required, priority desc, id'

    plan_id = fields.Many2one('mrp.planning.plan', required=True, ondelete='cascade', index=True)
    plan_state = fields.Selection(related='plan_id.state', store=False)
    sale_line_id = fields.Many2one('sale.order.line', string='Línea de venta', index=True, ondelete='set null')
    sale_order_id = fields.Many2one(related='sale_line_id.order_id', string='Pedido de venta', store=True, index=True)
    partner_id = fields.Many2one(related='sale_line_id.order_id.partner_id', string='Cliente', store=True, index=True)
    product_id = fields.Many2one('product.product', required=True, index=True)
    product_uom_id = fields.Many2one(related='product_id.uom_id', store=True)
    warehouse_id = fields.Many2one(related='plan_id.warehouse_id', store=True)
    demand_qty = fields.Float()
    sales_qty = fields.Float()
    stock_qty = fields.Float(string='Inventario aplicado')
    reserved_qty = fields.Float()
    incoming_qty = fields.Float()
    outgoing_qty = fields.Float()
    production_qty = fields.Float(string='Fabricación aplicada')
    net_requirement_qty = fields.Float()
    planned_production_qty = fields.Float(string='Cantidad a fabricar')
    planned_purchase_qty = fields.Float()
    date_required = fields.Datetime(index=True)
    date_planned_start = fields.Datetime()
    date_planned_finish = fields.Datetime()
    priority = fields.Selection(related='plan_id.priority', store=True)
    source_type = fields.Selection([('sale', 'Sales'), ('manual', 'Manual'), ('mrp', 'Manufacturing')], default='sale')
    source_reference = fields.Char()
    bom_id = fields.Many2one('mrp.bom')
    route_id = fields.Many2one('stock.route')
    state = fields.Selection([('draft', 'Borrador'), ('planned', 'Listo'), ('blocked', 'Sin LdM'), ('applied', 'OF creada')], default='draft', index=True)
    created_production_id = fields.Many2one('mrp.production', string='Orden de fabricación', copy=False, readonly=True)

    def unlink(self):
        protected = self.filtered(lambda line: line.created_production_id or line.plan_id.state == 'approved')
        if protected:
            raise UserError(_('No puede eliminar un pronóstico después de aprobar el plan o crear su orden de fabricación.'))
        return super().unlink()

    def action_open_product(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.product_id.display_name,
            'res_model': 'product.product',
            'res_id': self.product_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    def action_open_sales(self):
        self.ensure_one()
        if self.sale_line_id and self.sale_order_id:
            return {
                'type': 'ir.actions.act_window',
                'name': self.sale_order_id.display_name,
                'res_model': 'sale.order',
                'res_id': self.sale_order_id.id,
                'view_mode': 'form',
                'views': [(False, 'form')],
                'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pedidos - %s') % self.product_id.display_name,
            'res_model': 'sale.order.line',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [
                ('product_id', '=', self.product_id.id),
                ('order_id.company_id', '=', self.plan_id.company_id.id),
                ('order_id.state', '=', 'sale'),
            ],
        }

    def action_open_manufacturing(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fabricación - %s') % self.product_id.display_name,
            'res_model': 'mrp.production',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [
                ('product_id', '=', self.product_id.id),
                ('company_id', '=', self.plan_id.company_id.id),
            ],
        }

    def action_open_purchases(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Compras - %s') % self.product_id.display_name,
            'res_model': 'purchase.order.line',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [
                ('product_id', '=', self.product_id.id),
                ('company_id', '=', self.plan_id.company_id.id),
            ],
        }

    def action_open_inventory(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Inventario - %s') % self.product_id.display_name,
            'res_model': 'stock.quant',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [
                ('product_id', '=', self.product_id.id),
                ('location_id', 'child_of', self.plan_id.warehouse_id.lot_stock_id.id),
            ],
            'context': {'search_default_internal_loc': 1},
        }


class PlanningDemand(models.Model):
    _name = 'mrp.planning.demand'
    _description = 'Planning Demand'
    _order = 'date_required, id'

    plan_id = fields.Many2one('mrp.planning.plan', required=True, ondelete='cascade', index=True)
    sale_line_id = fields.Many2one('sale.order.line', index=True)
    product_id = fields.Many2one('product.product', required=True, index=True)
    company_id = fields.Many2one(related='plan_id.company_id', store=True)
    warehouse_id = fields.Many2one(related='plan_id.warehouse_id', store=True)
    date_required = fields.Datetime(required=True, index=True)
    quantity = fields.Float(required=True)
    delivered_qty = fields.Float()
    remaining_qty = fields.Float(compute='_compute_remaining', store=True)
    priority = fields.Selection([('0', 'Normal'), ('1', 'High'), ('2', 'Urgent')], default='0')
    source_reference = fields.Char()

    @api.depends('quantity', 'delivered_qty')
    def _compute_remaining(self):
        for record in self:
            record.remaining_qty = max(record.quantity - record.delivered_qty, 0.0)


class PlanningRequirement(models.Model):
    _name = 'mrp.planning.requirement'
    _description = 'Planning Material Requirement'

    plan_id = fields.Many2one('mrp.planning.plan', required=True, ondelete='cascade', index=True)
    parent_id = fields.Many2one('mrp.planning.requirement', ondelete='cascade')
    product_id = fields.Many2one('product.product', required=True, index=True)
    bom_id = fields.Many2one('mrp.bom')
    bom_line_id = fields.Many2one('mrp.bom.line')
    level = fields.Integer(default=0)
    required_qty = fields.Float(required=True)
    available_qty = fields.Float()
    net_qty = fields.Float()
    date_required = fields.Datetime(index=True)
    supply_type = fields.Selection([('available', 'Available'), ('existing', 'Existing Supply'), ('make', 'Make'), ('buy', 'Buy'), ('blocked', 'Blocked')], default='blocked')
