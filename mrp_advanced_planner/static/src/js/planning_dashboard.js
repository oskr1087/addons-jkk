/** @odoo-module **/

import { Component, onWillStart, useState } from '@odoo/owl';
import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';

export class PlanningDashboard extends Component {
    static template = 'mrp_advanced_planner.PlanningDashboard';

    setup() {
        this.orm = useService('orm');
        this.action = useService('action');
        this.state = useState({ loading: true, data: { kpis: {}, alerts: {}, plans: [], states: [], forecast_products: [], manufacturing_orders: [], workcenters: [], purchase_orders: [], transfers: [] }, filters: { plan_id: false } });
        onWillStart(() => this.loadData());
    }
    async loadData() {
        this.state.loading = true;
        try { this.state.data = await this.orm.call('mrp.planning.dashboard', 'get_data', [this.state.filters.plan_id || false, false, false, false, false]); }
        finally { this.state.loading = false; }
    }
    async onPlanChange(ev) { this.state.filters.plan_id = Number(ev.target.value) || false; await this.loadData(); }
    async runAction(method, args = []) { const result = await this.orm.call('mrp.planning.dashboard', method, args); if (result) await this.action.doAction(result); }
    currentPlanId() { return this.state.data.plan ? this.state.data.plan.id : false; }
    openPlan() { if (this.currentPlanId()) return this.runAction('action_open_plan', [this.currentPlanId()]); }
    openMOs(state = false) { return this.runAction('action_open_mos', [state || false, this.currentPlanId()]); }
    openMO(id) { return this.runAction('action_open_mo', [id]); }
    openPOs() { return this.runAction('action_open_pos', [this.currentPlanId()]); }
    openTransfers() { return this.runAction('action_open_transfers', [this.currentPlanId()]); }
    openWorkorders(id = false) { return this.runAction('action_open_workorders', [id || false, this.currentPlanId()]); }
    openForecastLine(id) { return this.action.doAction({ type: 'ir.actions.act_window', name: 'Producto planificado', res_model: 'mrp.planning.plan.line', res_id: id, view_mode: 'form', views: [[false, 'form']], target: 'current' }); }
    progressStyle(value) { const p = Math.max(0, Math.min(Number(value || 0), 100)); return `width:${p}%`; }
    statePercent(item) { const total = this.state.data.states.reduce((s, r) => s + r.count, 0); return total ? Math.round(item.count / total * 100) : 0; }
    actionClass(action) { return { manufacture: 'aps-sem-blue', purchase: 'aps-sem-yellow', move: 'aps-sem-green', none: 'aps-sem-red' }[action] || 'aps-sem-gray'; }
    moClass(state) { return { done: 'aps-sem-green', to_close: 'aps-sem-green', progress: 'aps-sem-blue', confirmed: 'aps-sem-yellow', draft: 'aps-sem-gray', cancel: 'aps-sem-red' }[state] || 'aps-sem-gray'; }
    progressClass(value) { const p = Number(value || 0); if (p >= 100) return 'aps-progress-green'; if (p >= 50) return 'aps-progress-blue'; if (p > 0) return 'aps-progress-yellow'; return 'aps-progress-gray'; }
}
registry.category('actions').add('mrp_advanced_planner.dashboard', PlanningDashboard);
