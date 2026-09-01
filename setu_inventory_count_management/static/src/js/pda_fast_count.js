/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class PDAFastCount extends Component {
    static template = "setu_inventory_count_management.PDAFastCount";

    setup() {
        this.orm = useService("orm");
        this.barcode = useService("barcode");
        this.notification = useService("notification");
        this.action = useService("action");

        this.sessionId = this.props.action.params.session_id;
        this.scanQueue = [];
        this.processingQueue = false;

        this.state = useState({
            loading: true,
            busy: false,
            data: {},
            quantity: 1,
            manualBarcode: "",
            scanCounter: 0,
        });

        useBus(this.barcode.bus, "barcode_scanned", (event) => {
            const detail = event.detail || {};
            const barcode = detail.barcode || detail;
            this.enqueueBarcode(barcode);
        });

        onWillStart(() => this.loadState());
    }

    async loadState() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "setu.inventory.count.session",
                "pda_fast_get_state",
                [[this.sessionId]]
            );
            this.applyState(data);
        } finally {
            this.state.loading = false;
        }
    }

    applyState(data) {
        this.state.data = data || {};
        const qty = Number(data?.qty ?? 1);
        this.state.quantity = Number.isFinite(qty) ? qty : 1;
        this.state.scanCounter += 1;
        this.feedback(data?.feedback_type);
    }

    feedback(type) {
        if (!window.navigator?.vibrate) {
            return;
        }
        if (type === "success") {
            window.navigator.vibrate(45);
        } else if (type === "warning" || type === "danger") {
            window.navigator.vibrate([70, 45, 70]);
        }
    }

    enqueueBarcode(barcode) {
        const value = String(barcode || "").trim();
        if (!value || this.state.data.finished) {
            return;
        }
        this.scanQueue.push(value);
        this.drainQueue();
    }

    async drainQueue() {
        if (this.processingQueue) {
            return;
        }
        this.processingQueue = true;
        this.state.busy = true;
        try {
            while (this.scanQueue.length) {
                const barcode = this.scanQueue.shift();
                try {
                    const data = await this.orm.call(
                        "setu.inventory.count.session",
                        "pda_fast_scan",
                        [[this.sessionId], barcode]
                    );
                    this.applyState(data);
                } catch (error) {
                    this.notification.add(
                        error?.data?.message || error?.message || _t("No se pudo procesar el código."),
                        { type: "danger" }
                    );
                    this.feedback("danger");
                }
            }
        } finally {
            this.state.busy = false;
            this.processingQueue = false;
        }
    }

    async confirmQuantity() {
        if (!this.state.data.can_set_qty || this.state.busy) {
            return;
        }
        const qty = Number(this.state.quantity);
        if (!Number.isFinite(qty) || qty < 0) {
            this.notification.add(_t("Ingrese una cantidad válida."), { type: "warning" });
            return;
        }
        await this.callServer("pda_fast_confirm_qty", [qty]);
    }

    async clearItem() {
        await this.callServer("pda_fast_clear_item");
    }

    setQuantity(value) {
        this.state.quantity = Math.max(0, Number(value) || 0);
    }

    quantityMinus() {
        this.setQuantity(this.state.quantity - 1);
    }

    quantityPlus() {
        this.setQuantity(this.state.quantity + 1);
    }

    quantityZero() {
        this.setQuantity(0);
    }

    onQuantityInput(event) {
        this.state.quantity = event.target.value;
    }

    onManualBarcodeInput(event) {
        this.state.manualBarcode = event.target.value;
    }

    onManualBarcodeKeydown(event) {
        if (event.key === "Enter") {
            event.preventDefault();
            this.processManualBarcode();
        }
    }

    processManualBarcode() {
        const barcode = String(this.state.manualBarcode || "").trim();
        if (!barcode) {
            return;
        }
        this.state.manualBarcode = "";
        this.enqueueBarcode(barcode);
    }

    async control(operation) {
        if (this.state.busy) {
            return;
        }
        await this.callServer("pda_fast_control", [operation]);
    }

    startSession() {
        return this.control("start");
    }

    resumeSession() {
        return this.control("resume");
    }

    pauseSession() {
        return this.control("pause");
    }

    submitSession() {
        return this.control("submit");
    }

    async callServer(method, args = []) {
        this.state.busy = true;
        try {
            const data = await this.orm.call(
                "setu.inventory.count.session",
                method,
                [[this.sessionId], ...args]
            );
            this.applyState(data);
        } catch (error) {
            this.notification.add(
                error?.data?.message || error?.message || _t("No se pudo completar la operación."),
                { type: "danger" }
            );
            this.feedback("danger");
        } finally {
            this.state.busy = false;
        }
    }

    async goBack() {
        await this.action.doAction(
            "setu_inventory_count_management.inventory_count_session_act_window"
        );
    }
}

registry.category("actions").add(
    "setu_inventory_count_management.pda_fast_count",
    PDAFastCount
);
