from odoo import fields, models

class StockMove(models.Model):
    _inherit = "stock.move"
    is_reconditioning_return_component = fields.Boolean(string="Producto base de reacondicionamiento", copy=False, index=True)
