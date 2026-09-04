from collections import defaultdict

from odoo import api, fields, models


class PlanningStockAvailabilityWizard(models.TransientModel):
    _name = 'mrp.planning.stock.availability.wizard'
    _description = 'Disponibilidad temporal por almacén'

    planning_line_id = fields.Many2one('mrp.planning.plan.line', readonly=True)
    production_component_id = fields.Many2one(
        'mrp.planning.production.component', readonly=True
    )
    product_id = fields.Many2one('product.product', required=True, readonly=True)
    required_qty = fields.Float(string='Necesidad total', readonly=True, digits=(16, 4))
    total_available_qty = fields.Float(string='Disponible total', readonly=True, digits=(16, 4))
    net_need_qty = fields.Float(string='Necesidad neta', readonly=True, digits=(16, 4))
    availability_status = fields.Selection([
        ('sufficient', 'Suficiente'),
        ('partial', 'Parcial'),
        ('none', 'Insuficiente'),
    ], string='Estado', readonly=True)
    line_ids = fields.One2many(
        'mrp.planning.stock.availability.wizard.line', 'wizard_id', readonly=True
    )

    @api.model
    def _warehouse_values(self, plan, product, required_qty):
        PurchaseLine = self.env['purchase.order.line'].sudo()
        values = []
        total_available = 0.0

        from ..services.internal_stock import InternalWarehouseStock
        stock_rows = InternalWarehouseStock(
            self.env, plan.company_id
        ).quantities(product, plan.warehouse_ids)

        for warehouse in plan.warehouse_ids:
            stock = stock_rows[(product.id, warehouse.id)]
            on_hand = stock['on_hand']
            reserved = stock['reserved']
            free = stock['free']

            po_lines = PurchaseLine.search([
                ('company_id', '=', plan.company_id.id),
                ('product_id', '=', product.id),
                ('order_id.state', '=', 'purchase'),
                ('order_id.picking_type_id.warehouse_id', '=', warehouse.id),
                ('date_planned', '<=', plan.date_end),
            ])
            incoming = 0.0
            for po_line in po_lines:
                pending = max(
                    (po_line.product_qty or 0.0) - (po_line.qty_received or 0.0),
                    0.0,
                )
                incoming += po_line.product_uom_id._compute_quantity(
                    pending, product.uom_id
                )

            total = free + incoming
            total_available += total
            if total + 1e-6 >= required_qty:
                state = 'sufficient'
            elif total > 1e-6:
                state = 'partial'
            else:
                state = 'none'

            values.append((0, 0, {
                'warehouse_id': warehouse.id,
                'on_hand_qty': on_hand,
                'reserved_qty': reserved,
                'available_qty': free,
                'confirmed_po_qty': incoming,
                'available_with_incoming_qty': total,
                'availability_status': state,
            }))
        return values, total_available

    @api.model
    def open_for_line(self, planning_line):
        plan = planning_line.plan_id
        required = planning_line.planner_production_qty or planning_line.net_requirement_qty
        values, total = self._warehouse_values(
            plan, planning_line.product_id, required
        )
        status = (
            'sufficient' if total + 1e-6 >= required
            else 'partial' if total > 1e-6
            else 'none'
        )
        wizard = self.create({
            'planning_line_id': planning_line.id,
            'product_id': planning_line.product_id.id,
            'required_qty': required,
            'total_available_qty': total,
            'net_need_qty': max(required - total, 0.0),
            'availability_status': status,
            'line_ids': values,
        })
        view = self.env.ref(
            'mrp_advanced_planner.view_mrp_planning_stock_availability_wizard_form'
        )
        return {
            'type': 'ir.actions.act_window',
            'name': 'Disponibilidad por bodega',
            'res_model': self._name,
            'res_id': wizard.id,
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'target': 'new',
            'context': dict(self.env.context),
        }

    @api.model
    def open_for_component(self, component):
        plan = component.plan_id
        required = component.planned_qty if component.include_in_mo else 0.0
        values, total = self._warehouse_values(
            plan, component.product_id, required
        )
        status = (
            'sufficient' if total + 1e-6 >= required
            else 'partial' if total > 1e-6
            else 'none'
        )
        wizard = self.create({
            'production_component_id': component.id,
            'product_id': component.product_id.id,
            'required_qty': required,
            'total_available_qty': total,
            'net_need_qty': max(required - total, 0.0),
            'availability_status': status,
            'line_ids': values,
        })
        view = self.env.ref(
            'mrp_advanced_planner.view_mrp_planning_stock_availability_wizard_form'
        )
        return {
            'type': 'ir.actions.act_window',
            'name': 'Disponibilidad por bodega',
            'res_model': self._name,
            'res_id': wizard.id,
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'target': 'new',
            'context': dict(self.env.context),
        }



class PlanningStockAvailabilityWizardLine(models.TransientModel):
    _name = 'mrp.planning.stock.availability.wizard.line'
    _description = 'Detalle temporal de disponibilidad'

    wizard_id = fields.Many2one(
        'mrp.planning.stock.availability.wizard', required=True, ondelete='cascade'
    )
    warehouse_id = fields.Many2one('stock.warehouse', required=True, readonly=True)
    on_hand_qty = fields.Float(string='A mano', readonly=True, digits=(16, 4))
    reserved_qty = fields.Float(string='Reservado', readonly=True, digits=(16, 4))
    available_qty = fields.Float(string='Disponible', readonly=True, digits=(16, 4))
    confirmed_po_qty = fields.Float(string='PO confirmadas en tránsito', readonly=True, digits=(16, 4))
    available_with_incoming_qty = fields.Float(string='Disponible + tránsito', readonly=True, digits=(16, 4))
    availability_status = fields.Selection([
        ('sufficient', 'Suficiente'),
        ('partial', 'Parcial'),
        ('none', 'Insuficiente'),
    ], string='Estado', readonly=True)

