/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";

export class PlanningComponentTreeField extends Component {
    static template = "mrp_advanced_planner.PlanningComponentTreeField";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            roots: [],
            rows: [],
            expanded: {},
            query: "",
        });
        onWillStart(() => this.load());
    }

    get planId() {
        return this.props.record.resId;
    }

    async load() {
        if (!this.planId) {
            this.state.loading = false;
            return;
        }
        this.state.loading = true;

        const planningLines = await this.orm.searchRead(
            "mrp.planning.plan.line",
            [
                ["plan_id", "=", this.planId],
                ["action_manufacture", "=", true],
                ["planner_production_qty", ">", 0],
            ],
            ["product_id", "planner_production_qty", "product_uom_id", "created_production_id"],
            { order: "id" }
        );

        const components = await this.orm.searchRead(
            "mrp.planning.production.component",
            [["plan_id", "=", this.planId]],
            [
                "planning_line_id",
                "parent_line_id",
                "product_id",
                "original_product_id",
                "product_uom_id",
                "planned_qty",
                "original_qty",
                "level",
                "sequence",
                "path",
                "change_type",
                "include_in_mo",
                "availability_qty",
                "availability_need_qty",
                "availability_status",
                "effective_required_qty",
                "local_supply_qty",
                "external_move_suggested_qty",
                "to_manufacture_qty",
                "to_purchase_qty",
                "supply_resolution",
                "is_subcontracted",
                "subcontract_bom_id",
                "engineering_locked",
                "note",
            ],
            { order: "planning_line_id, sequence, level, id" }
        );

        const byPlanningLine = {};
        for (const component of components) {
            const planningLineId = component.planning_line_id?.[0];
            if (!byPlanningLine[planningLineId]) {
                byPlanningLine[planningLineId] = [];
            }
            byPlanningLine[planningLineId].push(component);
        }

        this.state.roots = planningLines.map((line) => ({
            key: `root-${line.id}`,
            id: line.id,
            productId: line.product_id?.[0],
            productName: line.product_id?.[1] || "",
            qty: line.planner_production_qty || 0,
            uom: line.product_uom_id?.[1] || "",
            locked: Boolean(line.created_production_id?.[0]),
            children: this.buildChildren(byPlanningLine[line.id] || [], false),
        }));

        for (const root of this.state.roots) {
            if (!(root.key in this.state.expanded)) {
                this.state.expanded[root.key] = true;
            }
        }
        this.state.loading = false;
    }

    buildChildren(records, parentId) {
        return records
            .filter((row) => (row.parent_line_id?.[0] || false) === parentId)
            .sort((a, b) => (a.sequence - b.sequence) || (a.id - b.id))
            .map((row) => ({
                ...row,
                key: `component-${row.id}`,
                productName: row.product_id?.[1] || "",
                uom: row.product_uom_id?.[1] || "",
                children: this.buildChildren(records, row.id),
            }));
    }

    toggle(key) {
        this.state.expanded[key] = !this.state.expanded[key];
    }

    expandAll() {
        const visit = (rows) => {
            for (const row of rows) {
                if (row.children?.length) {
                    this.state.expanded[row.key] = true;
                    visit(row.children);
                }
            }
        };
        for (const root of this.state.roots) {
            this.state.expanded[root.key] = true;
            visit(root.children);
        }
    }

    collapseAll() {
        for (const key of Object.keys(this.state.expanded)) {
            this.state.expanded[key] = false;
        }
    }

    async saveQty(row, ev) {
        if (row.engineering_locked) {
            this.notification.add("La ingeniería está bloqueada porque ya se generó la OF.", { type: "warning" });
            await this.load();
            return;
        }
        const value = Number(ev.target.value || 0);
        if (value < 0) {
            this.notification.add("La cantidad no puede ser negativa.", { type: "warning" });
            ev.target.value = row.planned_qty;
            return;
        }
        await this.orm.write(
            "mrp.planning.production.component",
            [row.id],
            { planned_qty: value }
        );
        await this.load();
    }

    async toggleActive(row) {
        if (row.engineering_locked) {
            this.notification.add("La ingeniería está bloqueada porque ya se generó la OF.", { type: "warning" });
            await this.load();
            return;
        }
        await this.orm.write(
            "mrp.planning.production.component",
            [row.id],
            { include_in_mo: !row.include_in_mo }
        );
        await this.load();
    }

    async openAvailability(row) {
        const ids = await this.orm.search(
            "mrp.planning.production.component",
            [["id", "=", row.id], ["plan_id", "=", this.planId]],
            { limit: 1 }
        );
        if (!ids.length) {
            this.notification.add(
                "El componente fue actualizado por un recálculo. Se refrescó el árbol.",
                { type: "warning" }
            );
            await this.load();
            return;
        }
        const action = await this.orm.call(
            "mrp.planning.production.component",
            "action_open_availability_by_id",
            [],
            { component_id: row.id }
        );
        await this.action.doAction(action, { onClose: () => this.load() });
    }

    async editComponent(row) {
        const ids = await this.orm.search(
            "mrp.planning.production.component",
            [["id", "=", row.id], ["plan_id", "=", this.planId]],
            { limit: 1 }
        );
        if (!ids.length) {
            this.notification.add(
                "El componente fue actualizado por un recálculo. Se refrescó el árbol.",
                { type: "warning" }
            );
            await this.load();
            return;
        }
        const action = await this.orm.call(
            "mrp.planning.production.component",
            "action_open_edit_component_by_id",
            [],
            { component_id: row.id }
        );
        await this.action.doAction(action, { onClose: () => this.load() });
    }

    async addComponent(root) {
        if (root.locked) {
            this.notification.add(
                "No puede agregar componentes: la OF ya fue generada.",
                { type: "warning" }
            );
            return;
        }
        await this.action.doAction(
            {
                type: "ir.actions.act_window",
                name: "Agregar componente APS",
                res_model: "mrp.planning.production.component",
                views: [[false, "form"]],
                target: "new",
                context: {
                    default_plan_id: this.planId,
                    default_planning_line_id: root.id,
                    default_root_product_id: root.productId,
                    default_level: 1,
                    default_include_in_mo: true,
                },
            },
            { onClose: () => this.load() }
        );
    }

    async addChildComponent(row) {
        if (row.engineering_locked) {
            this.notification.add("La ingeniería está bloqueada porque ya se generó la OF.", { type: "warning" });
            await this.load();
            return;
        }
        await this.action.doAction(
            {
                type: "ir.actions.act_window",
                name: "Agregar subcomponente APS",
                res_model: "mrp.planning.production.component",
                views: [[false, "form"]],
                target: "new",
                context: {
                    default_plan_id: this.planId,
                    default_planning_line_id: row.planning_line_id?.[0],
                    default_parent_line_id: row.id,
                    default_root_product_id: this.state.roots.find(
                        (root) => root.id === row.planning_line_id?.[0]
                    )?.productId,
                    default_level: (row.level || 0) + 1,
                    default_include_in_mo: true,
                },
            },
            { onClose: () => this.load() }
        );
    }

    async deleteComponent(row) {
        if (row.engineering_locked) {
            this.notification.add("La ingeniería está bloqueada porque ya se generó la OF.", { type: "warning" });
            await this.load();
            return;
        }
        const action = await this.orm.call(
            "mrp.planning.production.component",
            "action_delete_component_by_id",
            [],
            { component_id: row.id }
        );
        if (action) {
            await this.action.doAction(action);
        }
        await this.load();
    }

    getStatusClass(status) {
        if (status === "sufficient") return "aps-status aps-status-success";
        if (status === "partial") return "aps-status aps-status-warning";
        return "aps-status aps-status-danger";
    }

    getStatusText(row) {
        if (row.availability_status === "sufficient") return `Suficiente (${this.formatQty(row.availability_qty)})`;
        if (row.availability_status === "partial") return `Parcial (${this.formatQty(row.availability_qty)})`;
        return "Sin disponibilidad";
    }

    getChangeText(value) {
        return {
            original: "Original",
            modified: "Modificado",
            replaced: "Sustituido",
            manual: "Manual",
            omitted: "Omitido",
        }[value] || value || "";
    }

    getChangeClass(value) {
        return `aps-change aps-change-${value || "original"}`;
    }

    getSupplyText(row) {
        const labels = {
            not_required: "No requerido",
            available: "Disponible",
            move: "Mover",
            manufacture: "Fabricar",
            purchase: "Comprar",
            move_manufacture: "Mover + Fabricar",
            move_purchase: "Mover + Comprar",
            subcontract: "Subcontratación",
            move_subcontract: "Mover + Subcontratación",
            review: "Revisar",
        };
        return labels[row.supply_resolution] || "Revisar";
    }

    getSupplyClass(value) {
        if (value === "available") return "aps-supply aps-supply-available";
        if (value === "move") return "aps-supply aps-supply-move";
        if (value === "manufacture") return "aps-supply aps-supply-manufacture";
        if (value === "purchase") return "aps-supply aps-supply-purchase";
        if (value === "move_manufacture") return "aps-supply aps-supply-mixed";
        if (value === "move_purchase") return "aps-supply aps-supply-mixed";
        if (value === "subcontract") return "aps-supply aps-supply-subcontract";
        if (value === "move_subcontract") return "aps-supply aps-supply-subcontract";
        if (value === "not_required") return "aps-supply aps-supply-muted";
        return "aps-supply aps-supply-review";
    }

    getPendingQty(row) {
        return (row.to_manufacture_qty || 0) + (row.to_purchase_qty || 0);
    }

    formatQty(value) {
        return Number(value || 0).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    matches(row) {
        const q = (this.state.query || "").trim().toLowerCase();
        if (!q) return true;
        return (row.productName || "").toLowerCase().includes(q)
            || (row.path || "").toLowerCase().includes(q);
    }

    hasVisibleChildren(row) {
        return row.children?.some((child) => this.matches(child) || this.hasVisibleChildren(child));
    }
}

registry.category("fields").add("planning_component_tree", {
    component: PlanningComponentTreeField,
    supportedTypes: ["one2many"],
});
