from odoo import api, fields, models


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
