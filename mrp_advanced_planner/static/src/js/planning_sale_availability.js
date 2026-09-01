/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";

export class PlanningSaleAvailabilityField extends Component {
    static template = "mrp_advanced_planner.PlanningSaleAvailabilityField";
    static props = { ...standardFieldProps };

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
    }

    get rawStatus() {
        return this.props.record.data[this.props.name] || "uncovered";
    }

    get label() {
        const labels = {
            available: "Disponible",
            covered: "Cubierto",
            manufacturing: "Cubierto",
            purchase: "Cubierto",
            transfer: "Cubierto",
            mixed: "Cubierto",
            partial: "Parcial",
            uncovered: "Sin cubrir",
        };
        return labels[this.rawStatus] || "Sin cubrir";
    }

    get badgeClass() {
        if (["available", "covered", "manufacturing", "purchase", "transfer", "mixed"].includes(this.rawStatus)) {
            return "o_aps_supply_badge o_aps_supply_ok";
        }
        if (this.rawStatus === "partial") {
            return "o_aps_supply_badge o_aps_supply_partial";
        }
        return "o_aps_supply_badge o_aps_supply_danger";
    }

    async openAvailability(ev) {
        ev.stopPropagation();
        const resId = this.props.record.resId;
        if (!resId) {
            return;
        }
        const action = await this.orm.call(
            "sale.order.line",
            "action_open_aps_availability",
            [[resId]]
        );
        if (action) {
            await this.action.doAction(action);
        }
    }
}

registry.category("fields").add("planning_sale_availability", {
    component: PlanningSaleAvailabilityField,
    supportedTypes: ["selection"],
});
