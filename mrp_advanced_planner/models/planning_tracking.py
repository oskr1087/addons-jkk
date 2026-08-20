from odoo import fields, models


class PlanningSupply(models.Model):
    _name = "mrp.planning.supply"
    _description = "Planning Supply Proposal"

    plan_id = fields.Many2one(
        "mrp.planning.plan", required=True, ondelete="cascade", index=True
    )
    requirement_id = fields.Many2one("mrp.planning.requirement", ondelete="cascade")
    product_id = fields.Many2one("product.product", required=True, index=True)
    supply_type = fields.Selection(
        [("existing", "Existing"), ("make", "Manufacture"), ("buy", "Buy")],
        required=True,
    )
    quantity = fields.Float(required=True)
    date_required = fields.Datetime(index=True)
    logical_key = fields.Char(required=True, index=True)
    production_id = fields.Many2one("mrp.production", readonly=True)
    purchase_order_id = fields.Many2one("purchase.order", readonly=True)
    production_proposal_id = fields.Many2one(
        "mrp.planning.production.proposal", ondelete="set null", index=True
    )
    purchase_proposal_id = fields.Many2one(
        "mrp.planning.purchase.proposal", ondelete="set null", index=True
    )
    state = fields.Selection(
        [("draft", "Draft"), ("applied", "Applied"), ("cancelled", "Cancelled")],
        default="draft",
    )

    _planning_supply_key_unique = models.Constraint(
        "UNIQUE(logical_key)",
        "A supply proposal with this logical key already exists.",
    )


class PlanningConflict(models.Model):
    _name = "mrp.planning.conflict"
    _description = "Planning Conflict"
    _order = "severity desc, id desc"

    plan_id = fields.Many2one(
        "mrp.planning.plan", required=True, ondelete="cascade", index=True
    )
    conflict_type = fields.Selection(
        [
            ("material_shortage", "Material Shortage"),
            ("capacity_shortage", "Capacity Shortage"),
            ("date_conflict", "Date Conflict"),
            ("bom_missing", "BOM Missing"),
            ("calendar_conflict", "Calendar Conflict"),
        ],
        required=True,
    )
    severity = fields.Selection(
        [("info", "Info"), ("warning", "Warning"), ("error", "Error")],
        default="warning",
        required=True,
    )
    product_id = fields.Many2one("product.product")
    workcenter_id = fields.Many2one("mrp.workcenter")
    operation_id = fields.Many2one(
        "mrp.planning.operation", ondelete="cascade", index=True
    )
    message = fields.Text(required=True)
    resolved = fields.Boolean(default=False)


class PlanningRun(models.Model):
    _name = "mrp.planning.run"
    _description = "Planning Execution"

    plan_id = fields.Many2one(
        "mrp.planning.plan", required=True, ondelete="cascade", index=True
    )
    run_type = fields.Selection(
        [
            ("calculation", "Calculation"),
            ("simulation", "Simulation"),
            ("application", "Application"),
        ],
        required=True,
    )
    state = fields.Selection(
        [
            ("queued", "Queued"),
            ("running", "Running"),
            ("completed", "Completed"),
            ("failed", "Failed"),
            ("cancelled", "Cancelled"),
        ],
        default="queued",
        required=True,
    )
    started_at = fields.Datetime(default=fields.Datetime.now)
    finished_at = fields.Datetime()
    error_message = fields.Text()
    lines_processed = fields.Integer(default=0, readonly=True)
