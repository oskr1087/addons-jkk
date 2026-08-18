from odoo import models


class StockQuant(models.Model):
    _inherit = "stock.quant"

    # warehouse_id already exists in Odoo 19 as a related field from location_id.
    # We deliberately reuse it instead of creating a duplicate field.
