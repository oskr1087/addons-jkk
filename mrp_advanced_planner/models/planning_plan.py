from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PlanningPlan(models.Model):
    _name = 'mrp.planning.plan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Planificador de abastecimiento y fabricación'
    _order = 'date_end desc, id desc'

    name = fields.Char(required=True, copy=False, default='New', tracking=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)

    # warehouse_id is retained only to keep upgrades from older versions safe.
    warehouse_id = fields.Many2one('stock.warehouse', string='Almacén principal (legacy)', index=True)
    warehouse_ids = fields.Many2many(
        'stock.warehouse', 'mrp_planning_plan_warehouse_rel', 'plan_id', 'warehouse_id',
        string='Almacenes', required=True, check_company=True, tracking=True,
        default=lambda self: self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1),
        domain="[('company_id', '=', company_id)]",
    )

    user_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, tracking=True)
    date_start = fields.Datetime(required=True, default=fields.Datetime.now)
    date_end = fields.Datetime(string='Planificar hasta', required=True, tracking=True)
    priority = fields.Selection([('0', 'Normal'), ('1', 'Alta'), ('2', 'Urgente')], default='0', required=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Borrador'), ('calculated', 'Calculado'), ('approved', 'Finalizado'), ('cancelled', 'Cancelado')
    ], default='draft', required=True, index=True, tracking=True)
    calculated_at = fields.Datetime(readonly=True)
    approved_at = fields.Datetime(readonly=True)

    line_ids = fields.One2many('mrp.planning.plan.line', 'plan_id', string='Productos planificados')

    # Legacy technical relations kept so database upgrades from previous versions do not break.
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
    include_purchase = fields.Boolean(default=True)
    include_manufacturing = fields.Boolean(default=True)
    max_requirements = fields.Integer(default=10000)
    max_operations = fields.Integer(default=10000)

    line_count = fields.Integer(compute='_compute_counts')
    created_mo_count = fields.Integer(compute='_compute_counts')
    created_po_count = fields.Integer(compute='_compute_counts')
    created_transfer_count = fields.Integer(compute='_compute_counts')

    pending_manufacture_count = fields.Integer(compute='_compute_execution_status')
    pending_purchase_count = fields.Integer(compute='_compute_execution_status')
    pending_move_count = fields.Integer(compute='_compute_execution_status')
    pending_decision_count = fields.Integer(compute='_compute_execution_status')
    can_finalize_plan = fields.Boolean(compute='_compute_execution_status')

    total_sales_qty = fields.Float(compute='_compute_totals', string='Pedidos pendientes')
    total_stock_qty = fields.Float(compute='_compute_totals', string='Pronóstico disponible')
    total_open_mo_qty = fields.Float(compute='_compute_totals', string='OF abiertas')
    total_suggested_qty = fields.Float(compute='_compute_totals', string='Necesidad neta')
    total_to_manufacture_qty = fields.Float(compute='_compute_totals', string='A fabricar')
    total_to_purchase_qty = fields.Float(compute='_compute_totals', string='A comprar')
    total_to_move_qty = fields.Float(compute='_compute_totals', string='A mover')

    def init(self):
        # Upgrade-safe migration: preserve the warehouse selected in older versions
        # when the new multi-warehouse relation is introduced.
        self.env.cr.execute(
            """
            INSERT INTO mrp_planning_plan_warehouse_rel (plan_id, warehouse_id)
            SELECT p.id, p.warehouse_id
              FROM mrp_planning_plan p
             WHERE p.warehouse_id IS NOT NULL
               AND NOT EXISTS (
                    SELECT 1 FROM mrp_planning_plan_warehouse_rel r
                     WHERE r.plan_id = p.id AND r.warehouse_id = p.warehouse_id
               )
            """
        )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('mrp.planning.plan') or 'New'
            wh_commands = vals.get('warehouse_ids')
            if not vals.get('warehouse_id') and wh_commands:
                # Common create command [(6, 0, ids)] or [(4, id)].
                ids = []
                for command in wh_commands:
                    if command[0] == 6:
                        ids.extend(command[2])
                    elif command[0] == 4:
                        ids.append(command[1])
                if ids:
                    vals['warehouse_id'] = ids[0]
        records = super().create(vals_list)
        records._sync_legacy_warehouse()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'warehouse_ids' in vals:
            self._sync_legacy_warehouse()
        return res

    def _sync_legacy_warehouse(self):
        for plan in self:
            first = plan.warehouse_ids[:1]
            if first and plan.warehouse_id != first:
                super(PlanningPlan, plan).write({'warehouse_id': first.id})
        return True

    def _ensure_warehouse_ids(self):
        for plan in self:
            if not plan.warehouse_ids and plan.warehouse_id:
                plan.warehouse_ids = [(6, 0, plan.warehouse_id.ids)]
            if not plan.warehouse_ids:
                raise UserError(_('Debe seleccionar al menos un almacén para calcular la planificación.'))
        return True

    @api.depends('line_ids')
    def _compute_counts(self):
        Production = self.env['mrp.production']
        Purchase = self.env['purchase.order']
        Picking = self.env['stock.picking']
        for plan in self:
            plan.line_count = len(plan.line_ids)
            plan.created_mo_count = Production.search_count([('advanced_plan_id', '=', plan.id)])
            plan.created_po_count = Purchase.search_count([('advanced_plan_id', '=', plan.id)]) if 'advanced_plan_id' in Purchase._fields else 0
            plan.created_transfer_count = Picking.search_count([('advanced_plan_id', '=', plan.id)]) if 'advanced_plan_id' in Picking._fields else 0

    @api.depends(
        'state',
        'line_ids.planner_production_qty',
        'line_ids.action_manufacture',
        'line_ids.action_purchase',
        'line_ids.action_move',
        'line_ids.created_production_id',
        'line_ids.created_purchase_line_id',
        'line_ids.created_picking_ids',
    )
    def _compute_execution_status(self):
        for plan in self:
            relevant = plan.line_ids.filtered(lambda line: line.planner_production_qty > 0)
            plan.pending_manufacture_count = len(relevant.filtered(
                lambda line: line.action_manufacture and not line.created_production_id
            ))
            plan.pending_purchase_count = len(relevant.filtered(
                lambda line: line.action_purchase and not line.created_purchase_line_id
            ))
            plan.pending_move_count = len(relevant.filtered(
                lambda line: line.action_move and not line.created_picking_ids
            ))
            plan.pending_decision_count = len(relevant.filtered(
                lambda line: not line.action_manufacture and not line.action_purchase and not line.action_move
            ))

            pending_total = (
                plan.pending_manufacture_count
                + plan.pending_purchase_count
                + plan.pending_move_count
                + plan.pending_decision_count
            )
            plan.can_finalize_plan = plan.state == 'calculated' and pending_total == 0

    @api.depends(
        'line_ids.sales_qty', 'line_ids.stock_qty', 'line_ids.production_qty',
        'line_ids.net_requirement_qty', 'line_ids.planner_production_qty',
        'line_ids.action_manufacture', 'line_ids.action_purchase', 'line_ids.action_move',
    )
    def _compute_totals(self):
        for plan in self:
            plan.total_sales_qty = sum(plan.line_ids.mapped('sales_qty'))
            plan.total_stock_qty = sum(plan.line_ids.mapped('stock_qty'))
            plan.total_open_mo_qty = sum(plan.line_ids.mapped('production_qty'))
            plan.total_suggested_qty = sum(plan.line_ids.mapped('net_requirement_qty'))
            plan.total_to_manufacture_qty = sum(plan.line_ids.filtered('action_manufacture').mapped('planner_production_qty'))
            plan.total_to_purchase_qty = sum(plan.line_ids.filtered('action_purchase').mapped('planner_production_qty'))
            plan.total_to_move_qty = sum(plan.line_ids.filtered('action_move').mapped('planner_production_qty'))

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for plan in self:
            if plan.date_end <= plan.date_start:
                raise ValidationError(_('La fecha límite debe ser posterior a la fecha de creación del plan.'))

    @api.constrains('warehouse_ids', 'company_id')
    def _check_warehouse_company(self):
        for plan in self:
            if plan.warehouse_ids.filtered(lambda wh: wh.company_id != plan.company_id):
                raise ValidationError(_('Todos los almacenes seleccionados deben pertenecer a la compañía del plan.'))

    def action_calculate(self):
        self.ensure_one()
        if self.state not in ('draft', 'calculated'):
            raise UserError(_('Solo puede calcular o recalcular un plan en borrador o calculado.'))
        self._ensure_warehouse_ids()
        from ..services.simple_planning_engine import SimplePlanningEngine
        SimplePlanningEngine(self).run()
        self.write({'state': 'calculated', 'calculated_at': fields.Datetime.now()})
        return True

    def action_reset(self):
        for plan in self:
            if plan.created_mo_count or plan.created_po_count or plan.created_transfer_count:
                raise UserError(_('No puede regresar a borrador un plan que ya generó documentos.'))
            plan.write({'state': 'draft', 'calculated_at': False})
        return True

    def _current_source_sale_lines(self):
        self.ensure_one()
        self._ensure_warehouse_ids()
        return self.env['sale.order.line'].search([
            ('order_id.state', '=', 'sale'),
            ('order_id.company_id', '=', self.company_id.id),
            ('order_id.warehouse_id', 'in', self.warehouse_ids.ids),
            ('product_id', '!=', False),
            ('display_type', '=', False),
            ('planning_delivery_date', '!=', False),
            ('planning_delivery_date', '<=', self.date_end),
        ]).filtered(lambda sl: sl.product_uom_qty - sl.qty_delivered > 0)

    def _validate_sale_lines_still_pending(self):
        """Block execution when demand changed after calculation."""
        self.ensure_one()
        current = self._current_source_sale_lines()
        current_ids = set(current.ids)
        for line in self.line_ids:
            source_lines = line.sale_line_ids or line.sale_line_id
            if any(sl.id not in current_ids for sl in source_lines):
                raise UserError(_(
                    'Una o más ventas origen del producto %s ya no están pendientes o cambiaron de fecha/almacén. '
                    'Debe recalcular la planificación.'
                ) % line.product_id.display_name)
            current_qty = 0.0
            for sl in source_lines:
                pending = max(sl.product_uom_qty - sl.qty_delivered, 0.0)
                current_qty += sl.product_uom_id._compute_quantity(pending, sl.product_id.uom_id)
            if abs(current_qty - line.sales_qty) > 1e-6:
                raise UserError(_(
                    'La cantidad pendiente del producto %s cambió. Debe recalcular la planificación.'
                ) % line.product_id.display_name)
        return True

    def _validate_selected_lines(self, action_field):
        self.ensure_one()
        if self.state != 'calculated':
            raise UserError(_('Solo puede generar documentos mientras la planificación está en estado Calculado.'))
        self._validate_sale_lines_still_pending()
        lines = self.line_ids.filtered(lambda l: l[action_field] and l.planner_production_qty > 0)
        if not lines:
            labels = {'action_manufacture': _('fabricar'), 'action_purchase': _('comprar'), 'action_move': _('mover')}
            raise UserError(_('No existen productos seleccionados para %s.') % labels[action_field])
        return lines

    def action_finalize_plan(self):
        for plan in self:
            if plan.state != 'calculated':
                raise UserError(_('Solo puede finalizar una planificación calculada.'))

            relevant = plan.line_ids.filtered(lambda line: line.planner_production_qty > 0)
            undecided = relevant.filtered(
                lambda line: not line.action_manufacture and not line.action_purchase and not line.action_move
            )
            if undecided:
                raise UserError(_(
                    'Existen %s producto(s) con cantidad planificada pero sin una decisión '
                    '(Fabricar, Comprar o Mover).'
                ) % len(undecided))

            pending_manufacture = relevant.filtered(
                lambda line: line.action_manufacture and not line.created_production_id
            )
            pending_purchase = relevant.filtered(
                lambda line: line.action_purchase and not line.created_purchase_line_id
            )
            pending_move = relevant.filtered(
                lambda line: line.action_move and not line.created_picking_ids
            )

            messages = []
            if pending_manufacture:
                messages.append(_('Fabricar: %s') % len(pending_manufacture))
            if pending_purchase:
                messages.append(_('Comprar: %s') % len(pending_purchase))
            if pending_move:
                messages.append(_('Mover: %s') % len(pending_move))
            if messages:
                raise UserError(_(
                    'Todavía existen líneas pendientes de generar:\n%s'
                ) % '\n'.join(messages))

            plan.write({
                'state': 'approved',
                'approved_at': fields.Datetime.now(),
            })
            plan.message_post(body=_(
                'Planificación finalizada. Documentos generados: %s OF, %s compra(s), %s traslado(s).'
            ) % (
                plan.created_mo_count,
                plan.created_po_count,
                plan.created_transfer_count,
            ))
        return True

    def action_create_manufacturing(self):
        self.ensure_one()
        lines = self._validate_selected_lines('action_manufacture')
        missing_bom = lines.filtered(lambda l: not l.bom_id)
        if missing_bom:
            raise UserError(_('No se puede fabricar sin LdM:\n- %s') % '\n- '.join(missing_bom.mapped('product_id.display_name')))

        productions = self.env['mrp.production']
        for line in lines:
            if line.created_production_id:
                productions |= line.created_production_id
                continue
            warehouse = line.target_warehouse_id or self.warehouse_ids[:1]
            vals = {
                'origin': self.name,
                'product_id': line.product_id.id,
                'product_qty': line.planner_production_qty,
                'product_uom_id': line.product_uom_id.id,
                'bom_id': line.bom_id.id,
                'company_id': self.company_id.id,
                'advanced_plan_id': self.id,
                'planning_plan_line_id': line.id,
            }
            if warehouse and warehouse.manu_type_id:
                vals['picking_type_id'] = warehouse.manu_type_id.id
            if 'date_deadline' in self.env['mrp.production']._fields:
                vals['date_deadline'] = line.date_required or self.date_end
            mo = self.env['mrp.production'].create(vals)
            mo.action_confirm()
            line.write({'created_production_id': mo.id, 'state': 'applied', 'planned_production_qty': line.planner_production_qty})
            productions |= mo
        return self.action_open_created_productions()

    def action_create_purchases(self):
        self.ensure_one()
        lines = self._validate_selected_lines('action_purchase')
        Purchase = self.env['purchase.order']
        PurchaseLine = self.env['purchase.order.line']
        grouped_pos = {}

        missing_vendor = lines.filtered(lambda line: not line.purchase_vendor_id)
        if missing_vendor:
            raise UserError(_(
                'Debe seleccionar un proveedor para cada producto a comprar:\n- %s'
            ) % '\n- '.join(missing_vendor.mapped('product_id.display_name')))

        for line in lines:
            if line.created_purchase_line_id:
                continue

            warehouse = line.target_warehouse_id or self.warehouse_ids[:1]
            vendor = line.purchase_vendor_id
            key = (vendor.commercial_partner_id.id, warehouse.id if warehouse else False)
            po = grouped_pos.get(key)
            if not po:
                po = Purchase.search([
                    ('state', '=', 'draft'),
                    ('advanced_plan_id', '=', self.id),
                    ('partner_id', '=', vendor.commercial_partner_id.id),
                    ('picking_type_id', '=', warehouse.in_type_id.id if warehouse and warehouse.in_type_id else False),
                ], limit=1)
                if not po:
                    po_vals = {
                        'partner_id': vendor.commercial_partner_id.id,
                        'company_id': self.company_id.id,
                        'origin': self.name,
                        'advanced_plan_id': self.id,
                    }
                    if warehouse and warehouse.in_type_id:
                        po_vals['picking_type_id'] = warehouse.in_type_id.id
                    po = Purchase.create(po_vals)
                grouped_pos[key] = po

            vals = PurchaseLine._prepare_purchase_order_line(
                line.product_id,
                line.planner_production_qty,
                line.product_uom_id,
                self.company_id,
                po.partner_id,
                po,
            )
            vals['planning_plan_line_id'] = line.id
            pol = PurchaseLine.create(vals)
            line.write({
                'created_purchase_line_id': pol.id,
                'state': 'applied',
                'planned_purchase_qty': line.planner_production_qty,
            })

        return self.action_open_created_purchases()

    def _move_allocations_for_line(self, line):
        """Allocate free excess stock from one selected warehouse to local shortages in others."""
        sources = []
        targets = []
        for detail in line.warehouse_detail_ids:
            if detail.transferable_excess_qty > 0:
                sources.append([detail.warehouse_id, detail.transferable_excess_qty])
            if detail.local_shortage_qty > 0:
                targets.append([detail.warehouse_id, detail.local_shortage_qty])
        sources.sort(key=lambda row: row[1], reverse=True)
        targets.sort(key=lambda row: row[1], reverse=True)
        remaining = line.planner_production_qty
        allocations = []
        for target in targets:
            need = min(target[1], remaining)
            if need <= 0:
                break
            for source in sources:
                if source[0] == target[0] or source[1] <= 0 or need <= 0:
                    continue
                qty = min(source[1], need, remaining)
                if qty > 0:
                    allocations.append((source[0], target[0], qty))
                    source[1] -= qty
                    need -= qty
                    remaining -= qty
            if remaining <= 0:
                break
        return allocations, remaining

    def _create_replenishments_for_lines(self, lines):
        """Create internal transfers only for the supplied planner lines."""
        self.ensure_one()

        Picking = self.env['stock.picking']
        Move = self.env['stock.move']
        pickings_by_route = {}
        created = Picking

        for line in lines:
            if line.plan_id != self:
                raise UserError(_('La línea seleccionada no pertenece a esta planificación.'))
            if not line.action_move:
                raise UserError(_(
                    'El producto %s no está seleccionado para mover.'
                ) % line.product_id.display_name)
            if line.planner_production_qty <= 0:
                raise UserError(_(
                    'La cantidad a mover del producto %s debe ser mayor que cero.'
                ) % line.product_id.display_name)
            if line.created_picking_ids:
                created |= line.created_picking_ids
                continue

            allocations, unallocated = self._move_allocations_for_line(line)
            if not allocations or unallocated > 1e-6:
                raise UserError(_(
                    'No existe stock pronosticado suficiente entre los almacenes seleccionados '
                    'para mover %.2f de %s. Sugerido movible: %.2f.'
                ) % (
                    line.planner_production_qty,
                    line.product_id.display_name,
                    line.move_suggested_qty,
                ))

            line_pickings = Picking
            for source_wh, target_wh, qty in allocations:
                key = (source_wh.id, target_wh.id)
                picking = pickings_by_route.get(key)
                if not picking:
                    if not source_wh.int_type_id:
                        raise UserError(_(
                            'El almacén %s no tiene tipo de operación interna configurado.'
                        ) % source_wh.display_name)

                    picking = Picking.create({
                        'picking_type_id': source_wh.int_type_id.id,
                        'location_id': source_wh.lot_stock_id.id,
                        'location_dest_id': target_wh.lot_stock_id.id,
                        'origin': self.name,
                        'company_id': self.company_id.id,
                        'advanced_plan_id': self.id,
                    })
                    pickings_by_route[key] = picking

                Move.create({
                    'name': '%s - %s' % (self.name, line.product_id.display_name),
                    'product_id': line.product_id.id,
                    'product_uom_qty': qty,
                    'product_uom': line.product_uom_id.id,
                    'location_id': source_wh.lot_stock_id.id,
                    'location_dest_id': target_wh.lot_stock_id.id,
                    'picking_id': picking.id,
                    'company_id': self.company_id.id,
                    'planning_plan_line_id': line.id,
                })
                line_pickings |= picking

            line_pickings.action_confirm()
            line_pickings.action_assign()
            line.write({
                'created_picking_ids': [(6, 0, line_pickings.ids)],
                'state': 'applied',
            })
            created |= line_pickings

        return created

    def action_create_replenishments(self):
        self.ensure_one()
        lines = self._validate_selected_lines('action_move')
        self._create_replenishments_for_lines(lines)
        return self.action_open_created_transfers()

    # Compatibility with the old approval wizard: approval now means generate manufacturing selections.
    def action_open_approval(self):
        return self.action_create_manufacturing()

    def _approve_and_create_productions(self):
        self.action_create_manufacturing()
        return self.env['mrp.production'].search([('advanced_plan_id', 'in', self.ids)])

    def action_open_created_productions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Órdenes de fabricación del plan'),
            'res_model': 'mrp.production', 'view_mode': 'list,form', 'views': [(False, 'list'), (False, 'form')],
            'domain': [('advanced_plan_id', '=', self.id)],
        }

    def action_open_created_purchases(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Compras del plan'),
            'res_model': 'purchase.order', 'view_mode': 'list,form', 'views': [(False, 'list'), (False, 'form')],
            'domain': [('advanced_plan_id', '=', self.id)],
        }

    def action_open_created_transfers(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Reabastecimientos del plan'),
            'res_model': 'stock.picking', 'view_mode': 'list,form', 'views': [(False, 'list'), (False, 'form')],
            'domain': [('advanced_plan_id', '=', self.id)],
        }
