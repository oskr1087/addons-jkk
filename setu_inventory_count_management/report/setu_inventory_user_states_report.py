# -*- coding: utf-8 -*-
from odoo import fields, models


class SetuInvUserStatesReport(models.TransientModel):
    _name = 'setu.inventory.user.states.report'
    _inherit = 'setu.inventory.reporting.template'
    _description = 'Inventory User Statistics Report'

    sessions = fields.Integer(string="Total de sesiones")
    mistake_sessions = fields.Integer(string="Mistake Sessions")

    discrepancy_ratio = fields.Float(string="Discrepancy")
    user_mistake_ratio = fields.Float(string="Calculation Mistake")
    company_id = fields.Many2one(comodel_name="res.company", string="Compañía")


    def get_user_inventory_stats(self):
        allowed_company = self._context.get('allowed_company_ids')

        inventory_count_model = self.env['setu.stock.inventory.count']
        inventory_counts = inventory_count_model.search(
            [('type', '=', 'Single Session'), ('warehouse_id.company_id', 'in', allowed_company)])

        global_user_data = {}
        for count_id in inventory_counts:
            count_session = {}
            for session in count_id.session_ids.filtered(lambda ses: ses.state == 'Done'):
                lines = session.session_line_ids
                users = lines.mapped('user_ids')
                count_session = self.get_total_count_and_mistake_count(users, lines, count_session)

            global_user_data = self.update_global_user_data(global_user_data, count_session,
                                                            count_id.warehouse_id.company_id.id)

        inventory_counts = inventory_count_model.search([('type', '=', 'Multi Session'), ('count_id', '=', False),
                                                         ('state', 'in', ['Approved','Inventory Adjusted']),
                                                         ('warehouse_id.company_id', 'in', allowed_company)])

        for count_id in inventory_counts:
            current = count_id
            total_count_ids = []

            while True:
                total_count_ids.append(current)
                if not current.count_ids:
                    break
                current = current.count_ids.filtered(lambda count: count.state in ['Approved','Inventory Adjusted'])

            stock_count = {}

            for count in total_count_ids:
                lines = count.line_ids
                users = lines.mapped('user_ids')

                stock_count = self.get_total_count_and_mistake_count(users, lines, stock_count)

            global_user_data = self.update_global_user_data(global_user_data, stock_count,
                                                            count_id.warehouse_id.company_id.id)

        for data in global_user_data.values():
            data['user_mistake_ratio'] = round((data['mistake_sessions'] / data['sessions']) * 100, 2) if data[
                'sessions'] else 0.0

        return list(global_user_data.values())

    def get_total_count_and_mistake_count(self, users, lines, count_session):
        for user in users:
            user_lines = lines.filtered(lambda l: user in l.user_ids)
            product_ids = user_lines.mapped('product_id')
            states = user_lines.mapped('state')

            if user.id not in count_session:
                count_session[user.id] = {
                    'user_id': user.id,
                    'user': user,
                    'product_ids': self.env['product.product'],
                    'total_count': 0,
                    'mistake_count': 0,
                }

            existing_products = count_session[user.id]['product_ids']
            new_products = product_ids - existing_products

            if new_products:
                count_session[user.id]['product_ids'] |= new_products
                count_session[user.id]['total_count'] += 1

            if new_products and 'Reject' in states:
                count_session[user.id]['mistake_count'] += 1

        return count_session

    def update_global_user_data(self, global_user_data, session_data, company_id=None):
        for user_id, data in session_data.items():
            if user_id not in global_user_data:
                global_user_data[user_id] = {
                    'user_id': data['user_id'],
                    'sessions': 0,
                    'mistake_sessions': 0,
                    'company_id': company_id
                }
            global_user_data[user_id]['sessions'] += data['total_count']
            global_user_data[user_id]['mistake_sessions'] += data['mistake_count']

        return global_user_data

    # def generate_report(self):
    #     self.sudo().search([]).unlink()
    #     report_data = self.get_user_inventory_stats()
    #     self.create(report_data)
    #
    #     action = self.env.ref('setu_inventory_count_management.setu_inventory_user_states_report_action').read()[0]
    #     return action


    def generate_report(self):
        self.sudo().search([]).unlink()
        report_data = self.get_user_inventory_stats()
        if isinstance(report_data, dict):
            self.create([report_data])
        elif isinstance(report_data, list):
            self.create(report_data)
        else:
            raise ValueError("get_user_inventory_stats must return dict or list of dicts")
        action = self.env.ref('setu_inventory_count_management.setu_inventory_user_states_report_action').read()[0]
        return action
