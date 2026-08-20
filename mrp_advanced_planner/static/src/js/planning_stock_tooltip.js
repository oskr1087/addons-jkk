/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class PlanningStockTooltipField extends Component {
    static template = "mrp_advanced_planner.PlanningStockTooltipField";
    static props = { ...standardFieldProps };

    setup() {
        this.state = useState({
            visible: false,
            top: 0,
            left: 0,
        });
    }

    get numericValue() {
        return Number(this.props.record.data[this.props.name] || 0);
    }

    get value() {
        return this.numericValue.toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    formatQty(value) {
        return Number(value || 0).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    get warehouseRows() {
        const raw = this.props.record.data.stock_warehouse_tooltip || "";
        return raw
            .split("\n")
            .map((line) => line.trim())
            .filter((line) => line && line.includes("|"))
            .map((line) => {
                const parts = line.split("|");
                return {
                    warehouse: parts[0] || "",
                    onHand: Number(parts[1] || 0),
                    incoming: Number(parts[2] || 0),
                    outgoing: Number(parts[3] || 0),
                    rfq: Number(parts[4] || 0),
                    otherPlan: Number(parts[5] || 0),
                    forecast: Number(parts[6] || 0),
                };
            });
    }

    get totals() {
        const rows = this.warehouseRows;
        const sum = (name) => rows.reduce((acc, row) => acc + Number(row[name] || 0), 0);
        return {
            onHand: this.formatQty(sum("onHand")),
            incoming: this.formatQty(sum("incoming")),
            outgoing: this.formatQty(sum("outgoing")),
            rfq: this.formatQty(sum("rfq")),
            otherPlan: this.formatQty(sum("otherPlan")),
            forecast: this.value,
            hasAdjustments: Math.abs(sum("rfq")) > 1e-6 || Math.abs(sum("otherPlan")) > 1e-6,
        };
    }

    get popoverStyle() {
        return `top:${this.state.top}px;left:${this.state.left}px;`;
    }

    showPopover(ev) {
        const rect = ev.currentTarget.getBoundingClientRect();
        const width = Math.min(620, window.innerWidth - 24);
        const margin = 10;

        let left = rect.left + rect.width / 2 - width / 2;
        left = Math.max(margin, Math.min(left, window.innerWidth - width - margin));

        let top = rect.top - 12;
        if (top < 180) {
            top = rect.bottom + 12;
        }

        this.state.left = left;
        this.state.top = top;
        this.state.visible = true;
    }

    hidePopover() {
        this.state.visible = false;
    }
}

registry.category("fields").add("planning_stock_tooltip", {
    component: PlanningStockTooltipField,
    supportedTypes: ["float", "integer", "monetary"],
});
