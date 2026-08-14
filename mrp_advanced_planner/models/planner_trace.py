from odoo import fields, models

class MrpAdvancedAudit(models.Model):
    _name = 'mrp.advanced.audit'; _description = 'Trazabilidad de auditoría APS'; _order = 'create_date desc'
    plan_id = fields.Many2one('mrp.advanced.plan', required=True, ondelete='cascade'); user_id = fields.Many2one('res.users', default=lambda self: self.env.user)
    action = fields.Selection([('calculate','Calcular'),('approve','Aprobar'),('apply','Aplicar'),('rollback','Revertir')], required=True)
    model_name = fields.Char(); record_ref = fields.Char(); details = fields.Text()
