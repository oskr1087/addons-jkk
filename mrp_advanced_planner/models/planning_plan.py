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
    date_start = fields.Date(required=True, default=fields.Date.context_today)
    date_end = fields.Date(string='Planificar hasta', required=True, tracking=True)
    priority = fields.Selection([('0', 'Normal'), ('1', 'Alta'), ('2', 'Urgente')], default='0', required=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Borrador'), ('calculated', 'Calculado'), ('approved', 'Finalizado'), ('cancelled', 'Cancelado')
    ], default='draft', required=True, index=True, tracking=True)
    calculated_at = fields.Date(readonly=True)
    approved_at = fields.Date(readonly=True)

    source_sale_line_ids = fields.Many2many(
        'sale.order.line',
        'mrp_planning_plan_source_sale_rel',
        'plan_id',
        'sale_line_id',
        string='Líneas de venta seleccionadas',
        readonly=True,
        copy=False,
        help='Cuando tiene valores, el cálculo APS se limita exactamente a estas líneas de venta.',
    )
    excluded_sale_line_ids = fields.Many2many(
        'sale.order.line',
        'mrp_planning_plan_excluded_sale_rel',
        'plan_id',
        'sale_line_id',
        string='Líneas de venta retiradas',
        readonly=True,
        copy=False,
        help=(
            'Líneas de venta retiradas manualmente de este APS. '
            'No vuelven a cargarse al recalcular.'
        ),
    )
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
    pending_component_manufacture_count = fields.Integer(compute='_compute_execution_status')

    total_sales_qty = fields.Float(compute='_compute_totals', string='Pedidos pendientes', digits=(16, 4))
    total_stock_qty = fields.Float(compute='_compute_totals', string='Pronóstico disponible', digits=(16, 4))
    total_open_mo_qty = fields.Float(compute='_compute_totals', string='OF abiertas', digits=(16, 4))
    total_suggested_qty = fields.Float(compute='_compute_totals', string='Necesidad neta', digits=(16, 4))
    total_to_manufacture_qty = fields.Float(compute='_compute_totals', string='A fabricar', digits=(16, 4))
    total_to_purchase_qty = fields.Float(compute='_compute_totals', string='A comprar', digits=(16, 4))
    total_to_move_qty = fields.Float(compute='_compute_totals', string='A mover', digits=(16, 4))

    def _aps_date_end_datetime(self):
        """End-of-day datetime for domains over Datetime fields."""
        self.ensure_one()
        if not self.date_end:
            return False
        return fields.Datetime.end_of(
            fields.Datetime.to_datetime(self.date_end), 'day'
        )

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
                sequence_code = (
                    'mrp.planning.plan.purchase'
                    if plan_type == 'purchase'
                    else 'mrp.planning.plan.manufacturing'
                )
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code(sequence_code)
                    or 'New'
                )
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

    def _aps_rollback_blockers(self, lines=None, whole_plan=False):
        """Return real execution that makes rollback unsafe.

        ``whole_plan=True`` is deliberately broader than the current APS lines.
        A recalculation may have replaced/removed a planning line after a
        transfer/PO/OF was created.  Plan cancellation must therefore inspect
        EVERY document still linked to the plan (and its generated purchase
        plan), not only documents reachable through current line ids.
        """
        self.ensure_one()
        lines = (lines or self.line_ids).exists()
        blockers = []

        components = self.production_component_ids.filtered(
            lambda component: component.planning_line_id in lines
        )
        generated_purchase_lines = components.mapped(
            'generated_purchase_plan_line_id'
        ).exists()

        # ----- Manufacturing -----
        mo_domain = [('advanced_plan_id', '=', self.id)]
        if not whole_plan:
            mo_domain.append(
                ('planning_plan_line_id', 'in', lines.ids)
            )
        productions = self.env['mrp.production'].sudo().search(
            mo_domain
        )
        # Also include explicit links retained on root/subcomponent records.
        productions |= lines.mapped('created_production_id').sudo().exists()
        productions |= components.mapped(
            'generated_production_id'
        ).sudo().exists()

        for mo in productions:
            if mo.state == 'done':
                blockers.append(
                    _('OF %s: ya está finalizada.') % mo.display_name
                )
                continue
            if mo.state == 'cancel':
                continue
            done_moves = (
                mo.move_raw_ids | mo.move_finished_ids
            ).filtered(lambda move: move.state == 'done')
            if done_moves:
                blockers.append(_(
                    'OF %s: ya tiene movimientos de inventario realizados.'
                ) % mo.display_name)

        # ----- Purchases -----
        PurchaseLine = self.env['purchase.order.line'].sudo()
        purchase_lines = PurchaseLine
        if whole_plan:
            plan_ids = self.ids
            if self.generated_purchase_plan_id:
                plan_ids += self.generated_purchase_plan_id.ids
            purchase_lines |= PurchaseLine.search([
                ('order_id.advanced_plan_id', 'in', plan_ids),
            ])
        else:
            purchase_lines |= PurchaseLine.search([
                ('planning_plan_line_id', 'in',
                 generated_purchase_lines.ids),
            ])
            # Compatibility for direct purchase plans / older data.
            purchase_lines |= PurchaseLine.search([
                ('planning_plan_line_id', 'in', lines.ids),
            ])

        for pol in purchase_lines:
            if (getattr(pol, 'qty_received', 0.0) or 0.0) > 1e-9:
                blockers.append(_(
                    'Compra %s: %s ya tiene %.4f recibido.'
                ) % (
                    pol.order_id.display_name,
                    pol.product_id.display_name,
                    pol.qty_received,
                ))
                continue
            done_receipts = pol.move_ids.filtered(
                lambda move: move.state == 'done'
            )
            if done_receipts:
                blockers.append(_(
                    'Compra %s: %s ya tiene recepción/movimiento realizado.'
                ) % (
                    pol.order_id.display_name,
                    pol.product_id.display_name,
                ))

        # ----- Internal transfers -----
        Picking = self.env['stock.picking'].sudo()
        if whole_plan:
            pickings = Picking.search([
                ('advanced_plan_id', '=', self.id),
            ])
        else:
            pickings = lines.mapped('created_picking_ids').sudo().exists()
            pickings |= Picking.search([
                ('advanced_plan_id', '=', self.id),
                ('move_ids.planning_plan_line_id', 'in', lines.ids),
            ])

        for picking in pickings:
            if picking.state == 'done':
                blockers.append(_(
                    'Traslado %s: ya fue validado.'
                ) % picking.display_name)
                continue
            done_moves = picking.move_ids.filtered(
                lambda move: move.state == 'done'
            )
            if done_moves:
                blockers.append(_(
                    'Traslado %s: ya tiene movimientos realizados.'
                ) % picking.display_name)

        # ----- Lot consumption -----
        reservation_domain = [('state', '=', 'consumed')]
        if whole_plan:
            reservation_domain.append(('plan_id', '=', self.id))
        else:
            reservation_domain.append(
                ('planning_line_id', 'in', lines.ids)
            )
        consumed = self.env[
            'mrp.planning.component.lot.reservation'
        ].sudo().search(reservation_domain)
        if consumed:
            blockers.append(_(
                '%s reserva(s) APS de lote ya fueron consumidas.'
            ) % len(consumed))

        return blockers

    def _aps_cancel_documents_for_lines(self, lines):
        """Cancel only unexecuted documents belonging to selected APS roots."""
        self.ensure_one()
        lines = lines.exists()
        if not lines:
            return True

        Production = self.env['mrp.production'].sudo()
        PurchaseLine = self.env['purchase.order.line'].sudo()
        Picking = self.env['stock.picking'].sudo()

        components = self.production_component_ids.filtered(
            lambda component: component.planning_line_id in lines
        )

        # OF root + sub-OF: use both traceability fields and explicit stored
        # links so old/recalculated rows cannot hide a generated document.
        productions = Production.search([
            ('advanced_plan_id', '=', self.id),
            ('planning_plan_line_id', 'in', lines.ids),
        ])
        productions |= lines.mapped('created_production_id').sudo().exists()
        productions |= components.mapped(
            'generated_production_id'
        ).sudo().exists()
        active_mos = productions.filtered(
            lambda mo: mo.state not in ('done', 'cancel')
        )
        if active_mos:
            active_mos.action_cancel()

        # Release logical APS lot ownership before deleting components.
        reservations = self.env[
            'mrp.planning.component.lot.reservation'
        ].sudo().search([
            ('planning_line_id', 'in', lines.ids),
            ('state', 'in', ('reserved', 'assigned')),
        ])
        if reservations:
            reservations.with_context(
                aps_allow_locked_lot_reservation_write=True
            ).write({
                'state': 'released',
                'production_id': False,
            })

        # Generated purchase plan uses ITS OWN plan-line ids. Resolve the exact
        # contribution from component.generated_purchase_plan_line_id.
        generated_purchase_lines = components.mapped(
            'generated_purchase_plan_line_id'
        ).exists()
        purchase_lines = PurchaseLine.search([
            ('planning_plan_line_id', 'in',
             generated_purchase_lines.ids),
        ]) if generated_purchase_lines else PurchaseLine
        # Compatibility for direct/legacy planner data.
        purchase_lines |= PurchaseLine.search([
            ('planning_plan_line_id', 'in', lines.ids),
        ])
        affected_pos = purchase_lines.mapped('order_id')
        if purchase_lines:
            purchase_lines.unlink()
        for po in affected_pos.exists():
            if not po.order_line and po.state not in ('done', 'cancel'):
                po.button_cancel()

        # Transfers: created_picking_ids is authoritative for a root line.
        # The move traceability search remains for legacy data.
        pickings = lines.mapped('created_picking_ids').sudo().exists()
        pickings |= Picking.search([
            ('advanced_plan_id', '=', self.id),
            ('move_ids.planning_plan_line_id', 'in', lines.ids),
        ])
        active_pickings = pickings.filtered(
            lambda picking: picking.state not in ('done', 'cancel')
        )
        if active_pickings:
            active_pickings.action_cancel()

        # A cancelled manufacturing order keeps its stock moves. Remove the
        # APS component FK from those moves before the engineering snapshot can
        # be deleted. Do not delete stock moves or stock history.
        production_moves = productions.exists().mapped(
            'move_raw_ids'
        ) | productions.exists().mapped('move_finished_ids')
        if production_moves:
            production_moves.with_context(aps_rollback=True).write({
                'aps_planning_component_id': False,
            })

        # Remove APS links only after successful cancellation.
        productions.exists().with_context(aps_rollback=True).write({
            'advanced_plan_id': False,
            'planning_plan_line_id': False,
            'planning_sale_line_id': False,
            'aps_planning_component_id': False,
            'aps_component_snapshot': False,
        })
        for po in affected_pos.exists():
            if not po.order_line.filtered('planning_plan_line_id'):
                po.with_context(aps_rollback=True).write({
                    'advanced_plan_id': False,
                })
        pickings.exists().with_context(aps_rollback=True).write({
            'advanced_plan_id': False,
        })
        pickings.exists().mapped('move_ids').with_context(
            aps_rollback=True
        ).write({
            'planning_plan_line_id': False,
            'aps_planning_component_id': False,
        })
        return True

    def _aps_cleanup_generated_purchase_plan(self):
        """Keep the auto purchase plan aligned after removing MFG roots."""
        self.ensure_one()
        purchase_plan = self.generated_purchase_plan_id.sudo().exists()
        if not purchase_plan:
            return True

        # Executed receipts are impossible here because root rollback pre-check
        # would have blocked. Rebuild only when the generated purchase plan is
        # still operational/editable.
        if purchase_plan.state in ('draft', 'calculated'):
            # Remove stale lines that no longer have a manufacturing origin.
            valid_sale_lines = self.line_ids.mapped('sale_line_ids')
            stale = purchase_plan.line_ids.filtered(
                lambda line:
                    line.source_type == 'mrp'
                    and line.sale_line_ids
                    and not (line.sale_line_ids & valid_sale_lines)
            )
            if stale:
                stale.with_context(aps_rollback=True).unlink()
        return True

    def _aps_rollback_lines(self, lines, cancel_plan=False):
        """Atomic rollback of one or more root products."""
        self.ensure_one()
        lines = lines.exists().filtered(lambda line: line.plan_id == self)
        if not lines:
            return True
        blockers = self._aps_rollback_blockers(lines)
        if blockers:
            raise UserError(_(
                'No se puede revertir la planificación porque ya existe '
                'ejecución real:\n\n- %s'
            ) % '\n- '.join(blockers))

        products = ', '.join(lines.mapped('product_id.display_name'))
        sale_lines = lines.mapped('sale_line_ids') | lines.mapped('sale_line_id')

        self._aps_cancel_documents_for_lines(lines)

        # Remove generated-purchase links before deleting the engineering tree.
        components = self.production_component_ids.filtered(
            lambda component: component.planning_line_id in lines
        )
        components.with_context(
            aps_skip_sourcing_refresh=True,
            aps_rollback=True,
        ).write({
            'generated_production_id': False,
            'generated_purchase_plan_line_id': False,
        })

        # Cancelled MOs keep their stock.move rows as Odoo history. Detach
        # those rows from the APS engineering snapshot before deleting the
        # snapshot. This includes raw moves of the root OF and any legacy/native
        # manufacturing move that still references an APS component.
        component_subtree = components
        frontier = components
        while frontier:
            children = frontier.mapped('child_line_ids') - component_subtree
            if not children:
                break
            component_subtree |= children
            frontier = children
        linked_stock_moves = self.env['stock.move'].sudo().search([
            ('aps_planning_component_id', 'in', component_subtree.ids),
        ])
        if linked_stock_moves:
            linked_stock_moves.with_context(aps_rollback=True).write({
                'aps_planning_component_id': False,
            })

        # External suggestions/pending rows are planning-only data.
        self.external_move_ids.filtered(
            lambda move: move.planning_line_id in lines
            or move.production_component_id in components
        ).with_context(aps_rollback=True).unlink()

        # The line cascade removes component snapshots, reservations and the
        # M2M sale-line relation. This is what releases the SO for another APS.
        lines.with_context(
            aps_rollback=True,
            aps_skip_sourcing_refresh=True,
        ).unlink()

        # source_sale_line_ids is only the original calendar scope. Remove the
        # released SO lines as well so the plan itself keeps no traceability.
        if sale_lines:
            remaining_source = self.source_sale_line_ids - sale_lines
            self.sudo().write({
                'source_sale_line_ids': [(6, 0, remaining_source.ids)],
            })

        self._aps_cleanup_generated_purchase_plan()
        if not cancel_plan and self.plan_type == 'manufacturing' and self.state == 'calculated':
            self._refresh_component_sourcing()

        self.message_post(body=_(
            'APS retiró de la planificación: %s. Se liberaron lotes y líneas '
            'de venta, y se cancelaron los documentos APS no ejecutados.'
        ) % products)
        return True

    def action_cancel_plan(self):
        """Cancel the complete plan only when no real execution exists."""
        for plan in self:
            if plan.state == 'cancelled':
                continue
            plan._check_plan_type_permission()
            lines = plan.line_ids
            blockers = plan._aps_rollback_blockers(
                lines,
                whole_plan=True,
            )
            if blockers:
                raise UserError(_(
                    'No se puede cancelar %s porque ya existe ejecución real:'
                    '\n\n- %s'
                ) % (plan.display_name, '\n- '.join(blockers)))

            if lines:
                plan._aps_rollback_lines(lines, cancel_plan=True)

            purchase_plan = plan.generated_purchase_plan_id.sudo().exists()
            if purchase_plan:
                # At this point no executed contribution can remain.
                if purchase_plan.line_ids:
                    purchase_plan.line_ids.with_context(
                        aps_rollback=True
                    ).unlink()
                purchase_plan.with_context(aps_rollback=True).write({
                    'source_sale_line_ids': [(5, 0, 0)],
                    'source_manufacturing_plan_id': False,
                    'state': 'cancelled',
                })
                plan.sudo().write({'generated_purchase_plan_id': False})

            plan.with_context(aps_rollback=True).write({
                'source_sale_line_ids': [(5, 0, 0)],
                'needs_recalculation': False,
                'state': 'cancelled',
            })
            plan.message_post(body=_(
                'Planificación cancelada. Se liberaron reservas de lote y '
                'pedidos de venta; los documentos APS sin ejecución fueron '
                'cancelados y se eliminó su trazabilidad APS.'
            ))
        return True

    def unlink(self):
        protected = self.filtered(
            lambda plan:
                plan.state != 'cancelled'
                and (
                    plan.line_ids
                    or plan.source_sale_line_ids
                    or plan.created_mo_count
                    or plan.created_po_count
                    or plan.created_transfer_count
                )
        )
        if protected and not self.env.context.get('aps_rollback'):
            raise UserError(_(
                'Use "Cancelar planificación" antes de eliminar un APS. '
                'Así Odoo libera lotes, ventas y documentos relacionados '
                'de forma segura.'
            ))
        return super().unlink()

    def write(self, vals):
        res = super().write(vals)
        if 'warehouse_ids' in vals:
            self._sync_legacy_warehouse()

        # A cancelled plan must never keep lots blocked for future APS plans.
        if vals.get('state') == 'cancelled':
            reservations = self.env[
                'mrp.planning.component.lot.reservation'
            ].sudo().search([
                ('plan_id', 'in', self.ids),
                ('state', 'in', ('reserved', 'assigned')),
            ])
            if reservations:
                reservations.with_context(
                    aps_allow_locked_lot_reservation_write=True
                ).write({
                    'state': 'released',
                    'production_id': False,
                })
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
            # El smart button "OF" del plan muestra únicamente las OF raíz
            # creadas directamente por APS. Las sub-OF nativas de Odoo se
            # consultan desde la OF padre mediante su trazabilidad.
            plan.created_mo_count = Production.search_count([
                ('advanced_plan_id', '=', plan.id),
                ('aps_parent_production_id', '=', False),
                ('planning_plan_line_id', '!=', False),
            ])
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
            plan.pending_component_manufacture_count = len(
                plan.production_component_ids.filtered(
                    lambda component:
                        component.include_in_mo
                        and component.supply_resolution in (
                            'manufacture', 'move_manufacture'
                        )
                        and component.pending_manufacture_qty > 1e-9
                        and component.planning_line_id.created_production_id
                        and component.planning_line_id.created_production_id.state
                            not in ('done', 'cancel')
                )
            )

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

    @api.constrains('date_end')
    def _check_dates(self):
        for plan in self:
            if not plan.date_end or not plan.create_date:
                continue

            # create_date se guarda en UTC. Como date_end es un campo Date,
            # la validación debe usar la fecha LOCAL del usuario y no la fecha
            # UTC, que puede haber cambiado ya al día siguiente.
            local_created_dt = fields.Datetime.context_timestamp(
                plan,
                plan.create_date,
            )
            creation_date = local_created_dt.date()

            if plan.date_end < creation_date:
                raise ValidationError(_(
                    'La fecha límite no puede ser anterior a la fecha de creación del plan.'
                ))

    @api.constrains('warehouse_ids', 'company_id')
    def _check_warehouse_company(self):
        for plan in self:
            if plan.warehouse_ids.filtered(lambda wh: wh.company_id != plan.company_id):
                raise ValidationError(_('Todos los almacenes seleccionados deben pertenecer a la compañía del plan.'))

    def _has_generated_documents(self):
        self.ensure_one()
        return bool(
            self.line_ids.filtered(
                lambda line:
                    line.created_production_id
                    or line.created_purchase_line_id
                    or line.created_picking_ids
            )
        )

    def _aps_repair_native_submanufacturing_chain(self):
        """Ensure the complete native sub-MO tree exists and is usable.

        The identity of a submanufacturing need is the exact APS component /
        downstream raw move, not merely the product.  Therefore the same
        semi-finished product can legitimately generate two child MOs when it
        is required by two different parent branches.

        This routine is intentionally called from BOTH Recalcular and
        Fabricar.  It also repairs the specific legacy defect where a native
        APS child MO was created while ``skip_compute_move_raw_ids`` leaked
        from its parent and consequently had no raw components.
        """
        self.ensure_one()
        if self.plan_type != 'manufacturing':
            return self.env['mrp.production']

        Production = self.env['mrp.production'].sudo()
        all_touched = Production

        # A finite fixed-point loop lets each newly created child expose its
        # own fabricable descendants.  32 levels is far beyond a sensible BoM
        # depth and also protects against malformed circular configurations.
        for _iteration in range(32):
            productions = Production.search([
                ('advanced_plan_id', '=', self.id),
                ('state', 'not in', ('done', 'cancel')),
            ], order='id')
            if not productions:
                break

            before_ids = set(productions.ids)
            repaired_any = False

            # First restore APS identity on raw moves of chains generated by
            # older/native flows.  Correct physical moves without the APS node
            # link are not enough: recursive procurement needs the exact
            # component identity to create the next child MO.
            for mo in productions.filtered(
                lambda production:
                    production.aps_component_snapshot
                    and production.planning_plan_line_id
            ):
                adopted = mo._aps_adopt_existing_raw_moves()
                if adopted:
                    repaired_any = True
                    all_touched |= mo

            # Repair only the known malformed case: an APS child/root that
            # should have direct snapshot components but has no active raw
            # moves at all.  We do not rewrite partially executed structures.
            for mo in productions.filtered(
                lambda production:
                    production.aps_component_snapshot
                    and production.planning_plan_line_id
            ):
                active_raw = mo.move_raw_ids.filtered(
                    lambda move: move.state != 'cancel'
                )
                expected = mo._aps_snapshot_components()
                if expected and not active_raw:
                    clean_mo = mo.with_context(
                        skip_compute_move_raw_ids=False
                    )
                    created = clean_mo._aps_sync_raw_moves()
                    draft_moves = created.filtered(
                        lambda move: move.state == 'draft'
                    )
                    if draft_moves:
                        # Confirm the repaired raw demand so native stock rules
                        # can create the next submanufacturing level.
                        draft_moves.with_context(
                            skip_compute_move_raw_ids=False
                        )._action_confirm()
                    if clean_mo.state not in ('done', 'cancel'):
                        clean_mo.action_assign()
                    repaired_any = True
                    all_touched |= clean_mo

            # Launch every still-missing fabricable demand.  The method uses
            # the exact APS component/raw move and is idempotent when an
            # upstream manufacturing move already feeds that demand.
            launched = productions.with_context(
                skip_compute_move_raw_ids=False
            )._aps_launch_missing_component_procurements()

            self._aps_link_manufacturing_chain()

            after = Production.search([
                ('advanced_plan_id', '=', self.id),
                ('state', 'not in', ('done', 'cancel')),
            ], order='id')
            all_touched |= after
            new_ids = set(after.ids) - before_ids

            if not new_ids and not launched and not repaired_any:
                break
        else:
            raise UserError(_(
                'APS no pudo estabilizar la cadena de subfabricaciones luego '
                'de 32 niveles. Revise si existe una LdM circular.'
            ))

        self._aps_link_manufacturing_chain()
        return all_touched


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

        # Recalcular is the authoritative engineering refresh too.  Complete
        # any missing positive BoM node before sourcing is evaluated, otherwise
        # a fabricable descendant can disappear from the execution matrix even
        # though the parent snapshot looks valid.  The builder is additive and
        # preserves substitutions/manual planner decisions.
        if self.plan_type == 'manufacturing' and self.line_ids:
            from ..services.manufacturing_snapshot import ManufacturingSnapshotBuilder
            snapshot_lines = self.line_ids.filtered(
                lambda line: line.bom_id and line.planner_production_qty > 1e-9
            )
            if snapshot_lines:
                ManufacturingSnapshotBuilder(self).ensure_complete(snapshot_lines)

        # CALCULAR / RECALCULAR is analysis-only.  It may refresh the
        # sourcing decision (Disponible / Mover / Fabricar / Comprar), but it
        # MUST NOT create or repair execution documents.  In particular:
        #   - no linked purchase plan is created here,
        #   - no purchase order is created here,
        #   - no manufacturing procurement is launched here,
        #   - no child MO is created/repaired here.
        # Execution is deliberately isolated in the explicit Fabricar /
        # Comprar / Reabastecer actions.
        if self.plan_type == 'manufacturing' and self.production_component_ids:
            self._refresh_component_sourcing()


        # A search with no demand/results must remain reusable.  Moving the
        # plan to Calculated here used to lock date_end/warehouses in the form,
        # forcing the user to create a new plan just to try another horizon.
        if not result_count and self._has_generated_documents():
            # No additional proposal is required. Existing OF/PO/transfers are
            # preserved and already cover the current demand.
            self.write({
                'state': 'calculated',
                'calculated_at': fields.Date.context_today(self),
                'needs_recalculation': False,
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('APS actualizado'),
                    'message': _(
                        'Se recalculó la planificación sin recrear documentos. '
                        'Las órdenes de fabricación, compras y traslados ya '
                        'generados se conservaron y no existen necesidades '
                        'adicionales por generar.'
                    ),
                    'type': 'success',
                    'sticky': False,
                },
            }

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
            'calculated_at': fields.Date.context_today(self),
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
        lines = self.env['sale.order.line'].search([
            ('order_id.state', '=', 'sale'),
            ('order_id.company_id', '=', self.company_id.id),
            ('order_id.warehouse_id', 'in', self.warehouse_ids.ids),
            ('product_id', '!=', False),
            ('display_type', '=', False),
            ('planning_delivery_date', '!=', False),
            ('planning_delivery_date', '<=', self.date_end),
        ]).filtered(
            lambda sl:
                sl.product_uom_qty - sl.qty_delivered > 0
                and fields.Date.to_date(sl.planning_delivery_date) <= self.date_end
        )

        # Use the same cross-plan commitment rule as the planning engine.
        from ..services.simple_planning_engine import SimplePlanningEngine
        committed = SimplePlanningEngine(
            self
        )._sale_lines_already_committed_to_aps(lines)
        return lines - committed - self.excluded_sale_line_ids

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
                'approved_at': fields.Date.context_today(self),
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
                'date_start': fields.Date.context_today(self),
                'date_end': self.date_end,
                'priority': self.priority,
                'warehouse_ids': [(6, 0, self.warehouse_ids.ids)],
                'source_manufacturing_plan_id': self.id,
                'state': 'calculated',
                'calculated_at': fields.Date.context_today(self),
            })
            self.sudo().write({'generated_purchase_plan_id': purchase_plan.id})
        else:
            purchase_plan.line_ids.unlink()
            purchase_plan.write({
                'date_end': self.date_end,
                'warehouse_ids': [(6, 0, self.warehouse_ids.ids)],
                'state': 'calculated',
                'calculated_at': fields.Date.context_today(self),
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

        component_need_count = len(components)
        purchase_product_count = len(purchase_plan.line_ids)
        purchase_plan.message_post(body=_(
            'Plan de compras preparado explícitamente desde %(plan)s con '
            '%(needs)s necesidad(es) de componente consolidadas en '
            '%(products)s producto(s) a comprar.'
        ) % {
            'plan': self.name,
            'needs': component_need_count,
            'products': purchase_product_count,
        })
        self.message_post(body=_(
            'Se generó/actualizó automáticamente el PLAN de compras %(purchase)s con '
            '%(needs)s necesidad(es) de componentes. Cuando el mismo producto '
            'aparece en varias ramas de la LdM, APS consolida sus cantidades '
            'en una sola línea de compra.'
        ) % {
            'purchase': purchase_plan.name,
            'needs': component_need_count,
        })
        return purchase_plan

    def _aps_validate_created_mo_lot_links(self, productions):
        """Validate logical APS lot ownership after MO confirmation.

        We intentionally do NOT rewrite stock.move.line reservations here.
        Odoo remains owner of physical stock reservation; APS only validates
        that each tracked direct component has its logical reservation linked
        to the correct MO. This avoids affecting non-APS MRP behavior.
        """
        for production in productions.filtered(
            lambda mo:
                mo.aps_component_snapshot
                and mo.state not in ('done', 'cancel')
        ):
            for component in production._aps_snapshot_components().filtered(
                lambda row:
                    row.include_in_mo
                    and row.product_id.tracking != 'none'
                    and row._aps_effective_lot_target_qty() > 1e-9
            ):
                reservations = component.lot_reservation_ids.filtered(
                    lambda reservation:
                        reservation.state in ('reserved', 'assigned')
                )
                wrong_owner = reservations.filtered(
                    lambda reservation:
                        reservation.production_id
                        and reservation.production_id != production
                )
                if wrong_owner:
                    raise UserError(_(
                        'La reserva APS del componente %(component)s quedó '
                        'asociada a una OF diferente.\n\n'
                        'OF actual: %(current)s\n'
                        'OF de la reserva: %(owner)s\n\n'
                        'Reasigne los lotes antes de continuar.'
                    ) % {
                        'component': component.product_id.display_name,
                        'current': production.display_name,
                        'owner': wrong_owner[:1].production_id.display_name,
                    })
        return True

    def _aps_validate_component_execution_matrix(self):
        self.ensure_one()
        errors = []
        for component in self.production_component_ids.filtered(
            lambda c: c.include_in_mo and c.effective_required_qty > 1e-9
        ):
            resolution = component.supply_resolution
            children = component.child_line_ids.filtered('include_in_mo')
            if (
                resolution in ('manufacture', 'move_manufacture')
                and component.to_manufacture_qty > 1e-9
                and not children
            ):
                # A normal BoM with no positive component lines is a valid
                # manufacturing leaf: it still requires its own native sub-OF.
                # Only flag the snapshot as incomplete when the applicable
                # BoM really has material lines that should have been exploded.
                from ..services.odoo19_compat import find_bom
                warehouse = (
                    component.planning_line_id.target_warehouse_id
                    or self.warehouse_ids[:1]
                )
                bom = find_bom(
                    self.env,
                    component.product_id,
                    company_id=self.company_id.id,
                    picking_type_id=(
                        warehouse.manu_type_id.id
                        if warehouse and warehouse.manu_type_id else False
                    ),
                )
                positive_lines = (
                    bom.bom_line_ids.filtered(lambda line: line.product_qty > 0)
                    if bom and bom.type == 'normal'
                    else self.env['mrp.bom.line']
                )
                if positive_lines:
                    errors.append(
                        _('%s: fabricar sin estructura explotada.')
                        % component.product_id.display_name
                    )
            if (
                resolution in ('subcontract', 'move_subcontract')
                and not component.subcontract_bom_id
            ):
                errors.append(
                    _('%s: subcontratación sin LdM de subcontratación.')
                    % component.product_id.display_name
                )
            if resolution == 'phantom' and not children:
                errors.append(
                    _('%s: kit/phantom sin componentes explotados.')
                    % component.product_id.display_name
                )
        if errors:
            raise UserError(_(
                'APS detectó inconsistencias antes de generar documentos:\n\n- %s'
            ) % '\n- '.join(errors))
        return True

    def _create_component_manufacturing_orders(self):
        """Compatibility shim.

        APS no longer creates component/sub-MOs explicitly. The root MO is
        confirmed normally and Odoo procurement creates any required
        submanufacturing according to routes and BoMs.
        """
        self.ensure_one()
        return self.env['mrp.production']


    def _aps_link_manufacturing_chain(self):
        """Connect each sub-MO to the exact parent demand using native moves."""
        self.ensure_one()
        for component in self.production_component_ids.filtered(
            lambda c: c.generated_production_id
        ):
            child_mo = component.generated_production_id.exists()
            parent_component = component.parent_line_id
            parent_mo = (
                parent_component.generated_production_id
                if parent_component and parent_component.generated_production_id
                else component.planning_line_id.created_production_id
            ).exists()
            if not child_mo or not parent_mo:
                continue

            child_mo.sudo().write({'aps_parent_production_id': parent_mo.id})

            # Repair logical lot ownership for existing/native child MOs.
            # Every reservation of the child's executable direct components
            # must belong to that child MO, never to the parent/root MO.
            if child_mo.aps_component_snapshot and child_mo.aps_planning_component_id:
                child_direct_components = child_mo._aps_snapshot_components()
                child_direct_components.mapped(
                    'lot_reservation_ids'
                ).filtered(
                    lambda reservation:
                        reservation.state in ('reserved', 'assigned')
                ).with_context(
                    aps_allow_locked_lot_reservation_write=True
                ).write({
                    'production_id': child_mo.id,
                    'state': 'assigned',
                })

            demand_moves = parent_mo.move_raw_ids.filtered(
                lambda move:
                    move.state != 'cancel'
                    and move.aps_planning_component_id == component
                    and move.product_id == component.product_id
            )
            supply_moves = child_mo.move_finished_ids.filtered(
                lambda move:
                    move.state != 'cancel'
                    and move.product_id == component.product_id
            )
            if demand_moves and supply_moves:
                commands = [(4, move.id) for move in supply_moves]
                for demand in demand_moves:
                    demand.sudo().write({'move_orig_ids': commands})
        return True

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
        """Prepare/open the component purchase plan only on explicit click.

        Manufacturing calculation merely classifies component shortages.
        Creating the linked purchase *planning* document is an explicit user
        action; actual RFQs/POs are still created only from that purchase plan
        with its Comprar action.
        """
        self.ensure_one()
        if self.plan_type != 'manufacturing':
            return False
        if self.state not in ('calculated', 'approved'):
            raise UserError(_(
                'Primero calcule la planificación antes de preparar el plan de compras.'
            ))

        self._refresh_component_sourcing()
        purchase_plan = self._sync_component_purchase_plan()
        if not purchase_plan:
            raise UserError(_(
                'No existen componentes pendientes de compra en esta planificación.'
            ))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Plan de compras de componentes'),
            'res_model': 'mrp.planning.plan',
            'res_id': purchase_plan.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    def _aps_validate_no_duplicate_engineering_rows(self, lines):
        """Block execution if an old APS snapshot already contains duplicates.

        We intentionally do not auto-delete them because one of the duplicated
        rows may have been edited/substituted by a planner. A fresh/recalculated
        snapshot can be repaired safely before document creation.
        """
        self.ensure_one()
        duplicates = []
        for line in lines:
            seen = {}
            rows = line.production_component_ids.filtered(
                lambda c:
                    c.source_bom_line_id
                    and c.change_type == 'original'
                    and c.include_in_mo
            )
            for row in rows.sorted('id'):
                key = (
                    row.parent_line_id.id or 0,
                    row.source_bom_line_id.id,
                )
                previous = seen.get(key)
                if previous:
                    duplicates.append(
                        '%s → %s'
                        % (
                            row.parent_line_id.product_id.display_name
                            if row.parent_line_id
                            else line.product_id.display_name,
                            row.product_id.display_name,
                        )
                    )
                else:
                    seen[key] = row
        if duplicates:
            raise UserError(_(
                'La estructura APS contiene componentes duplicados generados '
                'por una versión anterior del planificador. Recalcule el plan '
                'antes de fabricar para reconstruir la estructura sin '
                'duplicados:\n\n- %s'
            ) % '\n- '.join(sorted(set(duplicates))))
        return True

    def _aps_validate_no_duplicate_executed_sale_demand(self, lines):
        """Prevent a second root MO for direct demand already executed here."""
        self.ensure_one()
        existing = self.line_ids.filtered(
            lambda line:
                line.created_production_id
                and line.created_production_id.state != 'cancel'
        )
        errors = []
        for line in lines:
            if line.created_production_id:
                continue
            direct_sales = (line.sale_line_ids or line.sale_line_id).filtered(
                lambda sale_line:
                    sale_line.product_id == line.product_id
            )
            if not direct_sales:
                continue
            overlap = existing.filtered(
                lambda other:
                    other != line
                    and other.product_id == line.product_id
                    and bool(
                        (other.sale_line_ids or other.sale_line_id)
                        & direct_sales
                    )
            )
            if overlap:
                errors.append(line.product_id.display_name)

        if errors:
            raise UserError(_(
                'APS detectó demanda de venta ya cubierta por una OF del '
                'mismo plan. Recalcule antes de fabricar. Productos: %s'
            ) % ', '.join(sorted(set(errors))))
        return True



    def action_create_manufacturing(self):
        self.ensure_one()
        self._check_plan_type_permission('manufacturing')
        if self.plan_type != 'manufacturing':
            raise UserError(_(
                'Esta acción solo está disponible en una planificación de fabricación.'
            ))

        lines = self._validate_selected_lines('action_manufacture')
        self._aps_validate_no_duplicate_executed_sale_demand(lines)
        missing_bom = lines.filtered(lambda l: not l.bom_id)
        if missing_bom:
            raise UserError(_('No se puede fabricar sin LdM:\n- %s') % '\n- '.join(
                missing_bom.mapped('product_id.display_name')
            ))

        # Validate/repair the engineering snapshot immediately before
        # execution. This catches BoM lines lost by old rounding/precision
        # logic without deleting substitutions or manual APS edits.
        from ..services.manufacturing_snapshot import ManufacturingSnapshotBuilder
        repaired = ManufacturingSnapshotBuilder(self).ensure_complete(lines)
        if repaired:
            self.message_post(body=_(
                'APS corrigió %s componente(s) faltante(s) de la estructura '
                'antes de generar fabricación.'
            ) % len(repaired))

        # Never propagate a duplicated engineering snapshot into stock.move.
        self._aps_validate_no_duplicate_engineering_rows(lines)

        # Re-evaluate sourcing after repairing the complete exploded structure.
        self._refresh_component_sourcing()
        self._aps_validate_component_execution_matrix()

        # APS classifies the complete component tree, but it creates ONLY the
        # finished-product MO. Fabricable component supply is delegated to
        # Odoo's native procurement/manufacturing chain when the root MO is
        # confirmed. This prevents duplicate sub-MOs and duplicate tree nodes.
        #
        # Fabricar is the execution boundary for a manufacturing plan.
        # At this point the engineering/sourcing snapshot is final, so create
        # or refresh the RELATED PURCHASE PLAN for every component classified
        # as Comprar faltante.  This does NOT create RFQs/POs: those remain an
        # explicit action from the generated purchase plan (Comprar).
        #
        # Important: CALCULAR / RECALCULAR never call this synchronization.
        # This keeps analysis free of execution side effects while ensuring
        # that Fabricar leaves both manufacturing and purchasing work ready.
        self._sync_component_purchase_plan()

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
            # Do not keep the create-only snapshot guard in the recordset
            # context.  mrp.production.action_confirm applies it locally where
            # needed, while native stock.rule child creation must remain clean.
            mo = mo.with_context(skip_compute_move_raw_ids=False)

            # The finished-product MO owns ONLY its direct snapshot
            # components. Descendant reservations belong to the corresponding
            # semiterminated/component MOs created above.
            mo._aps_snapshot_components().mapped(
                'lot_reservation_ids'
            ).filtered(
                lambda reservation:
                    reservation.state in ('reserved', 'assigned')
            ).with_context(
                aps_allow_locked_lot_reservation_write=True
            ).write({
                'production_id': mo.id,
                'state': 'assigned',
            })

            mo.action_confirm()

            # Defensive Odoo-19 path: APS raw moves are a frozen snapshot.
            # Ensure fabricable MTO component demand actually enters the
            # native procurement chain even when the raw move confirmation did
            # not launch it automatically.
            mo._aps_launch_missing_component_procurements()
            self._aps_link_manufacturing_chain()
            self._aps_validate_created_mo_lot_links(mo)

            line.write({
                'created_production_id': mo.id,
                'state': 'applied',
                'planned_production_qty': line.planner_production_qty,
            })
            productions |= mo

        # Fabricar must leave the complete native hierarchy ready in the same
        # transaction, not wait for a later Recalcular.  This also guarantees
        # distinct child MOs when the same semi-finished product is demanded
        # by different parent branches.
        self._aps_repair_native_submanufacturing_chain()

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

    def action_create_selected_external_transfers(self):
        """Create one internal picking for the selected external-stock rows.

        The selected rows must share exactly the same source and destination
        warehouses.  We deliberately keep one stock.move per APS row so the
        traceability back to the planning line/component remains intact.
        """
        self.ensure_one()
        self._check_plan_type_permission('manufacturing')

        if self.plan_type != 'manufacturing':
            raise UserError(_('La transferencia múltiple está disponible únicamente en la planificación de fabricación.'))
        if self.state != 'calculated':
            raise UserError(_('Solo puede transferir desde una planificación calculada.'))

        rows = self.external_move_ids.filtered(
            lambda row: row.selected_for_transfer
            and row.state == 'pending'
            and row.move_qty > 1e-6
        )
        if not rows:
            raise UserError(_(
                'Seleccione al menos una línea pendiente con una cantidad a transferir mayor que cero.'
            ))

        routes = {
            (row.source_warehouse_id.id, row.destination_warehouse_id.id)
            for row in rows
        }
        if len(routes) != 1:
            route_labels = sorted({
                '%s → %s' % (
                    row.source_warehouse_id.display_name,
                    row.destination_warehouse_id.display_name,
                )
                for row in rows
            })
            raise UserError(_(
                'No se pueden generar en una misma transferencia componentes con rutas diferentes.\n\n'
                'Seleccione líneas con el mismo almacén de origen y destino.\n\nRutas seleccionadas:\n%s'
            ) % '\n'.join('- %s' % label for label in route_labels))

        source_wh = rows[0].source_warehouse_id
        destination_wh = rows[0].destination_warehouse_id
        if source_wh == destination_wh:
            raise UserError(_('El almacén origen y destino deben ser diferentes.'))
        if not source_wh.int_type_id:
            raise UserError(_(
                'El almacén %s no tiene un tipo de operación interna configurado.'
            ) % source_wh.display_name)

        # Validate the total requested quantity per product against the current
        # free stock. This prevents two selected rows of the same product from
        # passing the check independently and over-reserving the source.
        from collections import defaultdict
        from ..services.internal_stock import InternalWarehouseStock

        qty_by_product = defaultdict(float)
        products = self.env['product.product']
        for row in rows:
            qty_by_product[row.product_id.id] += row.move_qty
            products |= row.product_id

        stock_now = InternalWarehouseStock(
            self.env, self.company_id
        ).quantities(products, source_wh)
        for product in products:
            requested = qty_by_product[product.id]
            free_now = stock_now[(product.id, source_wh.id)]['free']
            if free_now + 1e-6 < requested:
                raise UserError(_(
                    'El almacén %s ya no dispone de %.4f unidades libres de %s. '
                    'Disponible actualmente: %.4f. Recalcule la planificación.'
                ) % (
                    source_wh.display_name,
                    requested,
                    product.display_name,
                    free_now,
                ))

        picking = self.env['stock.picking'].create({
            'picking_type_id': source_wh.int_type_id.id,
            'location_id': source_wh.lot_stock_id.id,
            'location_dest_id': destination_wh.lot_stock_id.id,
            'origin': '%s - Transferencia APS' % self.name,
            'company_id': self.company_id.id,
            'advanced_plan_id': self.id,
        })

        Move = self.env['stock.move']
        for row in rows:
            move_vals = {
                'product_id': row.product_id.id,
                'product_uom_qty': row.move_qty,
                'product_uom': row.product_uom_id.id,
                'location_id': source_wh.lot_stock_id.id,
                'location_dest_id': destination_wh.lot_stock_id.id,
                'picking_id': picking.id,
                'company_id': self.company_id.id,
            }
            if row.planning_line_id:
                move_vals['planning_plan_line_id'] = row.planning_line_id.id
            if row.production_component_id and 'aps_planning_component_id' in Move._fields:
                move_vals['aps_planning_component_id'] = row.production_component_id.id
            Move.create(move_vals)

        picking.action_confirm()
        picking.action_assign()

        rows.write({
            'picking_id': picking.id,
            'state': 'generated',
            'selected_for_transfer': False,
        })
        self.write({'needs_recalculation': True})

        detail = '<br/>'.join(
            '• %s: %.4f %s' % (
                row.product_id.display_name,
                row.move_qty,
                row.product_uom_id.name or '',
            )
            for row in rows
        )
        self.message_post(body=_(
            'Transferencia interna APS creada con %s componentes desde <b>%s</b> hacia <b>%s</b>.'
            '<br/>%s'
            '<br/><br/><b>Recalcule la planificación</b> antes de generar nuevas compras u órdenes de fabricación.'
        ) % (
            len(rows),
            source_wh.display_name,
            destination_wh.display_name,
            detail,
        ))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Transferencia interna'),
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    # Compatibility with the old approval wizard: approval now means generate manufacturing selections.
    def action_open_approval(self):
        return self.action_create_manufacturing()

    def _approve_and_create_productions(self):
        self.action_create_manufacturing()
        return self.env['mrp.production'].search([('advanced_plan_id', 'in', self.ids)])

    def action_open_created_productions(self):
        """Abrir únicamente OF raíz creadas directamente por APS."""
        self.ensure_one()
        productions = self.line_ids.mapped(
            'created_production_id'
        ).exists().filtered(
            lambda mo:
                not mo.aps_parent_production_id
                and mo.planning_plan_line_id
        )
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Órdenes de fabricación del plan'),
            'res_model': 'mrp.production',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', productions.ids)],
            'target': 'current',
        }
        if len(productions) == 1:
            action.update({
                'res_id': productions.id,
                'view_mode': 'form',
                'views': [(False, 'form')],
            })
        return action

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
