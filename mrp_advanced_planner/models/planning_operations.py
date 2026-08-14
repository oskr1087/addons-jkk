from odoo import api, fields, models


class PlanningOperation(models.Model):
    _name = 'mrp.planning.operation'
    _description = 'APS Planned Operation'
    _order = 'workcenter_id, date_start, sequence, id'

    plan_id = fields.Many2one('mrp.planning.plan', required=True, ondelete='cascade', index=True)
    production_proposal_id = fields.Many2one('mrp.planning.production.proposal', ondelete='cascade', index=True)
    product_id = fields.Many2one('product.product', required=True, index=True)
    bom_operation_id = fields.Many2one('mrp.routing.workcenter', ondelete='set null')
    workcenter_id = fields.Many2one('mrp.workcenter', required=True, index=True)
    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    quantity = fields.Float(default=1.0)
    duration = fields.Float(help='Processing duration in hours.')
    setup_duration = fields.Float(help='Setup duration in hours.')
    date_start = fields.Datetime(index=True)
    date_end = fields.Datetime(index=True)
    state = fields.Selection([('planned', 'Planned'), ('conflict', 'Conflict'), ('cancelled', 'Cancelled')], default='planned', index=True)
    load_hours = fields.Float(compute='_compute_load_hours', store=True)
    calendar_id = fields.Many2one(related='workcenter_id.resource_calendar_id', store=True)
    conflict_ids = fields.One2many('mrp.planning.conflict', 'operation_id')

    @api.depends('duration', 'setup_duration')
    def _compute_load_hours(self):
        for operation in self:
            operation.load_hours = operation.duration + operation.setup_duration

    def action_mark_conflict(self):
        self.write({'state': 'conflict'})
        return True


class PlanningWorkcenterLoad(models.Model):
    _name = 'mrp.planning.workcenter.load'
    _description = 'APS Workcenter Capacity Load'
    _order = 'date_start, workcenter_id'

    plan_id = fields.Many2one('mrp.planning.plan', required=True, ondelete='cascade', index=True)
    workcenter_id = fields.Many2one('mrp.workcenter', required=True, index=True)
    date_start = fields.Datetime(required=True, index=True)
    date_end = fields.Datetime(required=True, index=True)
    available_hours = fields.Float()
    load_hours = fields.Float()
    utilization = fields.Float(compute='_compute_utilization', store=True)
    state = fields.Selection([('ok', 'Available'), ('warning', 'Warning'), ('overloaded', 'Overloaded')], compute='_compute_state', store=True)

    @api.depends('load_hours', 'available_hours')
    def _compute_utilization(self):
        for load in self:
            load.utilization = load.load_hours / load.available_hours if load.available_hours else 0.0

    @api.depends('utilization')
    def _compute_state(self):
        for load in self:
            load.state = 'overloaded' if load.utilization > 1.0 else 'warning' if load.utilization >= 0.85 else 'ok'
