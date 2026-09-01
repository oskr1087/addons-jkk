from odoo import api, fields, models
from odoo.exceptions import UserError


class PhysicalRollAssignment(models.Model):
    _name = 'mrp.physical.roll.assignment'
    _description = 'Physical Roll Assignment'
    _order = 'date_assigned desc, id desc'

    roll_id = fields.Many2one('mrp.physical.roll', required=True, ondelete='cascade', index=True)
    plan_id = fields.Many2one('mrp.planning.plan', index=True, ondelete='set null')
    production_id = fields.Many2one('mrp.production', index=True, ondelete='set null')
    workcenter_id = fields.Many2one('mrp.workcenter', index=True)
    quantity = fields.Float(required=True)
    consumed_qty = fields.Float(default=0.0)
    waste_qty = fields.Float(default=0.0)
    remaining_qty = fields.Float(compute='_compute_remaining', store=True)
    state = fields.Selection([('reserved', 'Reserved'), ('assigned', 'Assigned'), ('consumed', 'Consumed'), ('released', 'Released')], default='reserved', required=True, index=True)
    date_assigned = fields.Datetime(default=fields.Datetime.now, required=True)
    date_released = fields.Datetime()
    note = fields.Text()

    @api.depends('quantity', 'consumed_qty', 'waste_qty')
    def _compute_remaining(self):
        for assignment in self:
            assignment.remaining_qty = max(assignment.quantity - assignment.consumed_qty - assignment.waste_qty, 0.0)

    def action_assign(self):
        self.write({'state': 'assigned'})
        return True

    def action_release(self):
        for assignment in self:
            if assignment.state == 'consumed':
                raise UserError('Consumed roll assignments cannot be released.')
            assignment.write({'state': 'released', 'date_released': fields.Datetime.now()})
        return True

    def action_consume(self):
        for assignment in self:
            if assignment.state == 'released':
                raise UserError('Released roll assignments cannot be consumed.')
            assignment.write({'state': 'consumed', 'consumed_qty': assignment.quantity - assignment.waste_qty})
            assignment.roll_id._sync_assignment_state()
        return True

    def action_record_waste(self, quantity):
        for assignment in self:
            if quantity < 0 or quantity > assignment.quantity - assignment.consumed_qty:
                raise UserError('Waste quantity exceeds the remaining assigned quantity.')
            assignment.waste_qty += quantity
        return True

    _positive_quantity = models.Constraint(
        'CHECK(quantity > 0)',
        'Assignment quantity must be positive.',
    )
    _non_negative_consumed = models.Constraint(
        'CHECK(consumed_qty >= 0 AND waste_qty >= 0)',
        'Consumed and waste quantities cannot be negative.',
    )


class PhysicalRollCut(models.Model):
    _name = 'mrp.physical.roll.cut'
    _description = 'Physical Roll Cut'
    _order = 'create_date desc, id desc'

    roll_id = fields.Many2one('mrp.physical.roll', required=True, ondelete='cascade', index=True)
    assignment_id = fields.Many2one('mrp.physical.roll.assignment', ondelete='set null', index=True)
    product_id = fields.Many2one(related='roll_id.product_id', store=True)
    quantity = fields.Float(required=True)
    waste_qty = fields.Float(default=0.0)
    production_id = fields.Many2one('mrp.production', index=True, ondelete='set null')
    note = fields.Text()

    _positive_quantity = models.Constraint(
        'CHECK(quantity > 0)',
        'Cut quantity must be positive.',
    )
    _non_negative_waste = models.Constraint(
        'CHECK(waste_qty >= 0)',
        'Waste quantity cannot be negative.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for cut in records:
            if cut.assignment_id:
                cut.assignment_id.consumed_qty += cut.quantity
                cut.assignment_id.waste_qty += cut.waste_qty
                cut.assignment_id.roll_id._sync_assignment_state()
        return records
