from odoo import fields, models
class MrpAdvancedPlannerWizard(models.TransientModel):
    _name = 'mrp.planning.planner.wizard'; _description = 'APS Planner Wizard'
    plan_id = fields.Many2one('mrp.planning.plan', required=True)
    action = fields.Selection([('calculate','Calculate'),('approve','Approve'),('apply','Apply')], default='calculate', required=True)
    def action_execute(self):
        self.ensure_one()
        getattr(self.plan_id, f'action_{self.action}')()
        return {'type':'ir.actions.act_window_close'}
