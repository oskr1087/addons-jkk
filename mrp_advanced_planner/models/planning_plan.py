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

    plan_type = fields.Selection(
        [('manufacturing', 'Planificación de fabricación'), ('purchase', 'Planificación de compras')],
        string='Tipo de planificación',
        required=True,
        default=lambda self: self.env.context.get('default_plan_type', 'manufacturing'),
        tracking=True,
        index=True,
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
    production_component_ids = fields.One2many(
        'mrp.planning.production.component', 'plan_id',
        string='Componentes congelados de fabricación', copy=True,
    )
    external_move_ids = fields.One2many('mrp.planning.external.warehouse.move', 'plan_id', string='Disponibilidad en otros almacenes', copy=False)
    needs_recalculation = fields.Boolean(string='Requiere recalcular', readonly=True, tracking=True, help='Se activa después de crear una transferencia desde otro almacén. Recalcule antes de fabricar o comprar.')

    generated_purchase_plan_id = fields.Many2one(
        'mrp.planning.plan', string='Plan de compras de componentes',
        readonly=True, copy=False, ondelete='set null', tracking=True,
    )
    source_manufacturing_plan_id = fields.Many2one(
        'mrp.planning.plan', string='Plan de fabricación origen',
        readonly=True, copy=False, ondelete='set null', index=True,
    )
    generated_component_mo_count = fields.Integer(
        string='OF de subcomponentes', compute='_compute_component_document_counts'
    )

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

    def _allowed_plan_types_for_user(self):
        user = self.env.user
        if user.has_group('mrp_advanced_planner.group_planner_manager'):
            return {'manufacturing', 'purchase'}
        allowed = set()
        if user.has_group('mrp_advanced_planner.group_planner_manufacturing_user'):
            allowed.add('manufacturing')
        if user.has_group('mrp_advanced_planner.group_planner_purchase_user'):
            allowed.add('purchase')
        return allowed

    def _check_plan_type_permission(self, plan_type=None):
        allowed = self._allowed_plan_types_for_user()
        types = {plan_type} if plan_type else set(self.mapped('plan_type'))
        forbidden = types - allowed
        if forbidden:
            labels = {
                'manufacturing': _('fabricación'),
                'purchase': _('compras'),
            }
            raise UserError(_(
                'No tiene permisos para trabajar con planificación de %s.'
            ) % ', '.join(labels.get(value, value) for value in sorted(forbidden)))
        return True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            plan_type = vals.get('plan_type') or self.env.context.get('default_plan_type', 'manufacturing')
            if not self.env.context.get('aps_internal_create'):
                self._check_plan_type_permission(plan_type)
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

    @api.depends('production_component_ids.generated_production_id')
    def _compute_component_document_counts(self):
        for plan in self:
            plan.generated_component_mo_count = len(
                plan.production_component_ids.mapped('generated_production_id')
            )

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
        self._check_plan_type_permission()
        if self.source_manufacturing_plan_id and self.plan_type == 'purchase':
            origin = self.source_manufacturing_plan_id
            origin._refresh_component_sourcing()
            origin._sync_component_purchase_plan()
            return True
        if self.state not in ('draft', 'calculated'):
            raise UserError(_('Solo puede calcular o recalcular un plan en borrador o calculado.'))
        self._ensure_warehouse_ids()
        from ..services.simple_planning_engine import SimplePlanningEngine
        result_count = SimplePlanningEngine(self).run()

        # A search with no demand/results must remain reusable.  Moving the
        # plan to Calculated here used to lock date_end/warehouses in the form,
        # forcing the user to create a new plan just to try another horizon.
        if not result_count or not self.line_ids:
            self.write({
                'state': 'draft',
                'calculated_at': False,
                'needs_recalculation': False,
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin resultados'),
                    'message': _(
                        'No se encontraron necesidades para los almacenes y '
                        'la fecha seleccionados. El plan permanece en Borrador; '
                        'puede cambiar "Planificar hasta" y calcular nuevamente.'
                    ),
                    'type': 'warning',
                    'sticky': False,
                },
            }

        self.write({
            'state': 'calculated',
            'calculated_at': fields.Datetime.now(),
            'needs_recalculation': False,
        })
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
        """Validate demand freshness without confusing traceability with demand.

        ``sale_line_ids`` has two meanings in APS:
        - for direct Sale demand it is the quantity source;
        - for recursive MRP/component purchase lines it is traceability back to
          the finished-product SO only.

        Component purchase lines therefore must NOT compare the pending qty of
        the finished product against the component's ``direct_sale_demand_qty``.
        """
        self.ensure_one()

        # A purchase planner generated from manufacturing inherits SO lines only
        # for traceability. The manufacturing origin is the authoritative demand
        # snapshot, so validate that plan once and do not reinterpret its SO
        # quantities as component demand.
        if (
            self.plan_type == 'purchase'
            and self.source_manufacturing_plan_id
        ):
            self.source_manufacturing_plan_id._validate_sale_lines_still_pending()

        current = self._current_source_sale_lines()
        current_ids = set(current.ids)

        for line in self.line_ids:
            source_lines = line.sale_line_ids or line.sale_line_id
            if not source_lines:
                continue

            # MRP/component lines carry SOs for traceability only. Their
            # quantities come from the exploded engineering requirement.
            if line.source_type == 'mrp':
                continue

            # Mixed lines may contain both direct sales demand and component
            # demand. Validate only the direct sales portion.
            direct_qty = (
                line.direct_sale_demand_qty
                if 'direct_sale_demand_qty' in line._fields
                else line.sales_qty
            )
            if direct_qty <= 1e-6:
                continue

            if any(sl.id not in current_ids for sl in source_lines):
                raise UserError(_(
                    'Una o más ventas origen del producto %s ya no están '
                    'pendientes o cambiaron de fecha/almacén. Recalcule la '
                    'planificación antes de ejecutar documentos.'
                ) % line.product_id.display_name)

            # Only direct SO lines for this same product are a quantity source.
            product_sale_lines = source_lines.filtered(
                lambda sl: sl.product_id == line.product_id
            )
            current_qty = 0.0
            for sl in product_sale_lines:
                pending = max(sl.product_uom_qty - sl.qty_delivered, 0.0)
                current_qty += sl.product_uom_id._compute_quantity(
                    pending, sl.product_id.uom_id
                )

            if abs(current_qty - direct_qty) > 1e-6:
                raise UserError(_(
                    'La demanda pendiente de %s cambió desde el último cálculo '
                    '(planificado: %.2f, actual: %.2f). Recalcule la '
                    'planificación antes de continuar.'
                ) % (
                    line.product_id.display_name,
                    direct_qty,
                    current_qty,
                ))
        return True

    def _validate_selected_lines(self, action_field):
        self.ensure_one()
        allowed = {
            'manufacturing': {'action_manufacture'},
            'purchase': {'action_purchase', 'action_move'},
        }
        if action_field not in allowed.get(self.plan_type, set()):
            raise UserError(_('La acción seleccionada no corresponde al tipo de esta planificación.'))
        if self.state != 'calculated':
            raise UserError(_('Solo puede generar documentos mientras la planificación está en estado Calculado.'))
        if self.needs_recalculation:
            raise UserError(_('Se generó una transferencia desde otro almacén después del último cálculo. Recalcule la planificación antes de fabricar o comprar para evitar sobreplanificación.'))
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
            if plan.needs_recalculation:
                raise UserError(_('Debe recalcular la planificación después de las transferencias internas generadas.'))

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

    def _refresh_component_sourcing(self):
        self.ensure_one()
        if self.plan_type != 'manufacturing':
            return self.env['mrp.planning.production.component']
        from ..services.component_sourcing import ComponentSourcingEngine
        return ComponentSourcingEngine(self).run()

    def _sync_component_purchase_plan(self):
        """Create/update the purchase planner generated by this MFG plan."""
        self.ensure_one()
        if self.plan_type != 'manufacturing':
            return False

        components = self.production_component_ids.filtered(
            lambda c: c.include_in_mo and c.to_purchase_qty > 1e-6
        )
        purchase_plan = self.generated_purchase_plan_id.sudo()

        if not components and not purchase_plan:
            self.message_post(body=_(
                'APS: todos los componentes están cubiertos; no fue necesario '
                'generar un plan de compras.'
            ))
            return False

        # Do not rewrite an already executed linked purchase plan.
        if purchase_plan and (
            purchase_plan.created_po_count
            or purchase_plan.state in ('approved', 'cancelled')
        ):
            return purchase_plan

        Plan = self.env['mrp.planning.plan'].sudo().with_context(
            aps_internal_create=True
        )
        if not purchase_plan:
            purchase_plan = Plan.create({
                'plan_type': 'purchase',
                'company_id': self.company_id.id,
                'user_id': self.user_id.id,
                'date_start': fields.Datetime.now(),
                'date_end': self.date_end,
                'priority': self.priority,
                'warehouse_ids': [(6, 0, self.warehouse_ids.ids)],
                'source_manufacturing_plan_id': self.id,
                'state': 'calculated',
                'calculated_at': fields.Datetime.now(),
            })
            self.sudo().write({'generated_purchase_plan_id': purchase_plan.id})
        else:
            purchase_plan.line_ids.unlink()
            purchase_plan.write({
                'date_end': self.date_end,
                'warehouse_ids': [(6, 0, self.warehouse_ids.ids)],
                'state': 'calculated',
                'calculated_at': fields.Datetime.now(),
            })

        # No components to buy: keep traceability plan but empty.
        if not components:
            self.message_post(body=_(
                'APS: no existen componentes pendientes de compra después '
                'del análisis de abastecimiento.'
            ))
            return purchase_plan

        grouped = {}
        for component in components:
            warehouse = (
                component.planning_line_id.target_warehouse_id
                or self.warehouse_ids[:1]
            )
            key = (component.product_id.id, warehouse.id)
            row = grouped.setdefault(key, {
                'product': component.product_id,
                'warehouse': warehouse,
                'qty': 0.0,
                'demand': 0.0,
                'local': 0.0,
                'components': self.env['mrp.planning.production.component'],
                'sale_lines': self.env['sale.order.line'],
                'date_required': component.planning_line_id.date_required or self.date_end,
            })
            row['qty'] += component.to_purchase_qty
            row['demand'] += component.effective_required_qty
            row['local'] += component.local_supply_qty
            row['components'] |= component
            row['sale_lines'] |= (
                component.planning_line_id.sale_line_ids
                or component.planning_line_id.sale_line_id
            )
            date = component.planning_line_id.date_required or self.date_end
            if date and date < row['date_required']:
                row['date_required'] = date

        Line = self.env['mrp.planning.plan.line'].sudo()
        for row in grouped.values():
            product = row['product']
            sellers = product.with_company(self.company_id).seller_ids.filtered(
                lambda seller: not seller.company_id
                or seller.company_id == self.company_id
            ).sorted(key=lambda seller: (seller.sequence, seller.id))
            vendor = sellers[:1].partner_id if sellers else False
            line = Line.create({
                'plan_id': purchase_plan.id,
                'sale_line_id': row['sale_lines'][:1].id,
                'sale_line_ids': [(6, 0, row['sale_lines'].ids)],
                'product_id': product.id,
                'target_warehouse_id': row['warehouse'].id,
                'demand_qty': row['demand'],
                'sales_qty': row['demand'],
                'direct_sale_demand_qty': 0.0,
                'mrp_component_demand_qty': row['demand'],
                'stock_qty': row['local'],
                'net_requirement_qty': row['qty'],
                'planner_production_qty': row['qty'],
                'planned_purchase_qty': row['qty'],
                'action_purchase': True,
                'purchase_vendor_id': vendor.id if vendor else False,
                'date_required': row['date_required'],
                'source_type': 'mrp',
                'source_reference': self.name,
                'bom_origin_detail': '\n'.join(
                    row['components'].mapped('path')
                ),
                'state': 'planned',
            })
            row['components'].sudo().write({
                'generated_purchase_plan_line_id': line.id
            })

        purchase_plan.message_post(body=_(
            'Plan de compras generado automáticamente desde %s con %s '
            'producto(s) de componentes.'
        ) % (self.name, len(purchase_plan.line_ids)))
        self.message_post(body=_(
            'Se generó/actualizó el plan de compras %s con los componentes '
            'pendientes de compra.'
        ) % purchase_plan.name)
        return purchase_plan

    def _create_component_manufacturing_orders(self):
        """Create sub-MOs for fabricable components not covered by supply."""
        self.ensure_one()
        components = self.production_component_ids.filtered(
            lambda c: c.include_in_mo
            and c.to_manufacture_qty > 1e-6
            and not c.generated_production_id
        )
        if not components:
            return self.env['mrp.production']

        from ..services.odoo19_compat import find_bom
        Production = self.env['mrp.production']
        created = Production

        # Deepest components first so dependencies are visible in a logical order.
        for component in components.sorted(
            key=lambda c: (-c.level, c.planning_line_id.id, c.sequence, c.id)
        ):
            bom = find_bom(
                self.env,
                component.product_id,
                company_id=self.company_id.id,
            )
            if not bom:
                raise UserError(_(
                    'El componente %s está clasificado para Fabricar pero no '
                    'se encontró una Lista de Materiales.'
                ) % component.product_id.display_name)

            warehouse = (
                component.planning_line_id.target_warehouse_id
                or self.warehouse_ids[:1]
            )
            vals = {
                'origin': '%s / %s' % (self.name, component.product_id.display_name),
                'product_id': component.product_id.id,
                'product_qty': component.to_manufacture_qty,
                'product_uom_id': component.product_uom_id.id,
                'bom_id': bom.id,
                'company_id': self.company_id.id,
                'advanced_plan_id': self.id,
                'planning_plan_line_id': component.planning_line_id.id,
                'aps_component_snapshot': True,
                'aps_planning_component_id': component.id,
            }
            if warehouse and warehouse.manu_type_id:
                vals['picking_type_id'] = warehouse.manu_type_id.id
            if 'date_deadline' in Production._fields:
                vals['date_deadline'] = (
                    component.planning_line_id.date_required or self.date_end
                )
            mo = Production.with_context(
                skip_compute_move_raw_ids=True
            ).create(vals)
            mo.action_confirm()
            component.sudo().write({'generated_production_id': mo.id})
            created |= mo
        return created

    def action_open_component_productions(self):
        self.ensure_one()
        ids = self.production_component_ids.mapped('generated_production_id').ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('OF de subcomponentes'),
            'res_model': 'mrp.production',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', ids)],
            'target': 'current',
        }

    def action_open_generated_purchase_plan(self):
        self.ensure_one()
        if not self.generated_purchase_plan_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Plan de compras de componentes'),
            'res_model': 'mrp.planning.plan',
            'res_id': self.generated_purchase_plan_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    def action_create_manufacturing(self):
        self.ensure_one()
        self._check_plan_type_permission('manufacturing')
        if self.plan_type != 'manufacturing':
            raise UserError(_(
                'Esta acción solo está disponible en una planificación de fabricación.'
            ))

        lines = self._validate_selected_lines('action_manufacture')
        missing_bom = lines.filtered(lambda l: not l.bom_id)
        if missing_bom:
            raise UserError(_('No se puede fabricar sin LdM:\n- %s') % '\n- '.join(
                missing_bom.mapped('product_id.display_name')
            ))

        # Re-evaluate the edited snapshot immediately before execution.
        self._refresh_component_sourcing()

        # Internal transfers are OPTIONAL recommendations.  They never block
        # manufacturing.  If the user executes one, action_create_transfer()
        # marks the plan as requiring recalculation so the new incoming stock
        # is considered before creating subsequent supply documents.
        # Create/update procurement plan first, then sub-MOs and finished MOs.
        self._sync_component_purchase_plan()

        # APS does NOT create manufacturing orders for fabricable components.
        # The finished-product MO keeps those components in its raw material
        # snapshot and Odoo's standard MRP/replenishment flow resolves their
        # manufacturing supply.
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
                'aps_component_snapshot': True,
            }
            if warehouse and warehouse.manu_type_id:
                vals['picking_type_id'] = warehouse.manu_type_id.id
            if 'date_deadline' in self.env['mrp.production']._fields:
                vals['date_deadline'] = line.date_required or self.date_end
            mo = self.env['mrp.production'].with_context(
                skip_compute_move_raw_ids=True
            ).create(vals)
            mo.action_confirm()

            # Transfer the planner lot allocation to the generated MO.
            line.production_component_ids.mapped(
                'lot_reservation_ids'
            ).filtered(
                lambda reservation: reservation.state == 'reserved'
            ).with_context(
                aps_allow_locked_lot_reservation_write=True
            ).write({
                'production_id': mo.id,
                'state': 'assigned',
            })

            line.write({
                'created_production_id': mo.id,
                'state': 'applied',
                'planned_production_qty': line.planner_production_qty,
            })
            productions |= mo

        return self.action_open_created_productions()


    def _ensure_product_purchase_vendor(self, line, vendor, purchase_line=False):
        """Remember a manually selected vendor on the product for future APS runs.

        If the vendor is already configured on the product, nothing is changed.
        Otherwise create a supplierinfo for the exact product variant.
        """
        self.ensure_one()
        product = line.product_id
        if not product or not vendor:
            return False

        commercial_vendor = vendor.commercial_partner_id
        existing = product.with_company(self.company_id).seller_ids.filtered(
            lambda seller: seller.partner_id.commercial_partner_id == commercial_vendor
        )[:1]
        if existing:
            return existing

        SupplierInfo = self.env['product.supplierinfo']
        vals = {
            'partner_id': commercial_vendor.id,
            'product_tmpl_id': product.product_tmpl_id.id,
            'product_id': product.id,
            'company_id': self.company_id.id,
            'sequence': 10,
        }

        # If the generated RFQ line already has a price, remember it as the
        # starting vendor price as well. Do not force fields that are not present.
        if purchase_line and 'price' in SupplierInfo._fields:
            vals['price'] = purchase_line.price_unit or 0.0
        if purchase_line and 'currency_id' in SupplierInfo._fields and purchase_line.order_id.currency_id:
            vals['currency_id'] = purchase_line.order_id.currency_id.id

        supplier = SupplierInfo.create(vals)
        self.message_post(body=_(
            'El proveedor %s fue agregado automáticamente al producto %s '
            'para futuras planificaciones de compras.'
        ) % (commercial_vendor.display_name, product.display_name))
        return supplier

    def action_create_purchases(self):
        self.ensure_one()
        self._check_plan_type_permission('purchase')
        if self.plan_type != 'purchase':
            raise UserError(_('Esta acción solo está disponible en una planificación de compras.'))

        lines = self._validate_selected_lines('action_purchase')
        Purchase = self.env['purchase.order']
        PurchaseLine = self.env['purchase.order.line']

        missing_vendor = lines.filtered(lambda line: not line.purchase_vendor_id)
        if missing_vendor:
            raise UserError(_(
                'Debe seleccionar un proveedor para cada producto a comprar:\n- %s'
            ) % '\n- '.join(missing_vendor.mapped('product_id.display_name')))

        # One RFQ per supplier and destination warehouse. In the common case
        # where the plan has a single warehouse, this means exactly one RFQ
        # per supplier for all products assigned to that supplier.
        grouped_pos = {}

        for line in lines:
            if line.created_purchase_line_id:
                continue

            warehouse = line.target_warehouse_id or self.warehouse_ids[:1]
            vendor = line.purchase_vendor_id.commercial_partner_id
            key = (vendor.id, warehouse.id if warehouse else False)

            po = grouped_pos.get(key)
            if not po:
                domain = [
                    ('state', '=', 'draft'),
                    ('advanced_plan_id', '=', self.id),
                    ('partner_id', '=', vendor.id),
                ]
                if warehouse and warehouse.in_type_id:
                    domain.append(('picking_type_id', '=', warehouse.in_type_id.id))

                po = Purchase.search(domain, limit=1)

                if not po:
                    po_vals = {
                        'partner_id': vendor.id,
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

            # If the planner had no product-default vendor and the user chose
            # one manually, remember it on the product for future purchases.
            self._ensure_product_purchase_vendor(line, po.partner_id, pol)

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
        self._check_plan_type_permission('purchase')
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
