import json

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PlanningPlanLine(models.Model):
    _name = 'mrp.planning.plan.line'
    _description = 'Resumen de producto de planificación'
    _order = 'date_required, priority desc, product_id, id'

    plan_id = fields.Many2one('mrp.planning.plan', required=True, ondelete='cascade', index=True)
    plan_state = fields.Selection(related='plan_id.state', store=False)
    plan_type = fields.Selection(related='plan_id.plan_type', string='Tipo de planificación', store=True, index=True)

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
    sale_order_popover_data = fields.Text(
        string='Detalle de pedidos',
        compute='_compute_sale_order_popover_data',
    )

    product_id = fields.Many2one('product.product', required=True, index=True)
    product_uom_id = fields.Many2one(related='product_id.uom_id', store=True)
    target_warehouse_id = fields.Many2one(
        'stock.warehouse', string='Almacén destino', check_company=True,
        help='Almacén donde se fabricará o recibirá la compra. Para movimientos se calcula el origen/destino por el detalle de almacenes.',
    )
    production_component_ids = fields.One2many(
        'mrp.planning.production.component', 'planning_line_id',
        string='Componentes APS', copy=True,
    )
    warehouse_detail_ids = fields.One2many(
        'mrp.planning.plan.line.warehouse', 'planning_line_id', string='Detalle por almacén', copy=False,
    )

    demand_qty = fields.Float(string='Demanda')
    sales_qty = fields.Float(string='Demanda total')
    direct_sale_demand_qty = fields.Float(string='Demanda directa de ventas')
    mrp_component_demand_qty = fields.Float(string='Demanda desde fabricación')
    bom_origin_detail = fields.Text(
        string='Origen de componentes',
        help='Detalle de las rutas de LdM que originaron la necesidad de compra.',
    )
    stock_qty = fields.Float(
        string='Pronóstico disponible',
        help='Cantidad pronosticada al horizonte del plan. Incluye entradas/salidas de Odoo, RFQ pendientes y abastecimientos comprometidos en otras planificaciones.',
    )
    stock_warehouse_tooltip = fields.Char(
        string='Pronóstico por almacén',
        compute='_compute_stock_warehouse_tooltip',
        help='Detalle de la cantidad pronosticada por almacén al horizonte de la planificación.',
    )
    reserved_qty = fields.Float()
    incoming_qty = fields.Float(string='Entradas pronosticadas')
    outgoing_qty = fields.Float(string='Salidas pronosticadas')
    draft_purchase_qty = fields.Float(string='RFQ pendientes')
    other_plan_supply_qty = fields.Float(string='Otros planes')
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
    action_type = fields.Selection(
        [
            ('manufacture', 'Fabricar'),
            ('purchase', 'Comprar'),
            ('move', 'Mover'),
            ('none', 'Sin definir'),
        ],
        string='Acción',
        compute='_compute_action_type',
        store=True,
        index=True,
    )
    action_label = fields.Char(compute='_compute_action_label', string='Acción')
    purchase_vendor_id = fields.Many2one(
        'res.partner',
        string='Proveedor',
        domain="[('supplier_rank', '>', 0)]",
        help='Proveedor que se utilizará para crear la RFQ. Puede ser cualquier proveedor activo de Odoo.',
    )

    date_required = fields.Datetime(string='Entrega más próxima', index=True)
    date_planned_start = fields.Datetime()
    date_planned_finish = fields.Datetime()
    priority = fields.Selection(related='plan_id.priority', store=True)
    source_type = fields.Selection([('sale', 'Ventas'), ('manual', 'Manual'), ('mrp', 'Fabricación'), ('mixed', 'Ventas + fabricación')], default='sale')
    source_reference = fields.Char()
    bom_id = fields.Many2one('mrp.bom', string='LdM')
    route_id = fields.Many2one('stock.route')
    state = fields.Selection([
        ('draft', 'Borrador'), ('planned', 'Listo'), ('blocked', 'Revisar'), ('applied', 'Generado')
    ], default='draft', index=True)

    created_production_id = fields.Many2one('mrp.production', string='Orden de fabricación', copy=False, readonly=True)
    created_purchase_line_id = fields.Many2one('purchase.order.line', string='Línea de compra', copy=False, readonly=True)
    created_purchase_order_id = fields.Many2one(
        related='created_purchase_line_id.order_id',
        string='Orden de compra',
        readonly=True,
        store=False,
    )
    source_sale_order_ids = fields.Many2many(
        'sale.order',
        string='Pedidos de venta origen',
        compute='_compute_traceability_links',
        readonly=True,
    )
    created_picking_ids = fields.Many2many(
        'stock.picking', 'mrp_planning_line_picking_rel', 'planning_line_id', 'picking_id',
        string='Reabastecimientos', copy=False, readonly=True,
    )

    @api.depends(
        'sale_line_ids',
        'sale_line_ids.order_id',
        'sale_line_id',
        'sale_line_id.order_id',
    )
    def _compute_traceability_links(self):
        for line in self:
            source_lines = line.sale_line_ids or line.sale_line_id
            line.source_sale_order_ids = source_lines.mapped('order_id')

    @api.depends(
        'warehouse_detail_ids.stock_qty',
        'warehouse_detail_ids.open_mo_qty',
        'warehouse_detail_ids.warehouse_id',
        'plan_id.warehouse_ids',
    )
    def _compute_stock_warehouse_tooltip(self):
        for line in self:
            details = {
                detail.warehouse_id.id: detail
                for detail in line.warehouse_detail_ids
                if detail.warehouse_id
            }
            warehouses = line.plan_id.warehouse_ids.sorted(
                key=lambda wh: (wh.sequence, wh.name, wh.id)
            )
            values = []
            for warehouse in warehouses:
                detail = details.get(warehouse.id)
                values.append('|'.join([
                    warehouse.display_name,
                    str(detail.on_hand_qty if detail else 0.0),
                    str(detail.incoming_qty if detail else 0.0),
                    str(detail.outgoing_qty if detail else 0.0),
                    str(detail.draft_purchase_qty if detail else 0.0),
                    str(detail.other_plan_supply_qty if detail else 0.0),
                    str(detail.stock_qty if detail else 0.0),
                    str(detail.open_mo_qty if detail else 0.0),
                ]))
            line.stock_warehouse_tooltip = '\n'.join(values) or _('Sin detalle de almacenes')

    @api.depends(
        'sale_line_ids',
        'sale_line_ids.order_id',
        'sale_line_ids.order_id.partner_id',
        'sale_line_ids.order_id.warehouse_id',
        'sale_line_ids.product_uom_qty',
        'sale_line_ids.qty_delivered',
        'sale_line_ids.planning_delivery_date',
    )
    def _compute_sale_order_popover_data(self):
        for line in self:
            source_lines = line.sale_line_ids or line.sale_line_id
            grouped = {}
            for sale_line in source_lines:
                order = sale_line.order_id
                if not order:
                    continue
                row = grouped.setdefault(order.id, {
                    'id': order.id,
                    'name': order.name or '',
                    'customer': order.partner_id.display_name or '',
                    'warehouse': order.warehouse_id.display_name or '',
                    'delivery_date': False,
                    'pending_qty': 0.0,
                })
                pending_sale_uom = max(
                    (sale_line.product_uom_qty or 0.0) - (sale_line.qty_delivered or 0.0),
                    0.0,
                )
                pending_product_uom = sale_line.product_uom_id._compute_quantity(
                    pending_sale_uom,
                    line.product_uom_id,
                ) if line.product_uom_id else pending_sale_uom
                row['pending_qty'] += pending_product_uom
                delivery = sale_line.planning_delivery_date
                if delivery and (not row['delivery_date'] or delivery < row['delivery_date']):
                    row['delivery_date'] = delivery

            rows = []
            for row in sorted(
                grouped.values(),
                key=lambda value: (
                    value['delivery_date'] or fields.Datetime.now(),
                    value['name'],
                ),
            ):
                rows.append({
                    'id': row['id'],
                    'name': row['name'],
                    'customer': row['customer'],
                    'warehouse': row['warehouse'],
                    'delivery_date': fields.Datetime.to_string(row['delivery_date']) if row['delivery_date'] else '',
                    'pending_qty': round(row['pending_qty'], 2),
                })

            line.sale_order_popover_data = json.dumps({
                'count': len(rows),
                'total_pending_qty': round(sum(row['pending_qty'] for row in rows), 2),
                'uom': line.product_uom_id.name or '',
                'orders': rows,
            }, ensure_ascii=False)

    @api.depends('sale_line_ids')
    def _compute_source_counts(self):
        for line in self:
            source_lines = line.sale_line_ids or line.sale_line_id
            line.sale_line_count = len(source_lines)
            line.sale_order_count = len(source_lines.mapped('order_id'))

    @api.depends('action_manufacture', 'action_purchase', 'action_move')
    def _compute_action_type(self):
        for line in self:
            if line.action_manufacture:
                line.action_type = 'manufacture'
            elif line.action_purchase:
                line.action_type = 'purchase'
            elif line.action_move:
                line.action_type = 'move'
            else:
                line.action_type = 'none'

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
            if not self.purchase_vendor_id and self.product_id:
                sellers = self.product_id.with_company(self.plan_id.company_id).seller_ids.filtered(
                    lambda seller: not seller.company_id or seller.company_id == self.plan_id.company_id
                ).sorted(key=lambda seller: (seller.sequence, seller.id))
                self.purchase_vendor_id = sellers[:1].partner_id if sellers else False

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
        return self.env['mrp.planning.stock.availability.wizard'].open_for_line(self)


    def action_create_inventory_move(self):
        self.ensure_one()
        if self.plan_state != 'calculated':
            raise UserError(_(
                'Solo puede generar movimientos mientras la planificación está en estado Calculado.'
            ))
        if not self.action_move:
            raise UserError(_(
                'La línea debe estar seleccionada como Mover para generar una transferencia interna.'
            ))
        if self.created_picking_ids:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Reabastecimientos del producto'),
                'res_model': 'stock.picking',
                'view_mode': 'list,form',
                'views': [(False, 'list'), (False, 'form')],
                'domain': [('id', 'in', self.created_picking_ids.ids)],
                'target': 'current',
            }

        # Revalidate current sales demand before committing stock between warehouses.
        self.plan_id._validate_sale_lines_still_pending()
        pickings = self.plan_id._create_replenishments_for_lines(self)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Reabastecimientos - %s') % self.product_id.display_name,
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', pickings.ids)],
            'target': 'current',
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
    on_hand_qty = fields.Float(string='A mano')
    free_qty = fields.Float(string='Libre')
    incoming_qty = fields.Float(string='Entradas')
    outgoing_qty = fields.Float(string='Salidas')
    draft_purchase_qty = fields.Float(string='RFQ pendientes')
    other_plan_supply_qty = fields.Float(string='Otros planes')
    stock_qty = fields.Float(string='Pronóstico disponible')
    open_mo_qty = fields.Float(string='OF abiertas')
    unforecasted_mo_qty = fields.Float(string='OF no incluida en pronóstico')
    local_shortage_qty = fields.Float(string='Faltante local')
    transferable_excess_qty = fields.Float(string='Excedente movible')


class PlanningExternalWarehouseMove(models.Model):
    _name = 'mrp.planning.external.warehouse.move'
    _description = 'Disponibilidad APS en otros almacenes'
    _order = 'product_id, source_warehouse_id, destination_warehouse_id, id'

    plan_id = fields.Many2one('mrp.planning.plan', required=True, ondelete='cascade', index=True, string='Planificación')
    planning_line_id = fields.Many2one('mrp.planning.plan.line', ondelete='set null', index=True, string='Línea del plan')
    production_component_id = fields.Many2one(
        'mrp.planning.production.component', ondelete='set null', index=True,
        string='Componente de fabricación'
    )
    product_id = fields.Many2one('product.product', required=True, index=True, readonly=True)
    product_uom_id = fields.Many2one(related='product_id.uom_id', readonly=True)
    source_warehouse_id = fields.Many2one('stock.warehouse', string='Desde almacén', required=True, readonly=True)
    destination_warehouse_id = fields.Many2one('stock.warehouse', string='Hacia almacén', required=True, readonly=True)
    source_on_hand_qty = fields.Float(string='A mano origen', readonly=True)
    source_free_qty = fields.Float(string='Libre origen', readonly=True)
    source_forecast_qty = fields.Float(string='Pronóstico origen', readonly=True)
    source_open_mo_qty = fields.Float(string='OF abiertas origen', readonly=True)
    destination_shortage_qty = fields.Float(string='Faltante destino', readonly=True)
    suggested_qty = fields.Float(string='Sugerido mover', readonly=True)
    move_qty = fields.Float(string='Cantidad a transferir')
    picking_id = fields.Many2one('stock.picking', string='Transferencia', readonly=True, copy=False)
    state = fields.Selection([('pending', 'Pendiente'), ('generated', 'Transferencia creada')], default='pending', required=True, readonly=True, index=True)

    @api.constrains('move_qty')
    def _check_move_qty(self):
        for record in self:
            if record.move_qty < 0:
                raise ValidationError(_('La cantidad a transferir no puede ser negativa.'))
            if record.suggested_qty and record.move_qty - record.suggested_qty > 1e-6:
                raise ValidationError(_('La cantidad a transferir no puede superar lo sugerido (%.2f).') % record.suggested_qty)

    def action_create_transfer(self):
        self.ensure_one()
        if self.state == 'generated' and self.picking_id:
            return self.action_open_transfer()
        if self.plan_id.state != 'calculated':
            raise UserError(_('Solo puede transferir desde una planificación calculada.'))
        if self.move_qty <= 1e-6:
            raise UserError(_('Ingrese una cantidad mayor que cero para transferir.'))
        if self.source_warehouse_id == self.destination_warehouse_id:
            raise UserError(_('El almacén origen y destino deben ser diferentes.'))

        from ..services.internal_stock import InternalWarehouseStock
        stock_now = InternalWarehouseStock(
            self.env, self.plan_id.company_id
        ).quantities(self.product_id, self.source_warehouse_id)
        free_now = stock_now[
            (self.product_id.id, self.source_warehouse_id.id)
        ]['free']
        if free_now + 1e-6 < self.move_qty:
            raise UserError(_('El almacén %s ya no dispone de %.2f unidades libres de %s. Disponible actualmente: %.2f. Recalcule la planificación.') % (
                self.source_warehouse_id.display_name, self.move_qty, self.product_id.display_name, free_now,
            ))

        picking_type = self.source_warehouse_id.int_type_id
        if not picking_type:
            raise UserError(_('El almacén %s no tiene un tipo de operación interna configurado.') % self.source_warehouse_id.display_name)

        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': self.source_warehouse_id.lot_stock_id.id,
            'location_dest_id': self.destination_warehouse_id.lot_stock_id.id,
            'origin': '%s - %s' % (self.plan_id.name, self.product_id.display_name),
            'company_id': self.plan_id.company_id.id,
            'advanced_plan_id': self.plan_id.id,
        })
        # Odoo 19 removed the legacy stock.move `name` field.  The
        # description/reference belongs to the picking (`origin` above).
        # Keep move values strictly aligned with the Odoo 19 stock.move API.
        move_vals = {
            'product_id': self.product_id.id,
            'product_uom_qty': self.move_qty,
            'product_uom': self.product_uom_id.id,
            'location_id': self.source_warehouse_id.lot_stock_id.id,
            'location_dest_id': self.destination_warehouse_id.lot_stock_id.id,
            'picking_id': picking.id,
            'company_id': self.plan_id.company_id.id,
        }
        if self.planning_line_id:
            move_vals['planning_plan_line_id'] = self.planning_line_id.id
        self.env['stock.move'].create(move_vals)
        picking.action_confirm()
        picking.action_assign()
        self.write({'picking_id': picking.id, 'state': 'generated'})
        self.plan_id.write({'needs_recalculation': True})
        self.plan_id.message_post(body=_('Transferencia interna creada para %s: %.2f %s desde %s hacia %s. Recalcule la planificación antes de generar nuevas compras u órdenes de fabricación.') % (
            self.product_id.display_name, self.move_qty, self.product_uom_id.name or '',
            self.source_warehouse_id.display_name, self.destination_warehouse_id.display_name,
        ))
        return self.action_open_transfer()

    def action_open_transfer(self):
        self.ensure_one()
        if not self.picking_id:
            return False
        return {
            'type': 'ir.actions.act_window', 'name': _('Transferencia interna'),
            'res_model': 'stock.picking', 'res_id': self.picking_id.id,
            'view_mode': 'form', 'views': [(False, 'form')], 'target': 'current',
        }


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
    parent_line_id = fields.Many2one(
        'mrp.planning.requirement', string='Línea padre',
        ondelete='cascade', index=True,
    )
    child_line_ids = fields.One2many(
        'mrp.planning.requirement', 'parent_line_id', string='Subcomponentes'
    )
    product_id = fields.Many2one('product.product', required=True, index=True)
    root_product_id = fields.Many2one('product.product', string='Producto fabricado', index=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Almacén', index=True)
    source_plan_name = fields.Char(string='Planificación de fabricación')
    path = fields.Char(string='Ruta de LdM')
    bom_id = fields.Many2one('mrp.bom')
    bom_line_id = fields.Many2one('mrp.bom.line')
    level = fields.Integer(default=0)
    required_qty = fields.Float(required=True)
    available_qty = fields.Float()
    net_qty = fields.Float()
    date_required = fields.Datetime(index=True)
    supply_type = fields.Selection([('available', 'Available'), ('existing', 'Existing Supply'), ('make', 'Make'), ('buy', 'Buy'), ('blocked', 'Blocked')], default='blocked')
    hierarchy_label = fields.Char(string='Jerarquía', compute='_compute_hierarchy_label')

    @api.depends('level', 'product_id')
    def _compute_hierarchy_label(self):
        for line in self:
            prefix = '   ' * max((line.level or 1) - 1, 0)
            line.hierarchy_label = '%s↳ %s' % (
                prefix, line.product_id.display_name or ''
            )



class PlanningProductionComponent(models.Model):
    _name = 'mrp.planning.production.component'
    _description = 'Componente congelado de fabricación APS'
    _order = 'planning_line_id, sequence, level, id'

    plan_id = fields.Many2one('mrp.planning.plan', required=True, ondelete='cascade', index=True)
    planning_line_id = fields.Many2one(
        'mrp.planning.plan.line', required=True, ondelete='cascade', index=True,
        string='Línea de planificación',
    )
    parent_line_id = fields.Many2one(
        'mrp.planning.production.component', string='Componente padre',
        ondelete='cascade', index=True,
    )
    child_line_ids = fields.One2many(
        'mrp.planning.production.component', 'parent_line_id',
        string='Subcomponentes',
    )
    parent_product_id = fields.Many2one(
        related='parent_line_id.product_id',
        string='Componente padre',
        readonly=True,
    )
    root_product_display_id = fields.Many2one(
        related='planning_line_id.product_id',
        string='Producto terminado',
        readonly=True,
    )
    root_product_id = fields.Many2one('product.product', required=True, index=True)
    product_id = fields.Many2one('product.product', required=True, index=True, string='Componente')
    product_tracking = fields.Selection(
        related='product_id.tracking',
        string='Seguimiento',
        readonly=True,
    )
    original_product_id = fields.Many2one(
        'product.product', required=True, index=True, string='Componente ingeniería',
    )
    product_uom_id = fields.Many2one('uom.uom', required=True, string='UdM')
    original_qty = fields.Float(string='Cantidad ingeniería', digits='Product Unit of Measure')
    planned_qty = fields.Float(string='Cantidad planificada', digits='Product Unit of Measure', required=True)
    level = fields.Integer(required=True, default=1, index=True)
    sequence = fields.Integer(default=10)
    path = fields.Char(string='Ruta', readonly=True)
    source_bom_id = fields.Many2one('mrp.bom', string='LdM origen', readonly=True)
    source_bom_line_id = fields.Many2one('mrp.bom.line', string='Línea LdM origen', readonly=True)
    is_subcontracted = fields.Boolean(
        string='Subcontratación', readonly=True, copy=False, index=True
    )
    subcontract_bom_id = fields.Many2one(
        'mrp.bom', string='LdM de subcontratación',
        readonly=True, copy=False, ondelete='set null'
    )
    change_type = fields.Selection([
        ('original', 'Original'),
        ('modified', 'Modificado'),
        ('replaced', 'Sustituido'),
        ('manual', 'Agregado manualmente'),
        ('omitted', 'Omitido'),
    ], string='Cambio', default='original', required=True, index=True)
    include_in_mo = fields.Boolean(string='Incluir en OF', default=True)
    note = fields.Char(string='Observación')
    availability_qty = fields.Float(
        string='Disponible total', compute='_compute_availability', digits='Product Unit of Measure'
    )
    availability_need_qty = fields.Float(
        string='Necesidad neta', compute='_compute_availability', digits='Product Unit of Measure'
    )
    availability_status = fields.Selection([
        ('pending', 'Seleccione componente'),
        ('sufficient', 'Suficiente'),
        ('partial', 'Parcial'),
        ('none', 'Sin disponibilidad'),
    ], string='Disponibilidad', compute='_compute_availability')
    availability_label = fields.Char(
        string='Estado disponibilidad', compute='_compute_availability'
    )

    effective_required_qty = fields.Float(
        string='Necesidad efectiva', digits='Product Unit of Measure', readonly=True, copy=False
    )
    local_supply_qty = fields.Float(
        string='Cobertura local', digits='Product Unit of Measure', readonly=True, copy=False
    )
    external_move_suggested_qty = fields.Float(
        string='Movible desde otras bodegas', digits='Product Unit of Measure', readonly=True, copy=False
    )
    to_manufacture_qty = fields.Float(
        string='A fabricar', digits='Product Unit of Measure', readonly=True, copy=False
    )
    to_purchase_qty = fields.Float(
        string='A comprar', digits='Product Unit of Measure', readonly=True, copy=False
    )
    supply_resolution = fields.Selection([
        ('not_required', 'No requerido'),
        ('available', 'Disponible'),
        ('move', 'Mover'),
        ('manufacture', 'Fabricar'),
        ('purchase', 'Comprar'),
        ('move_manufacture', 'Mover + Fabricar'),
        ('move_purchase', 'Mover + Comprar'),
        ('subcontract', 'Subcontratación'),
        ('move_subcontract', 'Mover + Subcontratación'),
        ('review', 'Revisar'),
    ], string='Resolución', default='not_required', readonly=True, copy=False, index=True)
    generated_production_id = fields.Many2one(
        'mrp.production', string='OF de componente', readonly=True, copy=False, ondelete='set null'
    )
    engineering_locked = fields.Boolean(
        string='Ingeniería bloqueada',
        compute='_compute_engineering_locked',
        readonly=True,
    )
    generated_purchase_plan_line_id = fields.Many2one(
        'mrp.planning.plan.line', string='Línea de compra generada',
        readonly=True, copy=False, ondelete='set null'
    )
    external_move_ids = fields.One2many(
        'mrp.planning.external.warehouse.move', 'production_component_id',
        string='Traslados sugeridos', copy=False
    )
    lot_reservation_ids = fields.One2many(
        'mrp.planning.component.lot.reservation',
        'component_id',
        string='Lotes reservados',
        copy=False,
    )
    reserved_lot_qty = fields.Float(
        string='Cantidad en lotes APS',
        compute='_compute_lot_reservation_summary',
        digits='Product Unit of Measure',
    )
    lot_reservation_count = fields.Integer(
        string='Lotes', compute='_compute_lot_reservation_summary'
    )
    pending_lot_qty = fields.Float(
        string='Pendiente de reservar',
        compute='_compute_lot_reservation_summary',
        digits='Product Unit of Measure',
    )
    lot_coverage_percent = fields.Float(
        string='Cobertura de lotes (%)',
        compute='_compute_lot_reservation_summary',
    )
    lot_reservation_status = fields.Selection([
        ('not_tracked', 'Sin seguimiento'),
        ('none', 'Sin lotes disponibles'),
        ('pending_supply', 'Pendiente de abastecimiento'),
        ('partial', 'Reserva parcial'),
        ('reserved', 'Reservado'),
        ('locked', 'Asignado a OF'),
    ], string='Reserva de lotes', compute='_compute_lot_reservation_summary')

    hierarchy_label = fields.Char(
        string='Jerarquía', compute='_compute_hierarchy_label'
    )

    @api.depends(
        'lot_reservation_ids.reserved_qty',
        'lot_reservation_ids.state',
        'product_id.tracking',
        'engineering_locked',
        'effective_required_qty',
        'planned_qty',
    )
    def _compute_lot_reservation_summary(self):
        for component in self:
            active = component.lot_reservation_ids.filtered(
                lambda reservation:
                    reservation.state in ('reserved', 'assigned')
            )
            target_qty = max(
                component.effective_required_qty or component.planned_qty,
                0.0,
            )
            qty = sum(active.mapped('reserved_qty'))
            pending = max(target_qty - qty, 0.0)
            coverage = (
                min((qty / target_qty) * 100.0, 100.0)
                if target_qty > 1e-6
                else 100.0
            )

            component.reserved_lot_qty = qty
            component.pending_lot_qty = pending
            component.lot_coverage_percent = coverage
            component.lot_reservation_count = len(active)

            if component.product_id.tracking == 'none':
                status = 'not_tracked'
            elif pending <= 1e-6 and active:
                status = 'locked' if component.engineering_locked else 'reserved'
            elif qty > 1e-6:
                status = 'partial'
            elif target_qty > 1e-6:
                status = 'pending_supply'
            else:
                status = 'none'
            component.lot_reservation_status = status

    def _aps_has_complete_lot_reservation(self):
        self.ensure_one()
        if self.product_id.tracking == 'none':
            return True
        required = max(
            self.effective_required_qty or self.planned_qty,
            0.0,
        )
        reserved = sum(
            self.lot_reservation_ids.filtered(
                lambda reservation:
                    reservation.state in ('reserved', 'assigned')
            ).mapped('reserved_qty')
        )
        return reserved + 1e-6 >= required


    def _aps_lot_free_rows(self):
        """Available lot quantities in the component destination warehouse.

        Lots actively reserved by another APS component are excluded entirely.
        This intentionally makes a lot exclusive to one APS demand.
        """
        self.ensure_one()
        if not self.product_id or self.product_id.tracking == 'none':
            return []

        warehouse = (
            self.planning_line_id.target_warehouse_id
            or self.plan_id.warehouse_ids[:1]
        )
        if not warehouse:
            return []

        locations = self.env['stock.location'].sudo().search([
            ('id', 'child_of', warehouse.view_location_id.id),
            ('usage', '=', 'internal'),
            ('company_id', 'in', [False, self.plan_id.company_id.id]),
        ])
        quants = self.env['stock.quant'].sudo().search([
            ('product_id', '=', self.product_id.id),
            ('lot_id', '!=', False),
            ('location_id', 'in', locations.ids),
            ('quantity', '>', 0),
        ])

        reserved_elsewhere = set(
            self.env['mrp.planning.component.lot.reservation'].sudo().search([
                ('component_id', '!=', self.id),
                ('state', 'in', ('reserved', 'assigned')),
                ('lot_id', 'in', quants.mapped('lot_id').ids),
            ]).mapped('lot_id').ids
        )

        free_by_lot = {}
        for quant in quants:
            lot = quant.lot_id
            if lot.id in reserved_elsewhere:
                continue
            free = max(
                (quant.quantity or 0.0)
                - (getattr(quant, 'reserved_quantity', 0.0) or 0.0),
                0.0,
            )
            if free <= 1e-6:
                continue
            free_by_lot[lot.id] = free_by_lot.get(lot.id, 0.0) + free

        lots = self.env['stock.lot'].browse(list(free_by_lot))
        def lot_order(lot):
            removal = (
                getattr(lot, 'removal_date', False)
                or getattr(lot, 'expiration_date', False)
                or fields.Datetime.to_datetime('9999-12-31 00:00:00')
            )
            return (removal, lot.name or '', lot.id)

        return [
            (lot, free_by_lot[lot.id], warehouse)
            for lot in sorted(lots, key=lot_order)
        ]

    def _aps_sync_default_lot_reservations(self):
        Reservation = self.env[
            'mrp.planning.component.lot.reservation'
        ].sudo()
        for component in self:
            if (
                component.engineering_locked
                or not component.include_in_mo
                or not component.product_id
                or component.product_id.tracking == 'none'
            ):
                continue

            active = component.lot_reservation_ids.filtered(
                lambda reservation:
                    reservation.state in ('reserved', 'assigned')
            )
            target_qty = max(
                component.effective_required_qty or component.planned_qty,
                0.0,
            )
            current_qty = sum(active.mapped('reserved_qty'))
            missing = max(target_qty - current_qty, 0.0)
            if missing <= 1e-6:
                continue

            existing_lots = set(active.mapped('lot_id').ids)
            for lot, free_qty, warehouse in component._aps_lot_free_rows():
                if lot.id in existing_lots or missing <= 1e-6:
                    continue
                qty = min(free_qty, missing)
                Reservation.create({
                    'plan_id': component.plan_id.id,
                    'planning_line_id': component.planning_line_id.id,
                    'component_id': component.id,
                    'warehouse_id': warehouse.id,
                    'lot_id': lot.id,
                    'reserved_qty': qty,
                })
                existing_lots.add(lot.id)
                missing -= qty
        return True

    def action_open_lot_reservations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Lotes reservados - %s') % self.product_id.display_name,
            'res_model': 'mrp.planning.component.lot.reservation',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('component_id', '=', self.id)],
            'context': {
                'default_plan_id': self.plan_id.id,
                'default_planning_line_id': self.planning_line_id.id,
                'default_component_id': self.id,
                'default_warehouse_id': (
                    self.planning_line_id.target_warehouse_id.id
                    or self.plan_id.warehouse_ids[:1].id
                ),
            },
            'target': 'new',
        }

    def action_complete_lot_reservations(self):
        for component in self:
            self.env[
                'mrp.planning.component.lot.reservation'
            ].sudo()._aps_auto_complete_pending_for_products(
                component.product_id,
                warehouse=(
                    component.planning_line_id.target_warehouse_id
                    or component.plan_id.warehouse_ids[:1]
                ),
            )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reserva de lotes actualizada'),
                'message': _(
                    'APS volvió a buscar lotes físicos disponibles para '
                    'completar las reservas pendientes.'
                ),
                'type': 'success',
                'sticky': False,
            },
        }


    @api.depends(
        'generated_production_id',
        'planning_line_id.created_production_id',
    )
    def _compute_engineering_locked(self):
        for component in self:
            component.engineering_locked = bool(
                component.generated_production_id
                or component.planning_line_id.created_production_id
            )

    @api.depends('level', 'product_id')
    def _compute_hierarchy_label(self):
        for line in self:
            prefix = '   ' * max((line.level or 1) - 1, 0)
            line.hierarchy_label = '%s↳ %s' % (
                prefix, line.product_id.display_name or ''
            )


    @api.onchange('product_id')
    def _onchange_product_uom_aps(self):
        for line in self:
            if line.product_id:
                line.product_uom_id = line.product_id.uom_id

    def _aps_engineering_change_type(self):
        self.ensure_one()
        if not self.include_in_mo:
            return 'omitted'
        if (
            self.original_product_id
            and self.product_id != self.original_product_id
        ):
            return 'replaced'
        if (
            self.source_bom_line_id
            and abs(
                (self.planned_qty or 0.0)
                - (self.original_qty or 0.0)
            ) > 1e-6
        ):
            return 'modified'
        if not self.source_bom_line_id:
            return 'manual'
        return 'original'

    @api.onchange('product_id', 'planned_qty', 'include_in_mo')
    def _onchange_track_engineering_change(self):
        for line in self:
            line.change_type = line._aps_engineering_change_type()


    @api.depends(
        'product_id',
        'planned_qty',
        'include_in_mo',
        'plan_id.warehouse_ids',
        'plan_id.date_end',
        'effective_required_qty',
        'local_supply_qty',
        'supply_resolution',
    )
    def _compute_availability(self):
        """Batch availability for the component tree.

        Uses only warehouses selected on the plan:
        free stock + confirmed PO pending receipt within the plan horizon.
        """
        for line in self:
            line.availability_qty = 0.0
            line.availability_need_qty = max(line.planned_qty, 0.0)
            if not line.product_id:
                line.availability_status = 'pending'
                line.availability_label = 'Seleccione componente'
            else:
                line.availability_status = 'none'
                line.availability_label = 'Sin disponibilidad'

        classified = self.filtered(
            lambda line: line.include_in_mo
            and (
                line.effective_required_qty > 1e-6
                or line.supply_resolution != 'not_required'
            )
        )
        for line in classified:
            required = line.effective_required_qty
            available = min(line.local_supply_qty, required) if required > 0 else 0.0
            need = max(required - available, 0.0)
            if required <= 1e-6 or available + 1e-6 >= required:
                status = 'sufficient'
                label = 'Suficiente'
            elif available > 1e-6:
                status = 'partial'
                label = 'Parcial'
            else:
                status = 'none'
                label = 'Sin disponibilidad'
            line.availability_qty = available
            line.availability_need_qty = need
            line.availability_status = status
            line.availability_label = '%s (%.2f)' % (label, available)

        lines = (self - classified).filtered(
            lambda line: line.product_id
            and line.plan_id
            and line.include_in_mo
            and line.planned_qty > 1e-6
        )
        if not lines:
            return

        PurchaseLine = self.env['purchase.order.line'].sudo()
        for plan in lines.mapped('plan_id'):
            plan_lines = lines.filtered(lambda line: line.plan_id == plan)
            products = plan_lines.mapped('product_id')
            warehouses = plan.warehouse_ids
            available_by_product = {product.id: 0.0 for product in products}

            # Explicit APS rule: only free stock in internal locations
            # belonging to the warehouses selected on the plan.
            from ..services.internal_stock import InternalWarehouseStock
            stock_rows = InternalWarehouseStock(
                self.env, plan.company_id
            ).quantities(products, warehouses)
            for product in products:
                for warehouse in warehouses:
                    available_by_product[product.id] += (
                        stock_rows[(product.id, warehouse.id)]['free']
                    )

            # Confirmed purchase orders in transit within the planning horizon.
            po_lines = PurchaseLine.search([
                ('company_id', '=', plan.company_id.id),
                ('product_id', 'in', products.ids),
                ('order_id.state', '=', 'purchase'),
                ('order_id.picking_type_id.warehouse_id', 'in', warehouses.ids),
                ('date_planned', '<=', plan.date_end),
            ])
            for po_line in po_lines:
                pending = max(
                    (po_line.product_qty or 0.0) - (po_line.qty_received or 0.0),
                    0.0,
                )
                if pending <= 1e-6:
                    continue
                available_by_product[po_line.product_id.id] += (
                    po_line.product_uom_id._compute_quantity(
                        pending, po_line.product_id.uom_id
                    )
                )

            for line in plan_lines:
                available = max(available_by_product.get(line.product_id.id, 0.0), 0.0)
                need = max((line.planned_qty or 0.0) - available, 0.0)
                if available + 1e-6 >= line.planned_qty:
                    status = 'sufficient'
                    label = 'Suficiente'
                elif available > 1e-6:
                    status = 'partial'
                    label = 'Parcial'
                else:
                    status = 'none'
                    label = 'Sin disponibilidad'
                line.availability_qty = available
                line.availability_need_qty = need
                line.availability_status = status
                line.availability_label = '%s (%.2f)' % (label, available)

    def unlink(self):
        records = self.exists()
        if not records:
            return True
        if records.filtered(
            lambda component:
                component.generated_production_id
                or component.planning_line_id.created_production_id
        ):
            raise UserError(_(
                'No puede eliminar componentes después de generar las órdenes de fabricación.'
            ))
        plans = records.mapped('plan_id')
        subtree = records
        frontier = records
        while frontier:
            children = frontier.mapped('child_line_ids') - subtree
            if not children:
                break
            subtree |= children
            frontier = children
        subtree.mapped('external_move_ids').filtered(
            lambda move: move.state == 'pending'
        ).unlink()
        result = super().unlink()
        if not self.env.context.get('aps_skip_sourcing_refresh'):
            for plan in plans.filtered(
                lambda plan:
                    plan.plan_type == 'manufacturing'
                    and plan.state == 'calculated'
            ):
                plan._refresh_component_sourcing()
        return result

    @api.model
    def action_delete_component_by_id(self, component_id):
        component = self.browse(component_id).exists()
        if not component:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Árbol actualizado',
                    'message': 'El componente ya no existe.',
                    'type': 'warning',
                    'sticky': False,
                },
            }
        component.unlink()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Componente eliminado',
                'message': 'El componente y sus descendientes se eliminaron del snapshot APS.',
                'type': 'success',
                'sticky': False,
            },
        }

    @api.model
    def action_open_edit_component_by_id(self, component_id):
        component = self.browse(component_id).exists()
        if not component:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Componente actualizado',
                    'message': 'La línea ya no existe porque la planificación fue recalculada. Actualice el árbol.',
                    'type': 'warning',
                    'sticky': False,
                },
            }
        return component.action_open_edit_component()

    @api.model
    def action_open_availability_by_id(self, component_id):
        component = self.browse(component_id).exists()
        if not component:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Componente actualizado',
                    'message': 'La línea ya no existe porque la planificación fue recalculada. Actualice el árbol.',
                    'type': 'warning',
                    'sticky': False,
                },
            }
        return component.action_open_availability()

    def action_open_edit_component(self):
        self.ensure_one()
        view = self.env.ref('mrp_advanced_planner.view_mrp_planning_production_component_form')
        context = dict(self.env.context)
        context['aps_component_locked'] = self.engineering_locked
        return {
            'type': 'ir.actions.act_window',
            'name': (
                'Consultar componente'
                if self.engineering_locked
                else 'Editar / sustituir componente'
            ),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'target': 'new',
            'context': context,
        }

    def action_open_availability(self):
        self.ensure_one()
        return self.env['mrp.planning.stock.availability.wizard'].open_for_component(self)


    def write(self, vals):
        product_changed = 'product_id' in vals
        engineering_fields = {
            'product_id',
            'planned_qty',
            'product_uom_id',
            'include_in_mo',
            'note',
            'parent_line_id',
            'sequence',
        }
        engineering_changed = bool(engineering_fields & set(vals))
        if (
            engineering_changed
            and not self.env.context.get('aps_allow_locked_engineering_write')
            and self.filtered('engineering_locked')
        ):
            raise UserError(_(
                'La ingeniería de esta línea está bloqueada porque ya se '
                'generó una Orden de Fabricación. Los componentes del '
                'planificador quedan congelados desde ese momento.'
            ))
        result = super().write(vals)

        if (
            engineering_changed
            and not self.env.context.get('aps_skip_change_tracking')
        ):
            for component in self:
                change_type = component._aps_engineering_change_type()
                if component.change_type != change_type:
                    super(
                        PlanningProductionComponent,
                        component.with_context(aps_skip_change_tracking=True),
                    ).write({'change_type': change_type})

        if (
            product_changed
            and not self.env.context.get('aps_skip_subtree_rebuild')
        ):
            from ..services.manufacturing_snapshot import ManufacturingSnapshotBuilder
            for component in self:
                if component.plan_id.plan_type == 'manufacturing':
                    ManufacturingSnapshotBuilder(
                        component.plan_id
                    ).rebuild_component_subtree(component)
        if (
            engineering_changed
            and not self.env.context.get('aps_skip_sourcing_refresh')
        ):
            for plan in self.mapped('plan_id').filtered(
                lambda plan:
                    plan.plan_type == 'manufacturing'
                    and plan.state == 'calculated'
            ):
                plan._refresh_component_sourcing()
        return result

    @api.model_create_multi
    def create(self, vals_list):
        manual_flags = []
        PlanningLine = self.env['mrp.planning.plan.line']
        for vals in vals_list:
            planning_line = PlanningLine.browse(
                vals.get('planning_line_id')
            ).exists()
            if (
                planning_line
                and planning_line.created_production_id
                and not self.env.context.get(
                    'aps_allow_locked_engineering_write'
                )
            ):
                raise UserError(_(
                    'No puede agregar componentes: la Orden de Fabricación %s '
                    'ya fue generada para esta línea del plan.'
                ) % planning_line.created_production_id.display_name)

            is_manual = not vals.get('source_bom_line_id')
            manual_flags.append(is_manual)
            if is_manual:
                vals.setdefault('change_type', 'manual')
                vals.setdefault('original_product_id', vals.get('product_id'))
                vals.setdefault('original_qty', vals.get('planned_qty', 0.0))
        records = super().create(vals_list)
        if not self.env.context.get('aps_skip_subtree_rebuild'):
            from ..services.manufacturing_snapshot import ManufacturingSnapshotBuilder
            for record, is_manual in zip(records, manual_flags):
                if (
                    is_manual
                    and record.product_id
                    and record.plan_id.plan_type == 'manufacturing'
                ):
                    ManufacturingSnapshotBuilder(
                        record.plan_id
                    ).rebuild_component_subtree(record)
        if (
            any(manual_flags)
            and not self.env.context.get('aps_skip_sourcing_refresh')
        ):
            for plan in records.mapped('plan_id').filtered(
                lambda plan:
                    plan.plan_type == 'manufacturing'
                    and plan.state == 'calculated'
            ):
                plan._refresh_component_sourcing()
        return records
