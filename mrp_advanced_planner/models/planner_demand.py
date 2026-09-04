from odoo import fields, models


class MrpAdvancedDemand(models.Model):
    _name = "mrp.advanced.demand"
    _description = "APS Demand"
    plan_id = fields.Many2one("mrp.advanced.plan", required=True, ondelete="cascade")
    origin = fields.Reference(
        [("sale.order", "Sales Order"), ("mrp.advanced.demand", "Manual Demand")],
        required=True,
    )
    sale_line_id = fields.Many2one("sale.order.line")
    product_id = fields.Many2one("product.product", required=True)
    warehouse_id = fields.Many2one(
        "stock.warehouse", related="plan_id.warehouse_id", store=True
    )
    quantity = fields.Float(required=True, digits=(16, 4))
    uom_id = fields.Many2one("uom.uom", required=True)
    date_required = fields.Datetime(required=True)
    priority = fields.Integer(default=10)
    qty_available = fields.Float(digits=(16, 4))
    qty_short = fields.Float(digits=(16, 4))
    state = fields.Selection(
        [("open", "Open"), ("covered", "Covered"), ("blocked", "Blocked")],
        default="open",
    )
