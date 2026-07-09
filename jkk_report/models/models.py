# from odoo import models, fields, api


# class jkk_report(models.Model):
#     _name = 'jkk_report.jkk_report'
#     _description = 'jkk_report.jkk_report'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100

