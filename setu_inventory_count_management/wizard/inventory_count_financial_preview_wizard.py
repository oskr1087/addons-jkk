# -*- coding: utf-8 -*-
from odoo import fields, models, _


class InventoryCountFinancialPreviewWizard(models.TransientModel):
    _name = "setu.inventory.count.financial.preview.wizard"
    _description = "Vista previa económica del ajuste"

    count_id = fields.Many2one("setu.stock.inventory.count", readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)
    expected_value = fields.Monetary(
        string="Valor base del inventario", currency_field="currency_id", readonly=True
    )
    shortage_value = fields.Monetary(
        string="Faltantes valorizados", currency_field="currency_id", readonly=True
    )
    surplus_value = fields.Monetary(
        string="Sobrantes valorizados", currency_field="currency_id", readonly=True
    )
    net_adjustment_value = fields.Monetary(
        string="Impacto neto estimado", currency_field="currency_id", readonly=True
    )
    adjustment_candidate_count = fields.Integer(
        string="Líneas previstas para ajuste", readonly=True
    )
    high_impact_item_count = fields.Integer(
        string="Líneas de alto impacto", readonly=True
    )
    preview_line_ids = fields.Many2many(
        "setu.inventory.count.snapshot.line",
        "setu_fin_preview_line_rel",
        "wizard_id",
        "snapshot_line_id",
        string="Vista previa de líneas",
        readonly=True,
    )

    def action_open_lines(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Líneas de la vista previa del ajuste"),
            "res_model": "setu.inventory.count.snapshot.line",
            "view_mode": "list",
            "domain": [("id", "in", self.preview_line_ids.ids)],
            "context": {"create": False, "delete": False},
        }
