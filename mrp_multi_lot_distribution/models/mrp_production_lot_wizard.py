from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_round


class MrpProductionLotWizard(models.TransientModel):
    _name = "mrp.production.lot.wizard"
    _description = "Generar lotes de producción"

    production_id = fields.Many2one("mrp.production", required=True, readonly=True)
    workcenter_id = fields.Many2one(
        "mrp.workcenter", string="Centro de trabajo", required=True
    )
    lot_count = fields.Integer(string="Número de lotes", required=True, default=1)

    def action_generate(self):
        self.ensure_one()
        production = self.production_id
        if self.lot_count <= 0:
            raise UserError(_("El número de lotes debe ser mayor que cero."))
        if production.product_tracking != "lot":
            raise UserError(
                _(
                    "Este asistente solo está disponible para productos controlados por lotes."
                )
            )

        distribution = production._get_or_create_lot_distribution()
        distribution.line_ids.unlink()

        rounding = production.product_uom_id.rounding or 0.01
        total_quantity = float_round(
            production.qty_producing,
            precision_rounding=rounding,
        )
        base_quantity = float_round(
            total_quantity / self.lot_count,
            precision_rounding=rounding,
        )
        lot_model = self.env["stock.lot"]
        line_vals = []
        prefix = self.workcenter_id.label_prefix or self.workcenter_id.code or "GEN"
        sequence = self.env["ir.sequence"]
        accumulated = 0.0
        for index in range(self.lot_count):
            quantity = (
                float_round(
                    total_quantity - accumulated,
                    precision_rounding=rounding,
                )
                if index == self.lot_count - 1
                else base_quantity
            )
            accumulated += quantity
            lot_number = sequence.next_by_code("mrp.production.lot.sequence")
            lot = lot_model.create(
                {
                    "name": "%s%s" % (prefix, lot_number),
                    "product_id": production.product_id.id,
                    "company_id": production.company_id.id,
                }
            )
            line_vals.append(
                {
                    "distribution_id": distribution.id,
                    "lot_id": lot.id,
                    "quantity": quantity,
                }
            )
        self.env["mrp.production.lot.distribution.line"].create(line_vals)

        return distribution.action_open_distribution()

    def action_cancel(self):
        return {"type": "ir.actions.act_window_close"}

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        production_id = self.env.context.get("active_id") or vals.get("production_id")
        if production_id:
            production = self.env["mrp.production"].browse(production_id).exists()
            vals["production_id"] = production.id
            workcenter = production.workorder_ids[:1].workcenter_id
            if workcenter:
                vals["workcenter_id"] = workcenter.id
        return vals
