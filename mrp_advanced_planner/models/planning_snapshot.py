from odoo import fields, models


class PlanningSnapshot(models.Model):
    _name = "mrp.planning.snapshot"
    _description = "APS Application Snapshot"
    _order = "create_date desc"

    name = fields.Char(required=True, copy=False)
    plan_id = fields.Many2one(
        "mrp.planning.plan", required=True, ondelete="cascade", index=True
    )
    state = fields.Selection(
        [("created", "Created"), ("restored", "Restored")],
        default="created",
        required=True,
    )
    production_ids = fields.Many2many("mrp.production", string="Manufacturing Orders")
    purchase_ids = fields.Many2many("purchase.order", string="Purchase Orders")
    payload = fields.Json(default=dict)
    created_by = fields.Many2one(
        "res.users", default=lambda self: self.env.user, readonly=True
    )

    def action_restore(self):
        for snapshot in self:
            for production in snapshot.production_ids.filtered(
                lambda record: record.state not in ("done", "cancel")
            ):
                production.action_cancel()
            for purchase in snapshot.purchase_ids.filtered(
                lambda record: record.state not in ("done", "cancel")
            ):
                purchase.button_cancel()
            snapshot.state = "restored"
        return True
