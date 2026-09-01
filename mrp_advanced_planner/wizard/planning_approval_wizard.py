from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MrpPlanningApprovalWizard(models.TransientModel):
    _name = 'mrp.planning.approval.wizard'
    _description = 'Resumen de aprobación de planificación'

    plan_id = fields.Many2one('mrp.planning.plan', required=True, readonly=True)
    product_count = fields.Integer(compute='_compute_summary', string='Líneas a fabricar')
    total_qty = fields.Float(compute='_compute_summary', string='Cantidad total')
    production_count = fields.Integer(compute='_compute_summary', string='Órdenes de fabricación')

    @api.depends('plan_id', 'plan_id.line_ids.planned_production_qty')
    def _compute_summary(self):
        for wizard in self:
            lines = wizard.plan_id.line_ids.filtered(lambda line: line.planned_production_qty > 0)
            wizard.product_count = len(lines)
            wizard.total_qty = sum(lines.mapped('planned_production_qty'))
            wizard.production_count = len(lines)

    def action_confirm(self):
        self.ensure_one()
        if not self.plan_id:
            raise UserError(_('No existe una planificación para aprobar.'))
        productions = self.plan_id._approve_and_create_productions()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Órdenes de fabricación creadas'),
            'res_model': 'mrp.production',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', productions.ids)],
            'target': 'current',
        }
