# -*- coding: utf-8 -*-
from odoo import models, fields

# User statistic report
class SetuInventorySessionUserReport(models.Model):
    _name = 'setu.inventory.session.user.report'
    _description = 'User-wise Inventory Count Report'
    _auto = False

    user_id = fields.Many2one("res.users", string="User")
    company_id = fields.Many2one("res.company", string="Compañía")

    total_sessions = fields.Integer(string="Total de sesiones")
    scanned_products = fields.Integer(string="Total de productos escaneados")
    accurate_products = fields.Integer(string="Accurate Products")
    discrepancy_products = fields.Integer(string="Mistake Products")
    accuracy_ratio = fields.Float(string="Accuracy Ratio (%)")
    discrepancy_ratio = fields.Float(string="Mistake Ratio (%)")
    avg_time_per_session = fields.Float(string="Tiempo promedio por sesión (min)")

    def init(self):
        self.env.cr.execute("""DROP VIEW IF EXISTS setu_inventory_session_user_report;""")
        self.env.cr.execute("""
         CREATE OR REPLACE VIEW setu_inventory_session_user_report AS (
            SELECT 
                row_number() OVER() as id,
                line_user_rel.res_users_id as user_id,
                sess.company_id as company_id,
        
                COUNT(DISTINCT sess.id) as total_sessions,
                COUNT(DISTINCT CASE WHEN line.product_scanned THEN line.id END) as scanned_products,
        
                COUNT(DISTINCT CASE WHEN line.user_calculation_mistake = FALSE THEN line.id END) as accurate_products,
                COUNT(DISTINCT CASE WHEN line.user_calculation_mistake = TRUE THEN line.id END) as discrepancy_products,
        
                (CASE WHEN COUNT(DISTINCT line.id) > 0 
                      THEN (COUNT(DISTINCT CASE WHEN line.user_calculation_mistake = FALSE THEN line.id END)::float 
                            / COUNT(DISTINCT line.id)::float) * 100
                      ELSE 0 END) as accuracy_ratio,
        
                (CASE WHEN COUNT(DISTINCT line.id) > 0 
                      THEN (COUNT(DISTINCT CASE WHEN line.user_calculation_mistake = TRUE THEN line.id END)::float 
                            / COUNT(DISTINCT line.id)::float) * 100
                      ELSE 0 END) as discrepancy_ratio,
        
                (CASE WHEN COUNT(DISTINCT sess.id) > 0
                      THEN SUM(COALESCE(details.duration_seconds,0))/60.0 / COUNT(DISTINCT sess.id)
                      ELSE 0 END) as avg_time_per_session
        
            FROM setu_inventory_count_session_line line
            INNER JOIN setu_inventory_count_session sess ON sess.id = line.session_id
            INNER JOIN res_users_setu_inventory_count_session_line_rel line_user_rel 
                ON line_user_rel.setu_inventory_count_session_line_id = line.id
            LEFT JOIN setu_inventory_session_details details
                ON details.session_id = sess.id
            WHERE sess.state IN ('Submitted','Done')
            AND sess.session_id is NULL
            GROUP BY line_user_rel.res_users_id, sess.company_id
            )
        """)
