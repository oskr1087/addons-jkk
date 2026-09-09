from odoo import api, fields, models

class StockWarehouseProductCost(models.Model):
    _name = "stock.warehouse.product.cost"
    _description = "Costo de producto por almacén"
    _order = "warehouse_id, product_id"

    warehouse_id = fields.Many2one("stock.warehouse", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="warehouse_id.company_id", store=True)
    product_id = fields.Many2one("product.product", required=True, ondelete="cascade", index=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    cost_method = fields.Selection(related="warehouse_id.warehouse_cost_method", store=True)
    quantity = fields.Float(readonly=True)
    total_value = fields.Monetary(currency_field="currency_id", readonly=True)
    standard_cost = fields.Monetary(currency_field="currency_id")
    average_cost = fields.Monetary(currency_field="currency_id", compute="_compute_average_cost")

    _unique_cost = models.Constraint(
        "UNIQUE(warehouse_id, product_id)",
        "Solo puede existir un costo por producto y almacén.",
    )

    @api.depends("quantity", "total_value", "standard_cost", "cost_method")
    def _compute_average_cost(self):
        for rec in self:
            rec.average_cost = rec.standard_cost if rec.cost_method == "standard" else (
                rec.total_value / rec.quantity if rec.quantity else 0.0
            )

class StockWarehouseCostLayer(models.Model):
    _name = "stock.warehouse.cost.layer"
    _description = "Capa FIFO por almacén"
    _order = "date, id"

    warehouse_id = fields.Many2one("stock.warehouse", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="warehouse_id.company_id", store=True)
    product_id = fields.Many2one("product.product", required=True, ondelete="cascade", index=True)
    move_id = fields.Many2one("stock.move", ondelete="set null", index=True)
    date = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    original_qty = fields.Float(required=True)
    remaining_qty = fields.Float(required=True)
    unit_cost = fields.Float(required=True, digits="Product Price")
