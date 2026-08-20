from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    planning_delivery_date_manual = fields.Boolean(
        string="Fecha de planificación modificada manualmente",
        default=False,
        copy=False,
    )
    planning_delivery_date = fields.Datetime(
        string="Fecha de entrega planificación",
        compute="_compute_planning_delivery_date",
        inverse="_inverse_planning_delivery_date",
        store=True,
        readonly=False,
        precompute=True,
        index=True,
        copy=True,
        help=(
            "Fecha utilizada por el planificador de fabricación. Por defecto toma la "
            "Fecha de entrega del pedido de venta y puede modificarse por cada línea."
        ),
    )

    @api.depends(
        "order_id.commitment_date",
        "order_id.date_order",
        "planning_delivery_date_manual",
        "display_type",
    )
    def _compute_planning_delivery_date(self):
        for line in self:
            if line.display_type:
                line.planning_delivery_date = False
                continue
            if not line.planning_delivery_date_manual:
                line.planning_delivery_date = (
                    line.order_id.commitment_date
                    or line.order_id.date_order
                    or fields.Datetime.now()
                )

    def _inverse_planning_delivery_date(self):
        for line in self:
            if line.display_type:
                line.planning_delivery_date_manual = False
                continue
            default_date = line.order_id.commitment_date or line.order_id.date_order
            # Clearing the field restores the order-level default.
            if not line.planning_delivery_date:
                line.planning_delivery_date_manual = False
                line.planning_delivery_date = default_date or fields.Datetime.now()
            else:
                line.planning_delivery_date_manual = bool(
                    not default_date or line.planning_delivery_date != default_date
                )

    def action_reset_planning_delivery_date(self):
        for line in self.filtered(lambda row: not row.display_type):
            line.planning_delivery_date_manual = False
            line.planning_delivery_date = (
                line.order_id.commitment_date
                or line.order_id.date_order
                or fields.Datetime.now()
            )
        return True
