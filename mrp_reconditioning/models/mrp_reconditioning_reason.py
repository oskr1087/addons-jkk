from odoo import fields, models


class MrpReconditioningReason(models.Model):
    _name = "mrp.reconditioning.reason"
    _description = "Motivo de reacondicionamiento"
    _order = "sequence, name"

    name = fields.Char(string="Nombre", required=True, translate=True)
    sequence = fields.Integer(string="Secuencia", default=10)
    active = fields.Boolean(string="Activo", default=True)
    description = fields.Text(string="Descripción")
