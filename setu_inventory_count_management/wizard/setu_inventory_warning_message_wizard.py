# -*- coding: utf-8 -*-
from odoo import fields, models


class SetuWarningMSGWizard(models.TransientModel):
    _name = 'setu.inventory.warning.message.wizard'
    _description = 'Inventory Warning Message Wizard'

    message = fields.Char(string="Message")

    def approve(self):
        session_id = self.env['setu.inventory.count.session'].browse(self.env.context.get('active_id', False))
        for line in session_id.session_line_ids:
            line.state = 'Approve'
        session_id.is_session_approved = True

    def approve_count_lines(self):
        count_id = self.env['setu.stock.inventory.count'].browse(self.env.context.get('active_id', False))
        for line in count_id.line_ids:
            line.state = 'Approve'

    def reject(self):
        session_id = self.env['setu.inventory.count.session'].browse(self.env.context.get('active_id', False))
        for line in session_id.session_line_ids:
            line.state = 'Reject'
        session_id.is_session_approved = False

    def reject_count_lines(self):
        count_id = self.env['setu.stock.inventory.count'].browse(self.env.context.get('active_id', False))
        for line in count_id.line_ids:
            line.state = 'Reject'
