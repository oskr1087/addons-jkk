from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    estimated_payment_date = fields.Date(
        string="Fecha Teórica de Pago",
        compute="_compute_estimated_payment_date",
    )

    @api.depends("date_order", "partner_id")
    def _compute_estimated_payment_date(self):
        for order in self:
            order.estimated_payment_date = False

            payment_term = order.partner_id.property_supplier_payment_term_id
            if not payment_term or not order.date_order:
                continue

            days = max(payment_term.line_ids.mapped("days") or [0])

            order.estimated_payment_date = fields.Date.to_date(
                order.date_order
            ) + relativedelta(days=days)
