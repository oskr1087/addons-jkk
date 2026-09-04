from odoo import api, fields, models
from odoo.exceptions import UserError


class PhysicalRoll(models.Model):
    _name = 'mrp.physical.roll'
    _description = 'Physically Occupied Roll'
    _order = 'state, name'

    name = fields.Char(required=True, index=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    product_id = fields.Many2one('product.product', required=True, index=True)
    lot_id = fields.Many2one('stock.lot', index=True)
    location_id = fields.Many2one('stock.location', index=True)
    workcenter_id = fields.Many2one('mrp.workcenter', index=True)
    physical_qty = fields.Float(required=True, digits=(16, 4))
    reserved_qty = fields.Float(default=0.0, digits=(16, 4))
    assigned_qty = fields.Float(default=0.0, digits=(16, 4))
    available_qty = fields.Float(compute='_compute_available', store=True, digits=(16, 4))
    assignment_ids = fields.One2many('mrp.physical.roll.assignment', 'roll_id')
    cut_ids = fields.One2many('mrp.physical.roll.cut', 'roll_id')
    assigned_qty_total = fields.Float(compute='_compute_assignment_totals', store=True, digits=(16, 4))
    waste_qty_total = fields.Float(compute='_compute_assignment_totals', store=True, digits=(16, 4))
    mounted_at = fields.Datetime(copy=False)
    released_at = fields.Datetime(copy=False)
    state = fields.Selection([('available', 'Available'), ('reserved', 'Reserved'), ('mounted', 'Mounted'), ('consumed', 'Consumed'), ('released', 'Released')], default='available', required=True, index=True)

    @api.depends('physical_qty', 'reserved_qty', 'assigned_qty', 'state')
    def _compute_available(self):
        for record in self:
            record.available_qty = max(record.physical_qty - record.reserved_qty - record.assigned_qty, 0.0) if record.state not in ('mounted', 'consumed', 'released') else 0.0

    @api.depends('assignment_ids.quantity', 'assignment_ids.consumed_qty', 'assignment_ids.waste_qty')
    def _compute_assignment_totals(self):
        for record in self:
            active = record.assignment_ids.filtered(lambda item: item.state != 'released')
            record.assigned_qty_total = sum(active.mapped('quantity'))
            record.waste_qty_total = sum(record.assignment_ids.mapped('waste_qty'))

    def _sync_assignment_state(self):
        for record in self:
            if record.state in ('mounted', 'released'):
                continue
            active = record.assignment_ids.filtered(lambda item: item.state in ('reserved', 'assigned', 'consumed'))
            if active and all(item.state == 'consumed' for item in active):
                record.state = 'consumed'
            elif active:
                record.state = 'reserved'
            else:
                record.state = 'available'

    def action_mount(self):
        self.ensure_one()
        if self.state in ('consumed', 'released'):
            return False
        self.write({'state': 'mounted', 'mounted_at': fields.Datetime.now()})
        return True

    def action_release(self):
        self.ensure_one()
        if self.assignment_ids.filtered(lambda item: item.state in ('assigned', 'consumed')):
            raise UserError('A roll with active assignments cannot be released.')
        self.write({'state': 'released', 'workcenter_id': False, 'released_at': fields.Datetime.now()})
        return True

    def action_unmount(self):
        self.ensure_one()
        if self.state != 'mounted':
            return False
        self.write({'state': 'available', 'workcenter_id': False})
        return True

    def action_reserve(self, quantity, plan=False, production=False, workcenter=False):
        self.ensure_one()
        if quantity <= 0 or quantity > self.available_qty:
            raise UserError('The requested roll quantity is not available.')
        assignment = self.env['mrp.physical.roll.assignment'].create({'roll_id': self.id, 'plan_id': plan.id if plan else False, 'production_id': production.id if production else False, 'workcenter_id': workcenter.id if workcenter else False, 'quantity': quantity})
        self.reserved_qty += quantity
        self.state = 'reserved'
        return assignment
