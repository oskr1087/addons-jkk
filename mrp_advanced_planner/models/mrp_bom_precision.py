from odoo import fields, models


class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    # APS requires four decimal places in engineering factors.
    product_qty = fields.Float(digits=(16, 4))


class MrpBomLine(models.Model):
    _inherit = 'mrp.bom.line'

    # Preserve small structure factors such as 0.0025 instead of displaying/
    # treating them as 0.00 in the APS engineering chain.
    product_qty = fields.Float(digits=(16, 4))
