from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PlanningPlan(models.Model):
    _name = 'mrp.planning.plan'
    _description = 'Planificador simple de órdenes de fabricación'
    _order = 'date_end desc, id desc'

    name = fields.Char(required=True, copy=False, default='New')
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company, index=True
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse', required=True,
        default=lambda self: self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1
        ),
        index=True,
    )
    user_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user)
    date_start = fields.Datetime(required=True, default=fields.Datetime.now)
    date_end = fields.Datetime(string='Fabricar hasta', required=True)
    priority = fields.Selection(
        [('0', 'Normal'), ('1', 'Alta'), ('2', 'Urgente')], default='0', required=True
    )
    # cancelled is kept only for compatibility with plans created by previous versions.
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('calculated', 'Calculado'),
        ('approved', 'Aprobado'),
        ('cancelled', 'Cancelado'),
    ], default='draft', required=True, index=True)
    calculated_at = fields.Datetime(readonly=True)
    approved_at = fields.Datetime(readonly=True)

    line_ids = fields.One2many(
        'mrp.planning.plan.line', 'plan_id', string='Productos a fabricar'
    )
    # Legacy technical relations kept so upgrades from previous versions do not break.
    demand_ids = fields.One2many('mrp.planning.demand', 'plan_id')
    requirement_ids = fields.One2many('mrp.planning.requirement', 'plan_id')
    supply_ids = fields.One2many('mrp.planning.supply', 'plan_id')
    production_proposal_ids = fields.One2many('mrp.planning.production.proposal', 'plan_id')
    purchase_proposal_ids = fields.One2many('mrp.planning.purchase.proposal', 'plan_id')
    conflict_ids = fields.One2many('mrp.planning.conflict', 'plan_id')
    operation_ids = fields.One2many('mrp.planning.operation', 'plan_id')
    load_ids = fields.One2many('mrp.planning.workcenter.load', 'plan_id')
    run_ids = fields.One2many('mrp.planning.run', 'plan_id')
    snapshot_ids = fields.One2many('mrp.planning.snapshot', 'plan_id')

    finite_capacity = fields.Boolean(default=False)
    include_purchase = fields.Boolean(default=False)
    include_manufacturing = fields.Boolean(default=True)
    max_requirements = fields.Integer(default=10000)
    max_operations = fields.Integer(default=10000)

    line_count = fields.Integer(compute='_compute_counts')
    created_mo_count = fields.Integer(compute='_compute_counts')
    total_sales_qty = fields.Float(compute='_compute_totals', string='Pedidos pendientes')
    total_stock_qty = fields.Float(compute='_compute_totals', string='Inventario disponible')
    total_open_mo_qty = fields.Float(compute='_compute_totals', string='En fabricación')
    total_suggested_qty = fields.Float(compute='_compute_totals', string='Sugerido')
    total_to_manufacture_qty = fields.Float(compute='_compute_totals', string='A fabricar')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('mrp.planning.plan') or 'New'
        return super().create(vals_list)

    @api.depends('line_ids', 'line_ids.created_production_id')
    def _compute_counts(self):
        for record in self:
            record.line_count = len(record.line_ids)
            record.created_mo_count = len(record.line_ids.mapped('created_production_id'))

    @api.depends(
        'line_ids.sales_qty',
        'line_ids.stock_qty',
        'line_ids.production_qty',
        'line_ids.net_requirement_qty',
        'line_ids.planned_production_qty',
    )
    def _compute_totals(self):
        for record in self:
            record.total_sales_qty = sum(record.line_ids.mapped('sales_qty'))
            record.total_stock_qty = sum(record.line_ids.mapped('stock_qty'))
            record.total_open_mo_qty = sum(record.line_ids.mapped('production_qty'))
            record.total_suggested_qty = sum(record.line_ids.mapped('net_requirement_qty'))
            record.total_to_manufacture_qty = sum(record.line_ids.mapped('planned_production_qty'))

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for record in self:
            if record.date_end <= record.date_start:
                raise ValidationError(_('La fecha límite debe ser posterior a la fecha de creación del plan.'))

    def action_calculate(self):
        self.ensure_one()
        if self.state not in ('draft', 'calculated'):
            raise UserError(_('Solo puede calcular o recalcular un plan en borrador o calculado.'))
        from ..services.simple_planning_engine import SimplePlanningEngine
        SimplePlanningEngine(self).run()
        self.write({'state': 'calculated', 'calculated_at': fields.Datetime.now()})
        return True

    def action_reset(self):
        for plan in self:
            if plan.state == 'approved':
                raise UserError(_('Un plan aprobado ya generó órdenes de fabricación.'))
            plan.write({'state': 'draft', 'calculated_at': False})
        return True

    def _validate_sale_lines_still_pending(self):
        """Ensure the calculated plan still matches the current sale-line demand.

        Delivery can happen after the plan was calculated. Creating manufacturing orders
        from that stale snapshot would overproduce, so approval is blocked until the user
        recalculates whenever the source sale line changed materially.
        """
        self.ensure_one()
        issues = []
        precision = 1e-6

        for line in self.line_ids.filtered(lambda row: row.sale_line_id):
            sale_line = line.sale_line_id
            order = sale_line.order_id

            if order.state != 'sale':
                issues.append(_('%s: el pedido ya no está confirmado.') % order.name)
                continue

            if order.warehouse_id and order.warehouse_id != self.warehouse_id:
                issues.append(_('%s / %s: cambió el almacén del pedido.') % (
                    order.name, sale_line.product_id.display_name
                ))
                continue

            if not sale_line.planning_delivery_date:
                issues.append(_('%s / %s: no tiene fecha de entrega de planificación.') % (
                    order.name, sale_line.product_id.display_name
                ))
                continue

            if sale_line.planning_delivery_date > self.date_end:
                issues.append(_('%s / %s: la fecha de entrega quedó fuera del horizonte del plan.') % (
                    order.name, sale_line.product_id.display_name
                ))
                continue

            pending_sale_uom = max(sale_line.product_uom_qty - sale_line.qty_delivered, 0.0)
            pending_product_uom = sale_line.product_uom_id._compute_quantity(
                pending_sale_uom, sale_line.product_id.uom_id
            )

            if pending_product_uom <= precision:
                issues.append(_('%s / %s: la línea ya fue entregada completamente.') % (
                    order.name, sale_line.product_id.display_name
                ))
                continue

            if abs(pending_product_uom - line.sales_qty) > precision:
                issues.append(_(
                    '%s / %s: el pendiente cambió de %.2f a %.2f.'
                ) % (
                    order.name,
                    sale_line.product_id.display_name,
                    line.sales_qty,
                    pending_product_uom,
                ))

            if line.date_required and sale_line.planning_delivery_date != line.date_required:
                issues.append(_('%s / %s: cambió la fecha de entrega.') % (
                    order.name, sale_line.product_id.display_name
                ))

        if issues:
            shown = issues[:15]
            extra = len(issues) - len(shown)
            message = _(
                'La demanda de ventas cambió después de calcular la planificación.\n\n'
                'Debe pulsar Recalcular antes de aprobar para evitar fabricar cantidades que '
                'ya fueron entregadas o cuya fecha cambió.\n\n- %s'
            ) % '\n- '.join(shown)
            if extra > 0:
                message += _('\n- ... y %s cambios adicionales.') % extra
            raise UserError(message)

        return True

    def action_open_approval(self):
        self.ensure_one()
        if self.state != 'calculated':
            raise UserError(_('Solo puede aprobar un plan calculado.'))
        self._validate_sale_lines_still_pending()
        positive_lines = self.line_ids.filtered(lambda line: line.planned_production_qty > 0)
        if not positive_lines:
            raise UserError(_('No existen productos con cantidad a fabricar mayor que cero.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Aprobar planificación'),
            'res_model': 'mrp.planning.approval.wizard',
            'view_mode': 'form',
            'views': [(self.env.ref('mrp_advanced_planner.view_mrp_planning_approval_wizard_form').id, 'form')],
            'target': 'new',
            'context': {'default_plan_id': self.id},
        }

    def _approve_and_create_productions(self):
        for plan in self:
            if plan.state != 'calculated':
                raise UserError(_('Solo puede aprobar un plan calculado.'))

            # Validate again at the exact moment of creation. This protects against a
            # delivery occurring after the confirmation wizard was opened.
            plan._validate_sale_lines_still_pending()

            positive_lines = plan.line_ids.filtered(lambda line: line.planned_production_qty > 0)
            without_bom = positive_lines.filtered(lambda line: not line.bom_id)
            if without_bom:
                names = '\n- '.join(without_bom.mapped('product_id.display_name'))
                raise UserError(_(
                    'No se puede aprobar. Estos productos tienen cantidad a fabricar '
                    'pero no tienen Lista de Materiales:\n- %s'
                ) % names)

            productions = self.env['mrp.production']
            for line in positive_lines:
                if line.created_production_id:
                    productions |= line.created_production_id
                    continue
                vals = {
                    'origin': '%s / %s' % (plan.name, line.sale_order_id.name) if line.sale_order_id else plan.name,
                    'product_id': line.product_id.id,
                    'product_qty': line.planned_production_qty,
                    'product_uom_id': line.product_uom_id.id,
                    'bom_id': line.bom_id.id,
                    'company_id': plan.company_id.id,
                    'advanced_plan_id': plan.id,
                    'planning_plan_line_id': line.id,
                    'planning_sale_line_id': line.sale_line_id.id if line.sale_line_id else False,
                }
                if 'date_deadline' in self.env['mrp.production']._fields:
                    vals['date_deadline'] = line.date_required or plan.date_end
                production = self.env['mrp.production'].create(vals)
                production.action_confirm()
                line.write({'created_production_id': production.id, 'state': 'applied'})
                productions |= production

            plan.write({'state': 'approved', 'approved_at': fields.Datetime.now()})
        return productions

    def action_open_created_productions(self):
        self.ensure_one()
        ids = self.line_ids.mapped('created_production_id').ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Órdenes de fabricación del plan'),
            'res_model': 'mrp.production',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', ids)],
        }
