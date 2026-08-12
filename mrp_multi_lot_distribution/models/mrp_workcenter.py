from odoo import fields, models


class MrpWorkCenter(models.Model):
    _inherit = "mrp.workcenter"

    label_prefix = fields.Char(
        string="Prefijo de lote",
        size=5,
        help="Prefijo utilizado para generar los números de lote.",
    )
