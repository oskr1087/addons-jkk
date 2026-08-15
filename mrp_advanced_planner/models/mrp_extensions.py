from odoo import fields, models, _


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    advanced_plan_id = fields.Many2one('mrp.planning.plan', string='Planificación de origen', index=True, copy=False, readonly=True)
    planning_plan_line_id = fields.Many2one('mrp.planning.plan.line', string='Línea de planificación', index=True, copy=False, readonly=True)
    planning_sale_line_id = fields.Many2one('sale.order.line', string='Línea de venta origen', index=True, copy=False, readonly=True)
    planning_production_proposal_id = fields.Many2one('mrp.planning.production.proposal', string='Propuesta de planificación', index=True, copy=False, readonly=True)

    def action_open_advanced_plan(self):
        self.ensure_one()
        if not self.advanced_plan_id:
            return False
        return {
            'type': 'ir.actions.act_window', 'name': _('Planificación de origen'),
            'res_model': 'mrp.planning.plan', 'view_mode': 'form', 'views': [(False, 'form')],
            'res_id': self.advanced_plan_id.id, 'target': 'current',
        }


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    advanced_plan_id = fields.Many2one('mrp.planning.plan', string='Planificación de origen', index=True, copy=False, readonly=True)

    def action_open_advanced_plan(self):
        self.ensure_one()
        if not self.advanced_plan_id:
            return False
        return {
            'type': 'ir.actions.act_window', 'name': _('Planificación de origen'),
            'res_model': 'mrp.planning.plan', 'res_id': self.advanced_plan_id.id,
            'view_mode': 'form', 'views': [(False, 'form')], 'target': 'current',
        }


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    planning_plan_line_id = fields.Many2one('mrp.planning.plan.line', string='Línea de planificación', index=True, copy=False, readonly=True)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    advanced_plan_id = fields.Many2one('mrp.planning.plan', string='Planificación de origen', index=True, copy=False, readonly=True)

    def action_open_advanced_plan(self):
        self.ensure_one()
        if not self.advanced_plan_id:
            return False
        return {
            'type': 'ir.actions.act_window', 'name': _('Planificación de origen'),
            'res_model': 'mrp.planning.plan', 'res_id': self.advanced_plan_id.id,
            'view_mode': 'form', 'views': [(False, 'form')], 'target': 'current',
        }


class StockMove(models.Model):
    _inherit = 'stock.move'

    planning_plan_line_id = fields.Many2one('mrp.planning.plan.line', string='Línea de planificación', index=True, copy=False, readonly=True)


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    planning_operation_id = fields.Many2one('mrp.planning.operation', copy=False)
