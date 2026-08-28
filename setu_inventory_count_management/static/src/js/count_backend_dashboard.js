/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class CountBackendDashboard extends Component {
    static template = "setu_inventory_count_management.CountBackendDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.countId = this.props.action.params.count_id;

        this.state = useState({
            loading: true,
            refreshing: false,
            data: {
                count: {},
                kpis: {},
                pending: [],
                differences: [],
            },
            tab: "pending",
            pendingPage: 1,
            differencePage: 1,
            pageSize: 25,
        });

        onWillStart(() => this.loadData());
    }

    async loadData() {
        this.state.loading = true;
        try {
            const data = await this.fetchData();
            this.state.data = data;
            this.syncPages(data);
        } catch (error) {
            this.notification.add(
                error?.data?.message || error?.message || _t("No se pudo cargar el panel."),
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    async refresh() {
        if (this.state.refreshing) {
            return;
        }
        this.state.refreshing = true;
        try {
            const data = await this.fetchData();
            this.state.data = data;
            this.syncPages(data);
            this.notification.add(_t("Información actualizada."), { type: "success" });
        } finally {
            this.state.refreshing = false;
        }
    }

    fetchData() {
        return this.orm.call(
            "setu.stock.inventory.count",
            "get_backend_dashboard_data",
            [
                [this.countId],
                this.state.pendingPage,
                this.state.differencePage,
                this.state.pageSize,
            ]
        );
    }

    syncPages(data) {
        const pagination = data?.pagination || {};
        this.state.pendingPage = pagination.pending?.page || 1;
        this.state.differencePage = pagination.differences?.page || 1;
    }

    async changePage(kind, delta) {
        if (this.state.refreshing) {
            return;
        }
        const pager = this.state.data.pagination?.[kind];
        if (!pager) {
            return;
        }
        const current = pager.page || 1;
        const pages = pager.pages || 1;
        const next = Math.min(Math.max(current + delta, 1), pages);
        if (next === current) {
            return;
        }
        if (kind === "pending") {
            this.state.pendingPage = next;
        } else {
            this.state.differencePage = next;
        }
        this.state.refreshing = true;
        try {
            const data = await this.fetchData();
            this.state.data = data;
            this.syncPages(data);
        } finally {
            this.state.refreshing = false;
        }
    }

    previousPendingPage() {
        return this.changePage("pending", -1);
    }

    nextPendingPage() {
        return this.changePage("pending", 1);
    }

    previousDifferencePage() {
        return this.changePage("differences", -1);
    }

    nextDifferencePage() {
        return this.changePage("differences", 1);
    }

    setPendingTab() {
        this.state.tab = "pending";
    }

    setDifferenceTab() {
        this.state.tab = "differences";
    }

    async openSessions() {
        const action = await this.orm.call(
            "setu.stock.inventory.count",
            "dashboard_open_sessions",
            [[this.countId]]
        );
        return this.action.doAction(action);
    }

    async createSession() {
        const action = await this.orm.call(
            "setu.stock.inventory.count",
            "dashboard_create_session",
            [[this.countId]]
        );
        return this.action.doAction(action);
    }

    async completeCounting() {
        try {
            const data = await this.orm.call(
                "setu.stock.inventory.count",
                "dashboard_complete_counting",
                [[this.countId]]
            );
            this.state.data = data;
            this.syncPages(data);
            this.notification.add(_t("Conteo enviado para revisión."), { type: "success" });
        } catch (error) {
            this.notification.add(
                error?.data?.message || error?.message || _t("No se pudo completar el conteo."),
                { type: "danger" }
            );
        }
    }

    async openScanned() {
        const action = await this.orm.call(
            "setu.stock.inventory.count",
            "dashboard_open_scanned_lines",
            [[this.countId]]
        );
        return this.action.doAction(action);
    }

    async openDifferences() {
        const action = await this.orm.call(
            "setu.stock.inventory.count",
            "dashboard_open_difference_lines",
            [[this.countId]]
        );
        return this.action.doAction(action);
    }

    async openQuant(row) {
        const action = await this.orm.call(
            "setu.stock.inventory.count",
            "dashboard_open_quant",
            [[this.countId], row.product_id, row.lot_id || false, row.location_id || false]
        );
        return this.action.doAction(action);
    }

    async openQuantFromEvent(event) {
        const button = event.currentTarget;
        const productId = Number(button.dataset.productId);
        const lotId = Number(button.dataset.lotId) || false;
        const locationId = Number(button.dataset.locationId) || false;
        const action = await this.orm.call(
            "setu.stock.inventory.count",
            "dashboard_open_quant",
            [[this.countId], productId, lotId, locationId]
        );
        return this.action.doAction(action);
    }

    goBack() {
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "setu.stock.inventory.count",
            res_id: this.countId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add(
    "setu_inventory_count_management.count_backend_dashboard",
    CountBackendDashboard
);
