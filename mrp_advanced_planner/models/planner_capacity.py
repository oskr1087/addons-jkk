from odoo import fields, models

class MrpAdvancedOperation(models.Model):
    _name = 'mrp.advanced.operation'; _description = 'Finite Capacity Operation'
    plan_id = fields.Many2one('mrp.advanced.plan', required=True, ondelete='cascade'); production_id = fields.Many2one('mrp.production')
    workcenter_id = fields.Many2one('mrp.workcenter', required=True); product_id = fields.Many2one('product.product')
    name = fields.Char(required=True); date_start = fields.Datetime(required=True); date_end = fields.Datetime(required=True)
    duration = fields.Float(); setup_duration = fields.Float(); sequence = fields.Integer(); state = fields.Selection([('planned','Planned'),('conflict','Conflict'),('done','Done')], default='planned')

class MrpAdvancedRoll(models.Model):
    _name = 'mrp.advanced.roll'; _description = 'Physical Roll Availability'
    name = fields.Char(required=True); product_id = fields.Many2one('product.product', required=True); lot_id = fields.Many2one('stock.lot')
    length = fields.Float(); width = fields.Float(); reserved_length = fields.Float(default=0); plan_id = fields.Many2one('mrp.advanced.plan')
    available_length = fields.Float(compute='_compute_available', store=True)
    @fields.depends('length','reserved_length')
    def _compute_available(self):
        for rec in self: rec.available_length = max(rec.length - rec.reserved_length, 0)
