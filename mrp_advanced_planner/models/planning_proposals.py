from odoo import api, fields, models


class PlanningProductionProposal(models.Model):
    _name = 'mrp.planning.production.proposal'
    _description = 'APS Production Proposal'
    _order = 'date_required, id'

    _proposal_key_unique = models.Constraint(
        'UNIQUE(plan_id, product_id, date_required)',
        'A production proposal already exists for this plan, product and date.',
    )

    name = fields.Char(required=True, default='New')
    plan_id = fields.Many2one('mrp.planning.plan', required=True, ondelete='cascade', index=True)
    supply_ids = fields.One2many('mrp.planning.supply', 'production_proposal_id')
    product_id = fields.Many2one('product.product', required=True, index=True)
    bom_id = fields.Many2one('mrp.bom')
    company_id = fields.Many2one(related='plan_id.company_id', store=True)
    warehouse_id = fields.Many2one(related='plan_id.warehouse_id', store=True)
    quantity = fields.Float(required=True, digits=(16, 4))
    product_uom_id = fields.Many2one(related='product_id.uom_id', store=True)
    date_required = fields.Datetime(required=True, index=True)
    date_planned_start = fields.Datetime()
    date_planned_finished = fields.Datetime()
    total_duration = fields.Float(digits=(16, 4))
    priority = fields.Selection(related='plan_id.priority', store=True)
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'), ('applied', 'Applied'), ('cancelled', 'Cancelled')], default='draft', index=True)
    production_id = fields.Many2one('mrp.production', copy=False, index=True)
    origin = fields.Char()

    @api.depends('product_id', 'date_required')
    def _compute_name(self):
        for record in self:
            record.name = '%s - %s' % (record.product_id.display_name, fields.Datetime.to_string(record.date_required)) if record.product_id and record.date_required else 'New'


class PlanningPurchaseProposal(models.Model):
    _name = 'mrp.planning.purchase.proposal'
    _description = 'APS Purchase Proposal'
    _order = 'date_required, id'

    _proposal_key_unique = models.Constraint(
        'UNIQUE(plan_id, product_id, vendor_id, date_required)',
        'A purchase proposal already exists for this plan, product, vendor and date.',
    )

    name = fields.Char(required=True, default='New')
    plan_id = fields.Many2one('mrp.planning.plan', required=True, ondelete='cascade', index=True)
    supply_ids = fields.One2many('mrp.planning.supply', 'purchase_proposal_id')
    product_id = fields.Many2one('product.product', required=True, index=True)
    vendor_id = fields.Many2one('res.partner', required=True, index=True)
    supplierinfo_id = fields.Many2one('product.supplierinfo')
    company_id = fields.Many2one(related='plan_id.company_id', store=True)
    warehouse_id = fields.Many2one(related='plan_id.warehouse_id', store=True)
    quantity = fields.Float(required=True, digits=(16, 4))
    product_uom_id = fields.Many2one(related='product_id.uom_id', store=True)
    date_required = fields.Datetime(required=True, index=True)
    date_planned = fields.Datetime()
    price_unit = fields.Float(digits=(16, 4))
    currency_id = fields.Many2one(related='company_id.currency_id', store=True)
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'), ('applied', 'Applied'), ('cancelled', 'Cancelled')], default='draft', index=True)
    purchase_order_id = fields.Many2one('purchase.order', copy=False, index=True)
    origin = fields.Char()
