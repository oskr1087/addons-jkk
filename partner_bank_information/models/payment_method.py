# -*- coding: utf-8 -*-

from odoo import fields, models


class ContactPaymentMethod(models.Model):
    _name = "contact.payment.method"
    _description = "Contact Payment Method"
    _order = "name"
    _rec_name = "name"

    name = fields.Char(
        string="Método de Pago",
        required=True,
        translate=True,
    )

    _sql_constraints = [
        (
            "contact_payment_method_name_uniq",
            "unique(name)",
            "The payment method already exists.",
        ),
    ]