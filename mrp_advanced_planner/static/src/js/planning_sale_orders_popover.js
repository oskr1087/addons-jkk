/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class PlanningSaleOrdersPopoverField extends Component {
    static template = "mrp_advanced_planner.PlanningSaleOrdersPopoverField";
    static props = { ...standardFieldProps };

    setup() {
        this.state = useState({
            visible: false,
            top: 0,
            left: 0,
        });
    }

    get value() {
        return Number(this.props.record.data[this.props.name] || 0);
    }

    get data() {
        const raw = this.props.record.data.sale_order_popover_data || "";
        if (!raw) {
            return { count: 0, total_pending_qty: 0, uom: "", orders: [] };
        }
        try {
            return JSON.parse(raw);
        } catch {
            return { count: this.value, total_pending_qty: 0, uom: "", orders: [] };
        }
    }

    get orders() {
        return this.data.orders || [];
    }

    get popoverStyle() {
        return `top:${this.state.top}px;left:${this.state.left}px;`;
    }

    formatQty(qty) {
        return Number(qty || 0).toLocaleString(undefined, {
            minimumFractionDigits: 4,
            maximumFractionDigits: 4,
        });
    }

    formatDate(value) {
        if (!value) {
            return "Sin fecha";
        }
        const date = new Date(value.replace(" ", "T"));
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        return date.toLocaleDateString();
    }

    showPopover(ev) {
        const rect = ev.currentTarget.getBoundingClientRect();
        const width = 390;
        const margin = 10;

        let left = rect.left + rect.width / 2 - width / 2;
        left = Math.max(margin, Math.min(left, window.innerWidth - width - margin));

        let top = rect.top - 12;
        const estimatedHeight = Math.min(420, 145 + this.orders.length * 62);
        if (top - estimatedHeight < 10) {
            top = rect.bottom + estimatedHeight + 12;
        }

        this.state.left = left;
        this.state.top = top;
        this.state.visible = true;
    }

    hidePopover() {
        this.state.visible = false;
    }
}

registry.category("fields").add("planning_sale_orders_popover", {
    component: PlanningSaleOrdersPopoverField,
    supportedTypes: ["integer"],
});
