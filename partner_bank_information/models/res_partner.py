# -*- coding: utf-8 -*-

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    bank_name = fields.Char(
        string="Banco",
    )

    bank_branch = fields.Char(
        string="Sucursal del Banco",
    )

    bank_account = fields.Char(
        string="Número de Cuenta",
    )

    bank_iban = fields.Char(
        string="IBAN",
    )

    payment_method_id = fields.Many2one(
        comodel_name="contact.payment.method",
        string="Método de Pago",
        ondelete="restrict",
    )