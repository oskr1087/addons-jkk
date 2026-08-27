# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class SetuProductWiseDiscrepancyReport(models.Model):
    _name = "setu.product.wise.discrepancy.report"
    _description = "Product-wise Discrepancy Report"
    _auto = False

    product_id = fields.Many2one("product.product", string="Producto", readonly=True)
    total_times_counted = fields.Integer(string="Total Times Counted", readonly=True)
    discrepancy_products = fields.Integer(string="Productos con discrepancia", readonly=True)
    discrepancy_percent = fields.Float(string="% de discrepancia", readonly=True)
    company_id = fields.Many2one("res.company", string="Compañía", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)
        self._cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    MIN(l.id) AS id,
                    l.product_id AS product_id,
                    COUNT(DISTINCT l.id) AS total_times_counted,
                    SUM(CASE WHEN l.is_discrepancy_found = TRUE THEN 1 ELSE 0 END) AS discrepancy_products,
                    ROUND(
                        (SUM(CASE WHEN l.is_discrepancy_found = TRUE THEN 1 ELSE 0 END)::decimal /
                         NULLIF(COUNT(DISTINCT l.id),0)) * 100, 2
                    ) AS discrepancy_percent,
                    c.company_id AS company_id
                FROM setu_stock_inventory_count_line l
                JOIN setu_stock_inventory_count c ON c.id = l.inventory_count_id
                WHERE c.state NOT IN ('Rejected','Cancel')
                  AND l.state != 'Reject'
                GROUP BY l.product_id, c.company_id
            )
        """)
