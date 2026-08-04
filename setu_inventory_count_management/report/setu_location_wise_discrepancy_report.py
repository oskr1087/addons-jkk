# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class SetuLocationWiseDiscrepancyReport(models.Model):
    _name = "setu.location.wise.discrepancy.report"
    _description = "Location-wise Discrepancy Report"
    _auto = False

    location_id = fields.Many2one("stock.location", string="Location", readonly=True)
    total_products_counted = fields.Integer(string="Total Products Counted", readonly=True)
    total_discrepancy_lines = fields.Integer(string="Discrepancy Products", readonly=True)
    discrepancy_percent = fields.Float(string="Discrepancy %", readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)
        self._cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    MIN(l.id) AS id,
                    l.location_id AS location_id,
                    COUNT(l.id) AS total_products_counted,
                    SUM(CASE WHEN l.is_discrepancy_found = TRUE THEN 1 ELSE 0 END) AS total_discrepancy_lines,
                    ROUND(
                        (SUM(CASE WHEN l.is_discrepancy_found = TRUE THEN 1 ELSE 0 END)::decimal /
                         NULLIF(COUNT(l.id),0)) * 100, 2
                    ) AS discrepancy_percent,
                    c.company_id AS company_id
                FROM setu_stock_inventory_count_line l
                JOIN setu_stock_inventory_count c ON c.id = l.inventory_count_id
                WHERE c.state NOT IN ('Rejected','Cancel')
                  AND l.state != 'Reject'
                GROUP BY l.location_id, c.company_id
            )
        """)
