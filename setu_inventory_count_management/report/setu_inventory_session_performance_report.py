# -*- coding: utf-8 -*-
from odoo import fields, models, tools

# session performance report
class SetuInventorySessionPerformanceReport(models.Model):
    _name = 'setu.inventory.session.performance.report'
    _description = 'Session Performance Report'
    _auto = False

    count_id = fields.Many2one("setu.stock.inventory.count", string="Conteo")
    session_id = fields.Many2one("setu.inventory.count.session", string="Sesión")

    session_start = fields.Datetime("Session Start")
    session_end = fields.Datetime("Session End")
    duration = fields.Float("Duration (hrs)")

    total_products_assigned = fields.Integer("Total Products Assigned")
    total_products_counted = fields.Integer("Total Products Counted")
    users_involved = fields.Integer("Users Involved")

    avg_time_per_product = fields.Float("Avg Time Per Product (hrs)")
    accuracy_ratio = fields.Float("Accuracy Ratio (%)")
    company_id = fields.Many2one("res.company", string="Compañía", readonly=True)
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    sess.id as id,
                    sess.inventory_count_id as count_id,
                    sess.id as session_id,
                    sess.session_start_date as session_start,
                    sess.session_submit_date as session_end,

                    COALESCE(SUM(details.duration_seconds),0)/3600.0 as duration,
                    sess.total_products as total_products_assigned,
                    sess.total_scanned_products as total_products_counted,
                    COALESCE(COUNT(DISTINCT user_rel.user_id),0) as users_involved,
                    sess.company_id AS company_id,
                    CASE 
                        WHEN sess.total_scanned_products > 0 
                        THEN (COALESCE(SUM(details.duration_seconds),0)/3600.0) / NULLIF(sess.total_scanned_products,0)
                        ELSE 0 
                    END as avg_time_per_product,
                    CASE 
                        WHEN sess.total_products > 0 
                        THEN (COUNT(CASE WHEN line.difference_qty = 0 THEN 1 END)::float / 
                              NULLIF(COUNT(line.id),0)) * 100
                        ELSE 0 END as accuracy_ratio

                FROM setu_inventory_count_session sess
                JOIN setu_stock_inventory_count count_doc
                    ON count_doc.id = sess.inventory_count_id
                LEFT JOIN setu_inventory_session_details details 
                    ON details.session_id = sess.id
                LEFT JOIN setu_inventory_count_session_line line 
                    ON line.session_id = sess.id
                LEFT JOIN setu_inventory_count_session_user_rel user_rel
                    ON user_rel.session_id = sess.id

                WHERE sess.state IN ('Submitted','Done')
                  AND count_doc.count_id IS NULL

                GROUP BY sess.id, sess.company_id
            )
        """)
