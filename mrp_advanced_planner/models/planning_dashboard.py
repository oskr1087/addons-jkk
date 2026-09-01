from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import AccessError


class PlanningDashboard(models.AbstractModel):
    _name = 'mrp.planning.dashboard'
    _description = 'Panel de planificación y abastecimiento'

    @api.model
    def get_data(self, plan_id=False, company_id=False, warehouse_id=False, date_start=False, date_end=False):
        company_id = company_id or self.env.company.id
        Plan = self.env['mrp.planning.plan']
        user = self.env.user

        is_admin = user.has_group('mrp_advanced_planner.group_planner_manager')
        can_manufacturing = user.has_group('mrp_advanced_planner.group_planner_manufacturing_user')
        can_purchase = user.has_group('mrp_advanced_planner.group_planner_purchase_user')

        allowed_types = []
        if can_manufacturing:
            allowed_types.append('manufacturing')
        if can_purchase:
            allowed_types.append('purchase')

        domain = [
            ('company_id', '=', company_id),
            ('state', 'in', ('calculated', 'approved')),
            ('plan_type', 'in', allowed_types),
        ]

        plans = Plan.search(domain, order='date_end desc, id desc', limit=30)

        # Administrator defaults to a combined view. If a concrete plan is chosen,
        # the dashboard focuses on that plan only.
        selected_plan = False
        scoped_plans = plans
        combined_admin_view = bool(is_admin and not plan_id)

        if plan_id:
            selected_plan = Plan.browse(int(plan_id)).exists()
            if (
                not selected_plan
                or selected_plan.company_id.id != company_id
                or selected_plan.plan_type not in allowed_types
                or selected_plan.state not in ('calculated', 'approved')
            ):
                selected_plan = False
            scoped_plans = selected_plan if selected_plan else Plan
        elif not is_admin:
            selected_plan = plans[:1]
            scoped_plans = selected_plan if selected_plan else Plan

        manufacturing_plans = scoped_plans.filtered(lambda p: p.plan_type == 'manufacturing')
        purchase_plans = scoped_plans.filtered(lambda p: p.plan_type == 'purchase')

        show_manufacturing = bool(can_manufacturing and manufacturing_plans)
        show_purchase = bool(can_purchase and purchase_plans)

        lines = scoped_plans.mapped('line_ids') if scoped_plans else self.env['mrp.planning.plan.line']
        active_lines = lines.filtered(lambda l: l.planner_production_qty > 0)

        forecast_products = []
        for line in active_lines.sorted(
            key=lambda l: (l.date_required or l.plan_id.date_end, l.product_id.display_name, l.id)
        ):
            forecast_products.append({
                'id': line.id,
                'plan_id': line.plan_id.id,
                'plan': line.plan_id.name,
                'plan_type': line.plan_id.plan_type,
                'product': line.product_id.display_name,
                'product_id': line.product_id.id,
                'delivery_date': fields.Datetime.to_string(line.date_required) if line.date_required else '',
                'orders': line.sale_order_count,
                'sale_lines': line.sale_line_count,
                'sales_qty': round(line.sales_qty, 2),
                'stock_qty': round(line.stock_qty, 2),
                'manufacturing_qty': round(line.production_qty, 2),
                'suggested_qty': round(line.net_requirement_qty, 2),
                'move_suggested_qty': round(line.move_suggested_qty, 2),
                'planner_qty': round(line.planner_production_qty, 2),
                'action': (
                    'manufacture' if line.action_manufacture
                    else 'purchase' if line.action_purchase
                    else 'move' if line.action_move
                    else 'none'
                ),
                'action_label': line.action_label,
                'warehouse': line.target_warehouse_id.display_name if line.target_warehouse_id else '',
                'uom': line.product_uom_id.name or '',
                'has_bom': bool(line.bom_id),
            })

        Production = self.env['mrp.production']
        productions = Production
        if manufacturing_plans:
            productions = Production.search([
                ('advanced_plan_id', 'in', manufacturing_plans.ids),
                ('state', '!=', 'cancel'),
            ])

        state_labels = dict(Production._fields['state'].selection)
        state_data = defaultdict(lambda: {'count': 0, 'qty': 0.0, 'remaining_qty': 0.0})
        for mo in productions:
            qty = mo.product_qty or 0.0
            produced = getattr(mo, 'qty_produced', 0.0) or 0.0
            remaining = max(qty - produced, 0.0) if mo.state != 'done' else 0.0
            state_data[mo.state]['count'] += 1
            state_data[mo.state]['qty'] += qty
            state_data[mo.state]['remaining_qty'] += remaining

        preferred = ['draft', 'confirmed', 'progress', 'to_close', 'done']
        states = []
        for state in preferred + [s for s in state_data if s not in preferred]:
            if state not in state_data:
                continue
            row = state_data[state]
            states.append({
                'key': state,
                'label': state_labels.get(state, state),
                'count': row['count'],
                'qty': round(row['qty'], 2),
                'remaining_qty': round(row['remaining_qty'], 2),
            })

        manufacturing_orders = [
            self._serialize_mo(mo, state_labels)
            for mo in productions.sorted(key=lambda m: (m.state, m.id), reverse=True)[:30]
        ]

        Workorder = self.env['mrp.workorder']
        workcenter_data = []
        if manufacturing_plans:
            workorders = Workorder.search([
                ('production_id.advanced_plan_id', 'in', manufacturing_plans.ids),
                ('production_id.state', '!=', 'cancel'),
            ])
            workcenters = workorders.mapped('workcenter_id').sorted(key=lambda wc: (wc.sequence, wc.id))
            workcenter_data = self._serialize_workcenters_multi(workcenters, manufacturing_plans)

        Purchase = self.env['purchase.order']
        pos = Purchase
        if purchase_plans:
            pos = Purchase.search([
                ('advanced_plan_id', 'in', purchase_plans.ids),
            ], order='id desc', limit=30)

        purchase_orders = [{
            'id': po.id,
            'name': po.name,
            'vendor': po.partner_id.display_name,
            'state': po.state,
            'state_label': dict(Purchase._fields['state'].selection).get(po.state, po.state),
            'amount_total': round(po.amount_total, 2),
            'currency': po.currency_id.name or '',
            'plan': po.advanced_plan_id.name if po.advanced_plan_id else '',
        } for po in pos]

        Picking = self.env['stock.picking']
        pickings = Picking
        if purchase_plans:
            pickings = Picking.search([
                ('advanced_plan_id', 'in', purchase_plans.ids),
            ], order='id desc', limit=30)

        picking_state_labels = dict(Picking._fields['state'].selection)
        transfers = [{
            'id': picking.id,
            'name': picking.name,
            'state': picking.state,
            'state_label': picking_state_labels.get(picking.state, picking.state),
            'source': picking.location_id.display_name,
            'destination': picking.location_dest_id.display_name,
            'scheduled_date': fields.Datetime.to_string(picking.scheduled_date) if picking.scheduled_date else '',
            'plan': picking.advanced_plan_id.name if picking.advanced_plan_id else '',
        } for picking in pickings]

        now = fields.Datetime.now()
        late_mo_count = 0
        if manufacturing_plans and 'date_deadline' in Production._fields:
            late_mo_count = Production.search_count([
                ('advanced_plan_id', 'in', manufacturing_plans.ids),
                ('state', 'not in', ('done', 'cancel')),
                ('date_deadline', '<', now),
            ])

        total_sales_qty = sum(scoped_plans.mapped('total_sales_qty')) if scoped_plans else 0.0
        total_stock_qty = sum(scoped_plans.mapped('total_stock_qty')) if scoped_plans else 0.0
        total_open_mo_qty = sum(manufacturing_plans.mapped('total_open_mo_qty')) if manufacturing_plans else 0.0
        total_to_manufacture_qty = sum(manufacturing_plans.mapped('total_to_manufacture_qty')) if manufacturing_plans else 0.0
        total_to_purchase_qty = sum(purchase_plans.mapped('total_to_purchase_qty')) if purchase_plans else 0.0
        total_to_move_qty = sum(purchase_plans.mapped('total_to_move_qty')) if purchase_plans else 0.0

        plan_payload = False
        if selected_plan:
            plan_payload = {
                'id': selected_plan.id,
                'name': selected_plan.name,
                'state': selected_plan.state,
                'plan_type': selected_plan.plan_type,
                'date_end': fields.Datetime.to_string(selected_plan.date_end),
                'warehouses': ', '.join(selected_plan.warehouse_ids.mapped('display_name')),
            }
        elif combined_admin_view:
            plan_payload = {
                'id': False,
                'name': _('Vista consolidada'),
                'state': 'combined',
                'plan_type': 'combined',
                'date_end': '',
                'warehouses': '',
            }

        return {
            'plan': plan_payload,
            'combined_admin_view': combined_admin_view,
            'plans': [{
                'id': plan.id,
                'name': plan.name,
                'state': plan.state,
                'plan_type': plan.plan_type,
                'date_end': fields.Datetime.to_string(plan.date_end),
            } for plan in plans],
            'permissions': {
                'is_admin': is_admin,
                'can_manufacturing': can_manufacturing,
                'can_purchase': can_purchase,
                'show_manufacturing': show_manufacturing,
                'show_purchase': show_purchase,
            },
            'kpis': {
                'pending_sales_qty': round(total_sales_qty, 2),
                'stock_qty': round(total_stock_qty, 2),
                'manufacturing_qty': round(total_open_mo_qty, 2),
                'to_manufacture_qty': round(total_to_manufacture_qty, 2),
                'to_purchase_qty': round(total_to_purchase_qty, 2),
                'to_move_qty': round(total_to_move_qty, 2),
                'mo_count': len(productions),
                'po_count': len(pos),
                'transfer_count': len(pickings),
                'products': len(active_lines),
                'workcenters_running': len([wc for wc in workcenter_data if wc['running_count']]),
                'manufacturing_plans': len(manufacturing_plans),
                'purchase_plans': len(purchase_plans),
            },
            'alerts': {
                'late_mo_count': late_mo_count,
                'manufacture_without_bom': len(
                    active_lines.filtered(lambda l: l.action_manufacture and not l.bom_id)
                ) if show_manufacturing else 0,
                'undefined_action': len(
                    active_lines.filtered(
                        lambda l: not (l.action_manufacture or l.action_purchase or l.action_move)
                    )
                ),
            },
            'states': states,
            'forecast_products': forecast_products,
            'manufacturing_orders': manufacturing_orders,
            'workcenters': workcenter_data,
            'purchase_orders': purchase_orders,
            'transfers': transfers,
        }


    def _dashboard_permissions(self):
        user = self.env.user
        return {
            'manufacturing': user.has_group('mrp_advanced_planner.group_planner_manufacturing_user'),
            'purchase': user.has_group('mrp_advanced_planner.group_planner_purchase_user'),
        }

    def _check_dashboard_permission(self, plan_id, plan_type):
        if not self._dashboard_permissions().get(plan_type):
            raise AccessError(_('No tiene permisos para consultar esta sección del panel.'))
        if plan_id:
            plan = self.env['mrp.planning.plan'].browse(int(plan_id)).exists()
            if not plan or plan.plan_type != plan_type:
                raise AccessError(_('La planificación seleccionada no corresponde a esta sección.'))
        return True

    def _serialize_mo(self, mo, state_labels):
        qty = mo.product_qty or 0.0
        produced = getattr(mo, 'qty_produced', 0.0) or 0.0
        progress = min(round((produced / qty) * 100, 1), 100.0) if qty else 0.0
        return {
            'id': mo.id, 'name': mo.name, 'product': mo.product_id.display_name,
            'qty': round(qty, 2), 'produced': round(produced, 2), 'remaining': round(max(qty - produced, 0), 2),
            'uom': mo.product_uom_id.name or '', 'state': mo.state,
            'state_label': state_labels.get(mo.state, mo.state), 'progress': progress,
            'warehouse': mo.picking_type_id.warehouse_id.display_name if mo.picking_type_id.warehouse_id else '',
        }

    def _serialize_workcenters(self, workcenters, plan):
        Workorder = self.env['mrp.workorder']
        labels = dict(Workorder._fields['state'].selection)
        result = []
        for wc in workcenters:
            orders = Workorder.search([
                ('workcenter_id', '=', wc.id), ('production_id.advanced_plan_id', '=', plan.id if plan else 0),
                ('state', 'in', ('blocked', 'ready', 'progress')),
            ], order='state desc, date_start, id')
            running = orders.filtered(lambda wo: wo.state == 'progress')
            queued = orders.filtered(lambda wo: wo.state in ('ready', 'blocked'))
            current = running[:1]
            result.append({
                'id': wc.id, 'name': wc.display_name, 'running_count': len(running), 'queue_count': len(queued),
                'oee': round(wc.oee or 0.0, 1), 'current_product': current.product_id.display_name if current else '',
                'current_mo': current.production_id.name if current else '', 'current_operation': current.name if current else '',
                'current_progress': round(current.progress or 0.0, 1) if current else 0.0,
                'orders': [{
                    'id': wo.id, 'mo_id': wo.production_id.id, 'mo': wo.production_id.name,
                    'product': wo.product_id.display_name, 'operation': wo.name,
                    'state': wo.state, 'state_label': labels.get(wo.state, wo.state),
                    'progress': round(wo.progress or 0.0, 1),
                } for wo in orders[:5]],
            })
        return result

    def _serialize_workcenters_multi(self, workcenters, plans):
        Workorder = self.env['mrp.workorder']
        labels = dict(Workorder._fields['state'].selection)
        result = []
        for wc in workcenters:
            orders = Workorder.search([
                ('workcenter_id', '=', wc.id),
                ('production_id.advanced_plan_id', 'in', plans.ids),
                ('state', 'in', ('blocked', 'ready', 'progress')),
            ], order='state desc, date_start, id')
            running = orders.filtered(lambda wo: wo.state == 'progress')
            queued = orders.filtered(lambda wo: wo.state in ('ready', 'blocked'))
            current = running[:1]
            result.append({
                'id': wc.id,
                'name': wc.display_name,
                'running_count': len(running),
                'queue_count': len(queued),
                'oee': round(wc.oee or 0.0, 1),
                'current_product': current.product_id.display_name if current else '',
                'current_mo': current.production_id.name if current else '',
                'current_operation': current.name if current else '',
                'current_progress': round(current.progress or 0.0, 1) if current else 0.0,
                'orders': [{
                    'id': wo.id,
                    'mo_id': wo.production_id.id,
                    'mo': wo.production_id.name,
                    'product': wo.product_id.display_name,
                    'operation': wo.name,
                    'state': wo.state,
                    'state_label': labels.get(wo.state, wo.state),
                    'progress': round(wo.progress or 0.0, 1),
                    'plan': wo.production_id.advanced_plan_id.name if wo.production_id.advanced_plan_id else '',
                } for wo in orders[:8]],
            })
        return result

    @api.model
    def action_open_mos(self, state=False, plan_id=False):
        self._check_dashboard_permission(plan_id, 'manufacturing')
        domain = [('advanced_plan_id', '=', int(plan_id) if plan_id else 0)]
        if state:
            domain.append(('state', '=', state))
        return {'type': 'ir.actions.act_window', 'name': _('Órdenes de fabricación'), 'res_model': 'mrp.production', 'view_mode': 'list,form', 'views': [(False, 'list'), (False, 'form')], 'domain': domain}

    @api.model
    def action_open_mo(self, production_id):
        return {'type': 'ir.actions.act_window', 'name': _('Orden de fabricación'), 'res_model': 'mrp.production', 'res_id': int(production_id), 'view_mode': 'form', 'views': [(False, 'form')], 'target': 'current'}

    @api.model
    def action_open_pos(self, plan_id=False):
        self._check_dashboard_permission(plan_id, 'purchase')
        return {'type': 'ir.actions.act_window', 'name': _('Compras del plan'), 'res_model': 'purchase.order', 'view_mode': 'list,form', 'views': [(False, 'list'), (False, 'form')], 'domain': [('advanced_plan_id', '=', int(plan_id) if plan_id else 0)]}

    @api.model
    def action_open_transfers(self, plan_id=False):
        self._check_dashboard_permission(plan_id, 'purchase')
        return {'type': 'ir.actions.act_window', 'name': _('Reabastecimientos del plan'), 'res_model': 'stock.picking', 'view_mode': 'list,form', 'views': [(False, 'list'), (False, 'form')], 'domain': [('advanced_plan_id', '=', int(plan_id) if plan_id else 0)]}

    @api.model
    def action_open_workorders(self, workcenter_id=False, plan_id=False):
        self._check_dashboard_permission(plan_id, 'manufacturing')
        domain = [('production_id.advanced_plan_id', '=', int(plan_id) if plan_id else 0), ('state', 'not in', ('done', 'cancel'))]
        if workcenter_id:
            domain.append(('workcenter_id', '=', int(workcenter_id)))
        return {'type': 'ir.actions.act_window', 'name': _('Órdenes de trabajo'), 'res_model': 'mrp.workorder', 'view_mode': 'list,form', 'views': [(False, 'list'), (False, 'form')], 'domain': domain}

    @api.model
    def action_open_plan(self, plan_id):
        return {'type': 'ir.actions.act_window', 'name': _('Planificación'), 'res_model': 'mrp.planning.plan', 'res_id': int(plan_id), 'view_mode': 'form', 'views': [(False, 'form')], 'target': 'current'}
