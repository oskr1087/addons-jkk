from odoo import api, fields, models
from odoo.exceptions import UserError


class MrpAdvancedPlan(models.Model):
    _name = "mrp.advanced.plan"
    _description = "APS Planning Plan"
    _order = "create_date desc"

    name = fields.Char(required=True, copy=False, default="New")
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        required=True,
        default=lambda self: self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        ),
    )
    date_start = fields.Datetime(required=True, default=fields.Datetime.now)
    date_end = fields.Datetime(required=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("queued", "Queued"),
            ("running", "Running"),
            ("calculated", "Calculated"),
            ("approved", "Approved"),
            ("applied", "Applied"),
            ("cancelled", "Cancelled"),
            ("failed", "Failed"),
        ],
        default="draft",
        required=True,
    )
    finite_capacity = fields.Boolean(default=True)
    include_purchase = fields.Boolean(default=True)
    include_manufacturing = fields.Boolean(default=True)
    use_alternatives = fields.Boolean(default=True)
    setup_time = fields.Boolean(default=True)
    priority = fields.Selection(
        [
            ("sale", "Sales priority"),
            ("date", "Due date"),
            ("customer", "Customer priority"),
        ],
        default="date",
    )
    demand_ids = fields.One2many("mrp.advanced.demand", "plan_id")
    requirement_ids = fields.One2many("mrp.advanced.requirement", "plan_id")
    supply_ids = fields.One2many("mrp.advanced.supply", "plan_id")
    operation_ids = fields.One2many("mrp.advanced.operation", "plan_id")
    conflict_ids = fields.One2many("mrp.advanced.conflict", "plan_id")
    execution_ids = fields.One2many("mrp.advanced.execution", "plan_id")
    conflict_count = fields.Integer(compute="_compute_counts")
    demand_count = fields.Integer(compute="_compute_counts")
    supply_count = fields.Integer(compute="_compute_counts")

    @api.depends("conflict_ids", "demand_ids", "supply_ids")
    def _compute_counts(self):
        for rec in self:
            rec.conflict_count = len(rec.conflict_ids)
            rec.demand_count = len(rec.demand_ids)
            rec.supply_count = len(rec.supply_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("mrp.advanced.plan") or "New"
                )
        return super().create(vals_list)

    def action_calculate(self):
        from ..services.application_engine import PlannerEngine

        for plan in self:
            if plan.state not in ("draft", "calculated", "failed"):
                raise UserError("Only draft or recalculable plans can be calculated.")
            plan.write({"state": "running"})
            try:
                PlannerEngine(plan).calculate()
                plan.write({"state": "calculated"})
            except Exception:
                plan.write({"state": "failed"})
                raise
        return True

    def action_approve(self):
        self.filtered(lambda p: p.state == "calculated").write({"state": "approved"})
        return True

    def action_apply(self):
        from ..services.application_engine import PlannerEngine

        for plan in self:
            if plan.state != "approved":
                raise UserError("Approve the plan before applying it.")
            PlannerEngine(plan).apply()
            plan.state = "applied"
        return True

    def action_cancel(self):
        self.write({"state": "cancelled"})
        return True


class MrpAdvancedExecution(models.Model):
    _name = "mrp.advanced.execution"
    _description = "APS Execution Log"
    plan_id = fields.Many2one("mrp.advanced.plan", required=True, ondelete="cascade")
    state = fields.Selection(
        [
            ("queued", "Queued"),
            ("running", "Running"),
            ("completed", "Completed"),
            ("failed", "Failed"),
            ("cancelled", "Cancelled"),
        ],
        default="queued",
    )
    started_at = fields.Datetime()
    finished_at = fields.Datetime()
    message = fields.Text()
    progress = fields.Float(default=0, digits=(16, 4))


class MrpAdvancedConflict(models.Model):
    _name = "mrp.advanced.conflict"
    _description = "APS Planning Conflict"
    plan_id = fields.Many2one("mrp.advanced.plan", required=True, ondelete="cascade")
    severity = fields.Selection(
        [("info", "Info"), ("warning", "Warning"), ("error", "Error")],
        default="warning",
        required=True,
    )
    conflict_type = fields.Selection(
        [
            ("material", "Material"),
            ("capacity", "Capacity"),
            ("calendar", "Calendar"),
            ("bom", "BOM"),
            ("route", "Route"),
            ("roll", "Roll"),
        ],
        required=True,
    )
    product_id = fields.Many2one("product.product")
    workcenter_id = fields.Many2one("mrp.workcenter")
    message = fields.Text(required=True)
    resolved = fields.Boolean(default=False)
