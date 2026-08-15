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

    get warehouseRows() {
        const raw = this.props.record.data.stock_warehouse_tooltip || "";
        return raw
            .split("\n")
            .map((line) => line.trim())
            .filter((line) => line && line.includes(":"))
            .map((line) => {
                const index = line.lastIndexOf(":");
                return {
                    warehouse: line.slice(0, index).trim(),
                    qty: line.slice(index + 1).trim(),
                };
            });
    }

    get popoverStyle() {
        return `top:${this.state.top}px;left:${this.state.left}px;`;
    }

    showPopover(ev) {
        const rect = ev.currentTarget.getBoundingClientRect();
        const width = 260;
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
