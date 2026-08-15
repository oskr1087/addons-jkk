from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PlanningPlanLine(models.Model):
    _name = 'mrp.planning.plan.line'
    _description = 'Resumen de producto de planificación'
    _order = 'date_required, priority desc, product_id, id'

    plan_id = fields.Many2one('mrp.planning.plan', required=True, ondelete='cascade', index=True)
    plan_state = fields.Selection(related='plan_id.state', store=False)

    # Legacy single source fields are kept for upgrade compatibility. New plans use sale_line_ids.
    sale_line_id = fields.Many2one('sale.order.line', string='Línea de venta principal', index=True, ondelete='set null')
    sale_line_ids = fields.Many2many(
        'sale.order.line', 'mrp_planning_line_sale_rel', 'planning_line_id', 'sale_line_id',
        string='Líneas de venta origen', copy=False,
    )
    sale_order_id = fields.Many2one(related='sale_line_id.order_id', string='Pedido principal', store=True, index=True)
    partner_id = fields.Many2one(related='sale_line_id.order_id.partner_id', string='Cliente principal', store=True, index=True)
    sale_order_count = fields.Integer(compute='_compute_source_counts', string='Pedidos')
    sale_line_count = fields.Integer(compute='_compute_source_counts', string='Líneas de venta')

    product_id = fields.Many2one('product.product', required=True, index=True)
    product_uom_id = fields.Many2one(related='product_id.uom_id', store=True)
    target_warehouse_id = fields.Many2one(
        'stock.warehouse', string='Almacén destino', check_company=True,
        help='Almacén donde se fabricará o recibirá la compra. Para movimientos se calcula el origen/destino por el detalle de almacenes.',
    )
    warehouse_detail_ids = fields.One2many(
        'mrp.planning.plan.line.warehouse', 'planning_line_id', string='Detalle por almacén', copy=False,
    )

    demand_qty = fields.Float(string='Demanda')
    sales_qty = fields.Float(string='Ventas pendientes')
    stock_qty = fields.Float(string='Stock disponible')
    stock_warehouse_tooltip = fields.Char(
        string='Stock por almacén',
        compute='_compute_stock_warehouse_tooltip',
        help='Detalle del stock disponible en cada almacén seleccionado en la planificación.',
    )
    reserved_qty = fields.Float()
    incoming_qty = fields.Float()
    outgoing_qty = fields.Float()
    production_qty = fields.Float(string='OF abiertas')
    net_requirement_qty = fields.Float(string='Necesidad neta')
    move_suggested_qty = fields.Float(string='Mover sugerido')

    # New generic planning quantity. The old field stays for technical backwards compatibility.
    planner_production_qty = fields.Float(string='Cantidad planificada')
    planned_production_qty = fields.Float(string='Cantidad a fabricar (legacy)')
    planned_purchase_qty = fields.Float()

    action_manufacture = fields.Boolean(string='Fabricar')
    action_purchase = fields.Boolean(string='Comprar')
    action_move = fields.Boolean(string='Mover')
    action_label = fields.Char(compute='_compute_action_label', string='Acción')

    date_required = fields.Datetime(string='Entrega más próxima', index=True)
    date_planned_start = fields.Datetime()
    date_planned_finish = fields.Datetime()
    priority = fields.Selection(related='plan_id.priority', store=True)
    source_type = fields.Selection([('sale', 'Ventas'), ('manual', 'Manual'), ('mrp', 'Fabricación')], default='sale')
    source_reference = fields.Char()
    bom_id = fields.Many2one('mrp.bom', string='LdM')
    route_id = fields.Many2one('stock.route')
    state = fields.Selection([
        ('draft', 'Borrador'), ('planned', 'Listo'), ('blocked', 'Revisar'), ('applied', 'Generado')
    ], default='draft', index=True)

    created_production_id = fields.Many2one('mrp.production', string='Orden de fabricación', copy=False, readonly=True)
    created_purchase_line_id = fields.Many2one('purchase.order.line', string='Línea de compra', copy=False, readonly=True)
    created_picking_ids = fields.Many2many(
        'stock.picking', 'mrp_planning_line_picking_rel', 'planning_line_id', 'picking_id',
        string='Reabastecimientos', copy=False, readonly=True,
    )

    @api.depends(
        'warehouse_detail_ids.stock_qty',
        'warehouse_detail_ids.warehouse_id',
        'plan_id.warehouse_ids',
    )
    def _compute_stock_warehouse_tooltip(self):
        for line in self:
            details = {
                detail.warehouse_id.id: detail.stock_qty
                for detail in line.warehouse_detail_ids
                if detail.warehouse_id
            }
            warehouses = line.plan_id.warehouse_ids.sorted(
                key=lambda wh: (wh.sequence, wh.name, wh.id)
            )
            values = []
            for warehouse in warehouses:
                qty = details.get(warehouse.id, 0.0)
                qty_text = ('%.2f' % qty).rstrip('0').rstrip('.') if qty else '0'
                values.append('%s: %s' % (warehouse.display_name, qty_text))
            line.stock_warehouse_tooltip = '\n'.join(values) or _('Sin detalle de almacenes')

    @api.depends('sale_line_ids')
    def _compute_source_counts(self):
        for line in self:
            source_lines = line.sale_line_ids or line.sale_line_id
            line.sale_line_count = len(source_lines)
            line.sale_order_count = len(source_lines.mapped('order_id'))

    @api.depends('action_manufacture', 'action_purchase', 'action_move')
    def _compute_action_label(self):
        for line in self:
            if line.action_manufacture:
                line.action_label = _('Fabricar')
            elif line.action_purchase:
                line.action_label = _('Comprar')
            elif line.action_move:
                line.action_label = _('Mover')
            else:
                line.action_label = _('Sin definir')

    def _suggested_qty_for_action(self):
        self.ensure_one()
        return self.move_suggested_qty if self.action_move else self.net_requirement_qty

    @api.onchange('action_manufacture')
    def _onchange_action_manufacture(self):
        if self.action_manufacture:
            self.action_purchase = False
            self.action_move = False
            self.planner_production_qty = self.net_requirement_qty

    @api.onchange('action_purchase')
    def _onchange_action_purchase(self):
        if self.action_purchase:
            self.action_manufacture = False
            self.action_move = False
            self.planner_production_qty = self.net_requirement_qty

    @api.onchange('action_move')
    def _onchange_action_move(self):
        if self.action_move:
            self.action_manufacture = False
            self.action_purchase = False
            self.planner_production_qty = self.move_suggested_qty

    @api.constrains('action_manufacture', 'action_purchase', 'action_move')
    def _check_single_action(self):
        for line in self:
            if sum(bool(value) for value in (line.action_manufacture, line.action_purchase, line.action_move)) > 1:
                raise ValidationError(_('Solo puede seleccionar una acción por producto: Fabricar, Comprar o Mover.'))

    @api.constrains('planner_production_qty')
    def _check_planner_qty(self):
        for line in self:
            if line.planner_production_qty < 0:
                raise ValidationError(_('La cantidad planificada no puede ser negativa.'))

    def unlink(self):
        protected = self.filtered(
            lambda line: line.created_production_id or line.created_purchase_line_id or line.created_picking_ids
        )
        if protected:
            raise UserError(_('No puede eliminar una línea que ya generó fabricación, compra o reabastecimiento.'))
        return super().unlink()

    def action_open_warehouse_stock_detail(self):
        self.ensure_one()
        view = self.env.ref('mrp_advanced_planner.view_mrp_planning_line_warehouse_list')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Stock por almacén - %s') % self.product_id.display_name,
            'res_model': 'mrp.planning.plan.line.warehouse',
            'view_mode': 'list',
            'views': [(view.id, 'list')],
            'target': 'new',
            'domain': [('planning_line_id', '=', self.id)],
            'context': {'create': False, 'delete': False},
        }

    def action_open_product(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': self.product_id.display_name,
            'res_model': 'product.product', 'res_id': self.product_id.id,
            'view_mode': 'form', 'views': [(False, 'form')], 'target': 'current',
        }

    def action_open_sales(self):
        self.ensure_one()
        source_lines = self.sale_line_ids or self.sale_line_id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Ventas origen - %s') % self.product_id.display_name,
            'res_model': 'sale.order.line', 'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', source_lines.ids)],
        }

    def action_open_manufacturing(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Fabricación - %s') % self.product_id.display_name,
            'res_model': 'mrp.production', 'view_mode': 'list,form', 'views': [(False, 'list'), (False, 'form')],
            'domain': [('product_id', '=', self.product_id.id), ('company_id', '=', self.plan_id.company_id.id)],
        }

    def action_open_purchases(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Compras - %s') % self.product_id.display_name,
            'res_model': 'purchase.order.line', 'view_mode': 'list,form', 'views': [(False, 'list'), (False, 'form')],
            'domain': [('product_id', '=', self.product_id.id), ('company_id', '=', self.plan_id.company_id.id)],
        }

    def action_open_inventory(self):
        self.ensure_one()
        locations = self.plan_id.warehouse_ids.mapped('lot_stock_id')
        return {
            'type': 'ir.actions.act_window', 'name': _('Inventario - %s') % self.product_id.display_name,
            'res_model': 'stock.quant', 'view_mode': 'list,form', 'views': [(False, 'list'), (False, 'form')],
            'domain': [('product_id', '=', self.product_id.id), ('location_id', 'child_of', locations.ids)],
            'context': {'search_default_internal_loc': 1},
        }


class PlanningPlanLineWarehouse(models.Model):
    _name = 'mrp.planning.plan.line.warehouse'
    _description = 'Detalle de planificación por almacén'
    _order = 'warehouse_id, id'

    planning_line_id = fields.Many2one('mrp.planning.plan.line', required=True, ondelete='cascade', index=True)
    plan_id = fields.Many2one(related='planning_line_id.plan_id', store=True, index=True)
    product_id = fields.Many2one(related='planning_line_id.product_id', store=True, index=True)
    warehouse_id = fields.Many2one('stock.warehouse', required=True, index=True, ondelete='cascade')
    demand_qty = fields.Float(string='Demanda')
    stock_qty = fields.Float(string='Stock disponible')
    stock_warehouse_tooltip = fields.Char(
        string='Stock por almacén',
        compute='_compute_stock_warehouse_tooltip',
        help='Detalle del stock disponible en cada almacén seleccionado en la planificación.',
    )
    open_mo_qty = fields.Float(string='OF abiertas')
    local_shortage_qty = fields.Float(string='Faltante local')
    transferable_excess_qty = fields.Float(string='Excedente movible')


class PlanningDemand(models.Model):
    _name = 'mrp.planning.demand'
    _description = 'Planning Demand'
    _order = 'date_required, id'

    plan_id = fields.Many2one('mrp.planning.plan', required=True, ondelete='cascade', index=True)
    sale_line_id = fields.Many2one('sale.order.line', index=True)
    product_id = fields.Many2one('product.product', required=True, index=True)
    company_id = fields.Many2one(related='plan_id.company_id', store=True)
    warehouse_id = fields.Many2one('stock.warehouse', index=True)
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
