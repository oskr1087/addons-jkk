# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class SetuCountWiseDiscrepancyReport(models.Model):
    _name = "setu.count.wise.discrepancy.report"
    _description = "Count-wise Discrepancy Report"
    _auto = False

    count_id = fields.Many2one("setu.stock.inventory.count", string="Inventory Count", readonly=True)
    total_count_lines = fields.Integer(string="Total de productos contados", readonly=True)
    discrepancy_lines = fields.Integer(string="Productos con discrepancia", readonly=True)
    discrepancy_percent = fields.Float(string="% de discrepancia", readonly=True)
    company_id = fields.Many2one("res.company", string="Compañía", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)
        self._cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    c.id AS id,
                    c.id AS count_id,
                    COUNT(l.id) AS total_count_lines,
                    SUM(CASE WHEN l.is_discrepancy_found = TRUE THEN 1 ELSE 0 END) AS discrepancy_lines,
                    ROUND(
                        (SUM(CASE WHEN l.is_discrepancy_found = TRUE THEN 1 ELSE 0 END)::decimal /
                         NULLIF(COUNT(l.id),0)) * 100, 2
                    ) AS discrepancy_percent,
                    c.company_id AS company_id
                FROM setu_stock_inventory_count c
                JOIN setu_stock_inventory_count_line l ON l.inventory_count_id = c.id
                WHERE c.state NOT IN ('Rejected','Cancel')
                  AND l.state != 'Reject'
                GROUP BY c.id, c.company_id
            )
        """)
