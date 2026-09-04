from odoo import fields, models


class MrpAdvancedRequirement(models.Model):
    _name = "mrp.advanced.requirement"
    _description = "Multi-level Material Requirement"
    plan_id = fields.Many2one("mrp.advanced.plan", required=True, ondelete="cascade")
    parent_id = fields.Many2one("mrp.advanced.requirement", ondelete="cascade")
    child_ids = fields.One2many("mrp.advanced.requirement", "parent_id")
    demand_id = fields.Many2one("mrp.advanced.demand")
    product_id = fields.Many2one("product.product", required=True)
    quantity = fields.Float(required=True, digits=(16, 4))
    date_required = fields.Datetime(required=True)
    level = fields.Integer(default=0)
    trace_key = fields.Char(index=True)
    state = fields.Selection(
        [("open", "Open"), ("covered", "Covered"), ("blocked", "Blocked")],
        default="open",
    )


class MrpAdvancedSupply(models.Model):
    _name = "mrp.advanced.supply"
    _description = "APS Supply Proposal"
    _sql_constraints = [
        (
            "logical_key_unique",
            "unique(plan_id,product_id,requirement_id)",
            "Duplicate supply proposal is not allowed.",
        )
    ]
    plan_id = fields.Many2one("mrp.advanced.plan", required=True, ondelete="cascade")
    requirement_id = fields.Many2one("mrp.advanced.requirement", ondelete="cascade")
    product_id = fields.Many2one("product.product", required=True)
    supply_type = fields.Selection(
        [
            ("available", "Available"),
            ("existing", "Existing supply"),
            ("make", "Make"),
            ("buy", "Buy"),
            ("blocked", "Blocked"),
        ],
        required=True,
    )
    quantity = fields.Float(required=True, digits=(16, 4))
    date_required = fields.Datetime(required=True)
    purchase_order_id = fields.Many2one("purchase.order")
    production_id = fields.Many2one("mrp.production")
    applied = fields.Boolean(default=False)
    logical_key = fields.Char(index=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("applied", "Applied"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        index=True,
    )
    production_proposal_id = fields.Many2one(
        "mrp.planning.production.proposal", ondelete="set null"
    )
    purchase_proposal_id = fields.Many2one(
        "mrp.planning.purchase.proposal", ondelete="set null"
    )
