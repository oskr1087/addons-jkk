from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class StockMove(models.Model):
    _inherit = "stock.move"

    line_number = fields.Integer(
        compute="_compute_line_number",
        string="#",
    )

    location_internal_id = fields.Integer(
        compute="_compute_location_internal_id",
        string="Almacén",
    )

    @api.depends(
        "raw_material_production_id",
        "raw_material_production_id.move_raw_ids.sequence",
    )
    def _compute_line_number(self):
        for production in self.mapped("raw_material_production_id"):
            for i, move in enumerate(
                production.move_raw_ids.sorted("sequence"),
                start=1,
            ):
                move.line_number = i

    @api.depends("location_id")
    def _compute_location_internal_id(self):
        for move in self:
            move.location_internal_id = (
                move.location_id.id if move.location_id else False
            )

    def _action_done(self, cancel_backorder=False):

        for move in self:

            if (
                move.purchase_line_id
                and move.product_id
                and move.quantity
            ):

                purchase_line = move.purchase_line_id

                # Cantidad comprada
                ordered_qty = purchase_line.product_qty

                # Todo lo recibido anteriormente
                previous_received = sum(
                    purchase_line.move_ids.filtered(
                        lambda m:
                        m.state == "done"
                        and m.id != move.id
                    ).mapped("quantity")
                )

                total_received = previous_received + move.quantity


                if total_received > ordered_qty:

                    raise ValidationError(
                        _(
                            "No puede recibir más cantidad de la comprada.\n\n"
                            "Producto: %s\n"
                            "Cantidad solicitada: %s\n"
                            "Cantidad recibida anteriormente: %s\n"
                            "Cantidad que intenta recibir: %s\n"
                            "Total recibido: %s"
                        )
                        % (
                            move.product_id.display_name,
                            ordered_qty,
                            previous_received,
                            move.quantity,
                            total_received,
                        )
                    )

        return super()._action_done(cancel_backorder)