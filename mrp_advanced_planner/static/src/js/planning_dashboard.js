/** @odoo-module **/

import { Component, onWillStart, useState } from '@odoo/owl';
import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';

export class PlanningDashboard extends Component {
    static template = 'mrp_advanced_planner.PlanningDashboard';

    setup() {
        this.orm = useService('orm');
        this.action = useService('action');
        this.state = useState({
            loading: true,
            data: {
                kpis: {}, states: [], forecast_products: [], plans: [], plan: false,
                alerts: {}, manufacturing_orders: [], workcenters: [],
            },
            filters: { plan_id: false },
        });
        onWillStart(() => this.loadData());
    }

    async loadData() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(
                'mrp.planning.dashboard',
                'get_data',
                [this.state.filters.plan_id || false, false, false, false, false]
            );
        } finally {
            this.state.loading = false;
        }
    }

    async onPlanChange(ev) {
        this.state.filters.plan_id = Number(ev.target.value) || false;
        await this.loadData();
    }

    async runAction(method, args = []) {
        const result = await this.orm.call('mrp.planning.dashboard', method, args);
        if (result) await this.action.doAction(result);
    }

    currentPlanId() {
        return this.state.data.plan ? this.state.data.plan.id : false;
    }
    openMOs(state = false) { return this.runAction('action_open_mos', [state || false, this.currentPlanId()]); }
    openMO(id) { return this.runAction('action_open_mo', [id]); }
    openWorkcenter(id) { return this.runAction('action_open_workcenter', [id]); }
    openWorkorders(id = false) { return this.runAction('action_open_workorders', [id || false, this.currentPlanId()]); }
    openLateMOs() { return this.runAction('action_open_late_mos', [this.currentPlanId()]); }
    openPlan() {
        if (this.state.data.plan) return this.runAction('action_open_plan', [this.state.data.plan.id]);
    }
    openForecastLine(lineId) {
        return this.action.doAction({
            type: 'ir.actions.act_window', name: 'Producto a fabricar', res_model: 'mrp.planning.plan.line',
            res_id: lineId, view_mode: 'form', views: [[false, 'form']], target: 'current',
        });
    }
    statePercent(item) {
        const total = this.state.data.states.reduce((sum, row) => sum + row.count, 0);
        return total ? Math.round((item.count / total) * 100) : 0;
    }
    coveragePercent() {
        const sales = Number(this.state.data.kpis.pending_sales_qty || 0);
        const covered = Number(this.state.data.kpis.stock_qty || 0) + Number(this.state.data.kpis.manufacturing_qty || 0);
        return sales ? Math.min(Math.round((covered / sales) * 100), 100) : 100;
    }
    progressStyle(value) {
        const pct = Math.max(0, Math.min(Number(value || 0), 100));
        return `width:${pct}%`;
    }
    moSemaphoreClass(state) {
        return {
            done: 'aps-sem-green',
            to_close: 'aps-sem-green',
            progress: 'aps-sem-blue',
            confirmed: 'aps-sem-yellow',
            draft: 'aps-sem-gray',
            cancel: 'aps-sem-red',
        }[state] || 'aps-sem-gray';
    }
    workcenterSemaphoreClass(wc) {
        if (Number(wc.running_count || 0) > 0) return 'aps-sem-blue';
        if (Number(wc.queue_count || 0) > 0) return 'aps-sem-yellow';
        return 'aps-sem-green';
    }
    progressSemaphoreClass(value) {
        const pct = Number(value || 0);
        if (pct >= 100) return 'aps-progress-green';
        if (pct >= 50) return 'aps-progress-blue';
        if (pct > 0) return 'aps-progress-yellow';
        return 'aps-progress-gray';
    }
}
registry.category('actions').add('mrp_advanced_planner.dashboard', PlanningDashboard);
