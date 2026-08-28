# -*- coding: utf-8 -*-
from odoo import api, models


class SetuInventoryCountViewRepairDiagnostics(models.AbstractModel):
    _name = "setu.inventory.count.view.repair.diagnostics"
    _description = "Diagnóstico técnico de vistas de conteo"

    @api.model
    def diagnostic_view_xmlids(self):
        names = [
            "setu_stock_inventory_count_form_view",
            "setu_stock_inventory_count_snapshot_form_extension",
            "setu_stock_inventory_count_form_modern",
        ]
        rows = self.env["ir.model.data"].sudo().search([
            ("module", "=", "setu_inventory_count_management"),
            ("name", "in", names),
            ("model", "=", "ir.ui.view"),
        ])
        return {
            row.name: {
                "view_id": row.res_id,
                "view_name": self.env["ir.ui.view"].sudo().browse(row.res_id).name,
            }
            for row in rows
        }
