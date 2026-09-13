import json

from odoo import api, fields, models, _


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    aps_planning_line_ids = fields.Many2many(
        'mrp.planning.plan.line',
        'mrp_planning_line_sale_rel',
        'sale_line_id',
        'planning_line_id',
        string='Líneas APS',
        readonly=True,
        copy=False,
    )
    aps_plan_ids = fields.Many2many(
        'mrp.planning.plan',
        string='Planificaciones APS',
        compute='_compute_aps_traceability',
        compute_sudo=True,
        readonly=True,
    )
    aps_production_ids = fields.Many2many(
        'mrp.production',
        string='Órdenes de fabricación APS',
        compute='_compute_aps_traceability',
        compute_sudo=True,
        readonly=True,
    )
    aps_purchase_order_ids = fields.Many2many(
        'purchase.order',
        string='Órdenes de compra APS',
        compute='_compute_aps_traceability',
        compute_sudo=True,
        readonly=True,
    )
    aps_picking_ids = fields.Many2many(
        'stock.picking',
        string='Transferencias APS',
        compute='_compute_aps_traceability',
        compute_sudo=True,
        readonly=True,
    )
    aps_plan_count = fields.Integer(
        string='Planificaciones APS',
        compute='_compute_aps_traceability',
        compute_sudo=True,
        search='_search_aps_plan_count',
    )
    aps_planning_status = fields.Selection(
        [
            ('pending', 'Pendiente de planificación'),
            ('planned', 'Ya planificada'),
        ],
        string='Estado planificación',
        compute='_compute_aps_traceability',
        compute_sudo=True,
        search='_search_aps_planning_status',
    )
    aps_mo_count = fields.Integer(
        string='OF APS',
        compute='_compute_aps_traceability',
        compute_sudo=True,
    )
    aps_po_count = fields.Integer(
        string='PO APS',
        compute='_compute_aps_traceability',
        compute_sudo=True,
    )


    # Legacy technical fields are retained for compatibility, but the SO
    # displays only the unified "Disponibilidad" indicator.
    aps_forecast_qty = fields.Float(
        string='Pronóstico técnico',
        compute='_compute_aps_sale_forecast',
        digits=(16, 4),
    )
    aps_open_mo_qty = fields.Float(
        string='Fabricación pendiente técnica',
        compute='_compute_aps_sale_forecast',
        digits=(16, 4),
    )
    aps_forecast_status = fields.Selection([
        ('available', 'Disponible'),
        ('covered', 'Cubierto'),
        ('manufacturing', 'Por fabricación'),
        ('purchase', 'Por compra'),
        ('transfer', 'Por traslado'),
        ('mixed', 'Abastecimiento mixto'),
        ('partial', 'Cobertura parcial'),
        ('uncovered', 'Sin cubrir'),
    ], string='Disponibilidad', compute='_compute_aps_sale_forecast')
    aps_stock_warehouse_tooltip = fields.Text(
        string='Detalle disponibilidad APS',
        compute='_compute_aps_sale_forecast',
    )
    planning_delivery_date_manual = fields.Boolean(
        string='Fecha de planificación modificada manualmente',
        default=False,
        copy=False,
    )
    planning_delivery_date = fields.Date(
        string='Fecha de entrega planificación',
        compute='_compute_planning_delivery_date',
        inverse='_inverse_planning_delivery_date',
        store=True,
        readonly=False,
        precompute=True,
        index=True,
        copy=True,
        help=(
            'Fecha utilizada por el planificador de fabricación. Por defecto toma la '
            'Fecha de entrega del pedido de venta y puede modificarse por cada línea.'
        ),
    )

    def _action_launch_stock_rule(self, previous_product_uom_qty=False):
        """Keep current Odoo routes but hold manufacture launched from SO.

        No extra product parameter is required. Existing MTO, Manufacture,
        Buy and warehouse routes remain unchanged. Only manufacturing rules
        reached while confirming sale lines are held for APS. Component MRP
        launched later from manufacturing does not carry this context.
        """
        commercial_lines = self.filtered(
            lambda line:
                not line.display_type
                and line.product_id
                and line.product_uom_qty > 0
        )
        other_lines = self - commercial_lines

        result = True
        if other_lines:
            result = super(
                SaleOrderLine, other_lines
            )._action_launch_stock_rule(
                previous_product_uom_qty=previous_product_uom_qty
            )

        if commercial_lines:
            result = super(
                SaleOrderLine,
                commercial_lines.with_context(
                    aps_hold_sale_mto_manufacturing=True
                ),
            )._action_launch_stock_rule(
                previous_product_uom_qty=previous_product_uom_qty
            )
        return result


    @api.model
    def _search_aps_planning_status(self, operator, value):
        if operator not in ('=', '!='):
            return [('id', '=', 0)]

        planned = value == 'planned'
        if operator == '!=':
            planned = not planned

        return [
            ('aps_plan_count', '>', 0)
            if planned
            else ('aps_plan_count', '=', 0)
        ]

    @api.model
    def _search_aps_plan_count(self, operator, value):
        """Buscar líneas de venta según si ya fueron tomadas por APS.

        ``aps_plan_count`` es calculado porque la trazabilidad puede provenir
        tanto de la relación M2M histórica como de ``sale_line_id`` en las
        líneas del plan. Para los filtros operativos de agenda sólo necesitamos
        distinguir 0 vs. uno-o-más planes, sin almacenar un contador duplicado.
        """
        try:
            numeric_value = float(value or 0)
        except (TypeError, ValueError):
            numeric_value = 0.0

        PlanLine = self.env['mrp.planning.plan.line'].sudo()
        direct_sale_ids = PlanLine.search([
            ('sale_line_id', '!=', False),
        ]).mapped('sale_line_id').ids

        planned_domain = [
            '|',
            ('aps_planning_line_ids', '!=', False),
            ('id', 'in', direct_sale_ids),
        ]

        # Los filtros de la agenda usan exactamente = 0 y > 0.
        if operator == '=' and numeric_value == 0:
            planned_ids = self.sudo().search(planned_domain).ids
            return [('id', 'not in', planned_ids)]

        if operator in ('>', '>=') and numeric_value <= 0:
            return planned_domain

        if operator == '!=' and numeric_value == 0:
            return planned_domain

        if operator in ('<', '<=') and numeric_value <= 0:
            # El contador nunca es negativo; < 0 no tiene resultados,
            # <= 0 equivale a no planificado.
            if operator == '<':
                return [('id', '=', 0)]
            planned_ids = self.sudo().search(planned_domain).ids
            return [('id', 'not in', planned_ids)]

        # Para búsquedas numéricas no binarias, calcular sobre candidatos.
        # Es menos frecuente pero hace al campo correctamente searchable.
        candidate_ids = self.sudo().search([]).ids
        matching_ids = []
        for line in self.sudo().browse(candidate_ids):
            line._compute_aps_traceability()
            count = line.aps_plan_count
            ok = {
                '=': count == numeric_value,
                '!=': count != numeric_value,
                '>': count > numeric_value,
                '>=': count >= numeric_value,
                '<': count < numeric_value,
                '<=': count <= numeric_value,
            }.get(operator, False)
            if ok:
                matching_ids.append(line.id)
        return [('id', 'in', matching_ids)]

    @api.depends(
        'aps_planning_line_ids',
        'aps_planning_line_ids.plan_id',
        'aps_planning_line_ids.created_production_id',
        'aps_planning_line_ids.created_purchase_line_id',
        'aps_planning_line_ids.created_picking_ids',
    )
    def _compute_aps_traceability(self):
        PlanLine = self.env['mrp.planning.plan.line'].sudo()
        for line in self:
            planning_lines = line.aps_planning_line_ids.sudo() | PlanLine.search([
                ('sale_line_id', '=', line.id),
            ])
            line.aps_plan_ids = planning_lines.mapped('plan_id')
            line.aps_production_ids = planning_lines.mapped(
                'created_production_id'
            )
            line.aps_purchase_order_ids = planning_lines.mapped(
                'created_purchase_line_id.order_id'
            )
            line.aps_picking_ids = planning_lines.mapped('created_picking_ids')
            line.aps_plan_count = len(line.aps_plan_ids)
            line.aps_planning_status = (
                'planned' if line.aps_plan_count else 'pending'
            )
            line.aps_mo_count = len(line.aps_production_ids)
            line.aps_po_count = len(line.aps_purchase_order_ids)

    def _aps_open_records(self, model, records, name):
        self.ensure_one()
        if not records:
            return False
        action = {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': model,
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', records.ids)],
            'target': 'current',
        }
        if len(records) == 1:
            action.update({
                'res_id': records.id,
                'view_mode': 'form',
                'views': [(False, 'form')],
            })
        return action

    def action_open_aps_plans(self):
        self.ensure_one()
        return self._aps_open_records(
            'mrp.planning.plan',
            self.aps_plan_ids,
            'Planificaciones APS',
        )

    def action_open_aps_productions(self):
        self.ensure_one()
        return self._aps_open_records(
            'mrp.production',
            self.aps_production_ids,
            'Órdenes de fabricación APS',
        )

    def action_open_aps_purchases(self):
        self.ensure_one()
        return self._aps_open_records(
            'purchase.order',
            self.aps_purchase_order_ids,
            'Órdenes de compra APS',
        )

    @api.depends(
        'order_id.commitment_date',
        'order_id.date_order',
        'planning_delivery_date_manual',
        'display_type',
    )
    def _compute_planning_delivery_date(self):
        for line in self:
            if line.display_type:
                line.planning_delivery_date = False
                continue
            if not line.planning_delivery_date_manual:
                source_date = (
                    line.order_id.commitment_date
                    or line.order_id.date_order
                    or fields.Date.context_today(line)
                )
                line.planning_delivery_date = fields.Date.to_date(source_date)

    def _inverse_planning_delivery_date(self):
        for line in self:
            if line.display_type:
                line.planning_delivery_date_manual = False
                continue
            default_value = (
                line.order_id.commitment_date
                or line.order_id.date_order
                or fields.Date.context_today(line)
            )
            default_date = fields.Date.to_date(default_value)
            # Clearing the field restores the order-level DATE default.
            if not line.planning_delivery_date:
                line.planning_delivery_date_manual = False
                line.planning_delivery_date = default_date
            else:
                line.planning_delivery_date_manual = bool(
                    line.planning_delivery_date != default_date
                )


    @api.depends(
        'product_id',
        'product_uom_qty',
        'qty_delivered',
        'product_uom_id',
        'order_id.warehouse_id',
        'order_id.company_id',
        'aps_planning_line_ids',
        'aps_planning_line_ids.plan_id',
        'aps_planning_line_ids.created_production_id',
        'aps_planning_line_ids.created_purchase_line_id',
        'aps_planning_line_ids.created_picking_ids',
    )
    def _compute_aps_sale_forecast(self):
        """Availability for THIS sale line, without stealing committed supply.

        Important rules:
        * physical free stock is common stock and may cover the line;
        * an MO/PO/transfer explicitly linked to another sale line is NOT
          available to this line;
        * supply explicitly linked to this line is available;
        * truly uncommitted supply may be shown as generic supply;
        * Odoo ``virtual_available`` is informational only here because it
          already contains incoming/outgoing moves. Adding open MO/PO again to
          it would double-count supply (e.g. 152 forecast + 152 MO = 304).
        """
        MrpProduction = self.env['mrp.production'].sudo()
        PurchaseLine = self.env['purchase.order.line'].sudo()
        PlanLine = self.env['mrp.planning.plan.line'].sudo()

        state_selection = MrpProduction._fields['state'].selection
        if callable(state_selection):
            state_selection = state_selection(self.env)
        state_labels = dict(state_selection)
        mo_states = [
            state for state in ('confirmed', 'progress', 'to_close')
            if state in state_labels
        ]

        def source_sale_lines_from_plan_line(plan_line):
            if not plan_line:
                return self.env['sale.order.line']
            return (
                plan_line.sale_line_ids
                or plan_line.sale_line_id
            ).filtered(lambda row: not row.display_type)

        def classify_supply_sale_lines(supply_sale_lines, current_line):
            """Return own / other / generic commitment classification."""
            supply_sale_lines = supply_sale_lines.exists()
            if current_line in supply_sale_lines:
                return 'own'
            if supply_sale_lines:
                return 'other'
            return 'generic'

        def mo_source_sale_lines(mo):
            """Resolve every sale line really committed to a manufacturing order.

            Prefer explicit APS traceability, but also recover native MTO links
            through finished move destinations. This is required for older MOs
            or sub-MOs created before the latest APS traceability fields were
            persisted.
            """
            sale_lines = self.env['sale.order.line']

            if mo.planning_plan_line_id:
                sale_lines |= source_sale_lines_from_plan_line(
                    mo.planning_plan_line_id
                )
            if mo.planning_sale_line_id:
                sale_lines |= mo.planning_sale_line_id

            # Native chain: finished move -> destination sale stock move ->
            # sale_line_id. This catches manufacturing committed to another SO
            # even when advanced_plan/planning_line fields are incomplete.
            for finished in mo.move_finished_ids.filtered(
                lambda move: move.state != 'cancel'
            ):
                downstream = finished.move_dest_ids.filtered(
                    lambda move: move.state != 'cancel'
                )
                sale_lines |= downstream.mapped('sale_line_id')

                # Follow one more level defensively because depending on route
                # configuration the sale-linked move may sit after an internal
                # transfer/stock move.
                next_level = downstream.mapped('move_dest_ids').filtered(
                    lambda move: move.state != 'cancel'
                )
                sale_lines |= next_level.mapped('sale_line_id')

            return sale_lines.filtered(lambda row: not row.display_type)

        def po_source_sale_lines(po_line):
            """Resolve sale commitments behind a purchase line when possible."""
            sale_lines = self.env['sale.order.line']

            po_plan_line = getattr(po_line, 'planning_plan_line_id', False)
            if not po_plan_line:
                po_plan_line = PlanLine.search([
                    ('created_purchase_line_id', '=', po_line.id),
                ], limit=1)
            if po_plan_line:
                sale_lines |= source_sale_lines_from_plan_line(po_plan_line)

            # Native purchase stock moves can also point to sale demand via
            # move_dest_ids in MTO/buy flows.
            for move in po_line.move_ids.filtered(
                lambda move: move.state != 'cancel'
            ):
                downstream = move.move_dest_ids.filtered(
                    lambda row: row.state != 'cancel'
                )
                sale_lines |= downstream.mapped('sale_line_id')
                sale_lines |= downstream.mapped(
                    'move_dest_ids'
                ).mapped('sale_line_id')

            return sale_lines.filtered(lambda row: not row.display_type)

        for line in self:
            line.aps_forecast_qty = 0.0
            line.aps_open_mo_qty = 0.0
            line.aps_forecast_status = 'uncovered'
            line.aps_stock_warehouse_tooltip = ''

            if (
                line.display_type
                or not line.product_id
                or not line.order_id.warehouse_id
            ):
                continue

            product = line.product_id
            warehouse = line.order_id.warehouse_id
            company = line.order_id.company_id or self.env.company

            stock_values = product.with_company(company).with_context(
                warehouse_id=warehouse.id,
                allowed_company_ids=[company.id],
                company_owned=True,
                prefetch_fields=False,
            ).read([
                'qty_available',
                'free_qty',
                'incoming_qty',
                'outgoing_qty',
                'virtual_available',
            ])[0]

            on_hand = float(stock_values.get('qty_available') or 0.0)
            free_qty = max(float(stock_values.get('free_qty') or 0.0), 0.0)
            incoming = float(stock_values.get('incoming_qty') or 0.0)
            outgoing = float(stock_values.get('outgoing_qty') or 0.0)
            forecast = float(stock_values.get('virtual_available') or 0.0)

            requested = (
                line.product_uom_id._compute_quantity(
                    line.product_uom_qty or 0.0,
                    product.uom_id,
                )
                if line.product_uom_id
                else (line.product_uom_qty or 0.0)
            )
            delivered = (
                line.product_uom_id._compute_quantity(
                    line.qty_delivered or 0.0,
                    product.uom_id,
                )
                if line.product_uom_id
                else (line.qty_delivered or 0.0)
            )
            pending = max(requested - delivered, 0.0)

            # APS lines linked exactly to the current sale line.
            planning_lines = line.aps_planning_line_ids | PlanLine.search([
                '|',
                ('sale_line_id', '=', line.id),
                ('sale_line_ids', 'in', line.id),
            ])
            planning_lines = planning_lines.filtered(
                lambda pl: pl.plan_id.state != 'cancelled'
            )
            aps_plans = planning_lines.mapped('plan_id')
            aps_mos = planning_lines.mapped('created_production_id').filtered(
                lambda mo: mo.state != 'cancel'
            )
            aps_pos = planning_lines.mapped(
                'created_purchase_line_id.order_id'
            ).filtered(lambda po: po.state != 'cancel')
            aps_pickings = planning_lines.mapped('created_picking_ids').filtered(
                lambda picking: picking.state != 'cancel'
            )

            # ---------------- Manufacturing ----------------
            mos = MrpProduction.search([
                ('company_id', '=', company.id),
                ('product_id', '=', product.id),
                ('state', 'in', mo_states or ['confirmed']),
                ('picking_type_id.warehouse_id', '=', warehouse.id),
            ])
            own_mo = generic_mo = other_mo = 0.0
            mo_rows = []
            other_mo_rows = []
            for mo in mos:
                qty = max(
                    (mo.product_qty or 0.0) - (mo.qty_produced or 0.0),
                    0.0,
                )
                if qty <= 1e-6:
                    continue
                qty = mo.product_uom_id._compute_quantity(qty, product.uom_id)

                supply_sale_lines = mo_source_sale_lines(mo)
                commitment = classify_supply_sale_lines(
                    supply_sale_lines, line
                )

                if commitment == 'own':
                    own_mo += qty
                elif commitment == 'other':
                    other_mo += qty
                else:
                    generic_mo += qty

                # In the popup list only own and genuinely generic documents
                # are actionable supply for this line. Other-sale documents
                # are exposed separately as committed elsewhere.
                row = {
                    'id': mo.id,
                    'name': mo.display_name,
                    'qty': qty,
                    'state': state_labels.get(mo.state, mo.state),
                    'commitment': commitment,
                }
                if commitment != 'other':
                    mo_rows.append(row)
                else:
                    other_mo_rows.append(row)

            # ---------------- Purchases ----------------
            po_lines = PurchaseLine.search([
                ('company_id', '=', company.id),
                ('product_id', '=', product.id),
                ('order_id.state', 'in', ('draft', 'sent', 'to approve', 'purchase')),
                ('order_id.picking_type_id.warehouse_id', '=', warehouse.id),
            ])
            own_po = generic_po = other_po = 0.0
            po_rows = []
            other_po_rows = []
            for po_line in po_lines:
                qty = max(
                    (po_line.product_qty or 0.0) - (po_line.qty_received or 0.0),
                    0.0,
                )
                if qty <= 1e-6:
                    continue
                qty = po_line.product_uom_id._compute_quantity(
                    qty, product.uom_id
                )

                supply_sale_lines = po_source_sale_lines(po_line)
                commitment = classify_supply_sale_lines(
                    supply_sale_lines, line
                )

                if commitment == 'own':
                    own_po += qty
                elif commitment == 'other':
                    other_po += qty
                else:
                    generic_po += qty

                row = {
                    'id': po_line.order_id.id,
                    'name': po_line.order_id.display_name,
                    'qty': qty,
                    'state': po_line.order_id.state,
                    'commitment': commitment,
                }
                if commitment != 'other':
                    po_rows.append(row)
                else:
                    other_po_rows.append(row)

            # ---------------- Transfers linked to this sale ----------------
            transfer_qty = 0.0
            transfer_rows = []
            for picking in aps_pickings:
                qty = 0.0
                for move in picking.move_ids.filtered(
                    lambda move:
                        move.product_id == product
                        and move.state != 'cancel'
                ):
                    # Done transfer is already physical stock at destination.
                    # Do not add it again on top of free stock.
                    if move.state == 'done':
                        continue
                    qty += move.product_uom._compute_quantity(
                        move.product_uom_qty or 0.0,
                        product.uom_id,
                    )
                if qty <= 1e-6:
                    continue
                transfer_qty += qty
                transfer_rows.append({
                    'id': picking.id,
                    'name': picking.display_name,
                    'qty': qty,
                    'state': picking.state,
                    'commitment': 'own',
                })

            # ---------------- Soft APS planning ----------------
            # A calculated plan without a generated document is useful
            # traceability but is not firm supply. Do not count it as coverage.
            planned_qty = sum(
                planning_lines.filtered(
                    lambda pl:
                        not pl.created_production_id
                        and not pl.created_purchase_line_id
                        and not pl.created_picking_ids
                ).mapped('planner_production_qty')
            )

            # Coverage uses mutually exclusive buckets. virtual_available is
            # NOT included because it already embeds many incoming/outgoing
            # movements and caused the previous double-counting.
            physical_cover = min(pending, free_qty)
            remaining = max(pending - physical_cover, 0.0)

            own_firm_supply = own_mo + own_po + transfer_qty
            own_cover = min(remaining, own_firm_supply)
            remaining -= own_cover

            # Generic supply is not committed to another sale and can cover
            # the remaining demand. Explicitly committed "other" supply is
            # never used here.
            generic_firm_supply = generic_mo + generic_po
            generic_cover = min(remaining, generic_firm_supply)
            remaining -= generic_cover

            coverage = physical_cover + own_cover + generic_cover
            shortage = max(pending - coverage, 0.0)

            available_mo = own_mo + generic_mo
            available_po = own_po + generic_po
            has_mo = available_mo > 1e-6
            has_po = available_po > 1e-6
            has_transfer = transfer_qty > 1e-6
            source_count = sum((has_mo, has_po, has_transfer))

            if pending <= 1e-6:
                status = 'covered'
            elif free_qty + 1e-6 >= pending:
                status = 'available'
            elif shortage <= 1e-6:
                if source_count > 1:
                    status = 'mixed'
                elif has_mo:
                    status = 'manufacturing'
                elif has_po:
                    status = 'purchase'
                elif has_transfer:
                    status = 'transfer'
                else:
                    status = 'covered'
            elif coverage > 1e-6:
                status = 'partial'
            else:
                status = 'uncovered'

            line.aps_forecast_qty = forecast
            # Keep this field semantically "manufacturing available to this
            # sale", not total MOs for the product.
            line.aps_open_mo_qty = available_mo
            line.aps_forecast_status = status
            line.aps_stock_warehouse_tooltip = json.dumps({
                'product': product.display_name,
                'warehouse': warehouse.display_name,
                'requested': requested,
                'delivered': delivered,
                'pending': pending,
                'on_hand': on_hand,
                'free_qty': free_qty,
                'incoming': incoming,
                'outgoing': outgoing,
                'forecast': forecast,
                'open_mo': available_mo,
                'open_po': available_po,
                'transfer_qty': transfer_qty,
                'planned_qty': planned_qty,
                'coverage': coverage,
                'shortage': shortage,
                'status': status,
                'physical_cover': physical_cover,
                'own_mo': own_mo,
                'generic_mo': generic_mo,
                'other_mo': other_mo,
                'own_po': own_po,
                'generic_po': generic_po,
                'other_po': other_po,
                'committed_elsewhere_qty': other_mo + other_po,
                'plans': [
                    {
                        'id': plan.id,
                        'name': plan.display_name,
                        'type': plan.plan_type,
                        'state': plan.state,
                    }
                    for plan in aps_plans
                ],
                'mos': mo_rows,
                'pos': po_rows,
                'other_mos': other_mo_rows,
                'other_pos': other_po_rows,
                'transfers': transfer_rows,
                'aps_mo_ids': aps_mos.ids,
                'aps_po_ids': aps_pos.ids,
            }, ensure_ascii=False)


    def action_open_aps_availability(self):
        self.ensure_one()
        if not self.id:
            return False

        # Recompute immediately so the modal always reflects current stock,
        # manufacturing, purchase, transfer and APS data.
        self._compute_aps_sale_forecast()
        try:
            payload = json.loads(self.aps_stock_warehouse_tooltip or '{}')
        except (TypeError, ValueError):
            payload = {}

        status_labels = {
            'available': 'Disponible',
            'covered': 'Cubierto',
            'manufacturing': 'Cubierto',
            'purchase': 'Cubierto',
            'transfer': 'Cubierto',
            'mixed': 'Cubierto',
            'partial': 'Cobertura parcial',
            'uncovered': 'Sin cubrir',
        }
        document_commands = []
        for row in payload.get('plans', []):
            document_commands.append((0, 0, {
                'document_type': 'plan',
                'name': row.get('name'),
                'quantity': 0.0,
                'state_label': row.get('state'),
                'res_model': 'mrp.planning.plan',
                'res_id': row.get('id'),
            }))
        for row in payload.get('mos', []):
            document_commands.append((0, 0, {
                'document_type': 'mo',
                'name': row.get('name'),
                'quantity': row.get('qty') or 0.0,
                'state_label': row.get('state'),
                'res_model': 'mrp.production',
                'res_id': row.get('id'),
            }))
        for row in payload.get('pos', []):
            document_commands.append((0, 0, {
                'document_type': 'po',
                'name': row.get('name'),
                'quantity': row.get('qty') or 0.0,
                'state_label': row.get('state'),
                'res_model': 'purchase.order',
                'res_id': row.get('id'),
            }))
        for row in payload.get('transfers', []):
            document_commands.append((0, 0, {
                'document_type': 'transfer',
                'name': row.get('name'),
                'quantity': row.get('qty') or 0.0,
                'state_label': row.get('state'),
                'res_model': 'stock.picking',
                'res_id': row.get('id'),
            }))
        for row in payload.get('other_mos', []):
            document_commands.append((0, 0, {
                'document_type': 'mo_other',
                'name': row.get('name'),
                'quantity': row.get('qty') or 0.0,
                'state_label': _('Comprometido a otra venta'),
                'res_model': 'mrp.production',
                'res_id': row.get('id'),
            }))
        for row in payload.get('other_pos', []):
            document_commands.append((0, 0, {
                'document_type': 'po_other',
                'name': row.get('name'),
                'quantity': row.get('qty') or 0.0,
                'state_label': _('Comprometido a otra venta'),
                'res_model': 'purchase.order',
                'res_id': row.get('id'),
            }))

        wizard = self.env['mrp.planning.sale.availability.wizard'].create({
            'sale_line_id': self.id,
            'product_id': self.product_id.id,
            'warehouse_id': self.order_id.warehouse_id.id,
            'status': status_labels.get(payload.get('status'), 'Sin cubrir'),
            'status_key': payload.get('status') or 'uncovered',
            'requested_qty': payload.get('requested') or 0.0,
            'delivered_qty': payload.get('delivered') or 0.0,
            'pending_qty': payload.get('pending') or 0.0,
            'coverage_qty': payload.get('coverage') or 0.0,
            'shortage_qty': payload.get('shortage') or 0.0,
            'on_hand_qty': payload.get('on_hand') or 0.0,
            'free_qty': payload.get('free_qty') or 0.0,
            'incoming_qty': payload.get('incoming') or 0.0,
            'outgoing_qty': payload.get('outgoing') or 0.0,
            'forecast_qty': payload.get('forecast') or 0.0,
            'manufacturing_qty': payload.get('open_mo') or 0.0,
            'purchase_qty': payload.get('open_po') or 0.0,
            'transfer_qty': payload.get('transfer_qty') or 0.0,
            'planned_qty': payload.get('planned_qty') or 0.0,
            'committed_elsewhere_qty': (
                payload.get('committed_elsewhere_qty') or 0.0
            ),
            'document_line_ids': document_commands,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Disponibilidad y abastecimiento'),
            'res_model': 'mrp.planning.sale.availability.wizard',
            'res_id': wizard.id,
            'views': [(self.env.ref(
                'mrp_advanced_planner.view_mrp_planning_sale_availability_wizard_form'
            ).id, 'form')],
            'view_mode': 'form',
            'target': 'new',
        }

    def action_reset_planning_delivery_date(self):
        for line in self.filtered(lambda row: not row.display_type):
            line.planning_delivery_date_manual = False
            source_date = (
                line.order_id.commitment_date
                or line.order_id.date_order
                or fields.Date.context_today(line)
            )
            line.planning_delivery_date = fields.Date.to_date(source_date)
        return True


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    aps_plan_ids = fields.Many2many(
        'mrp.planning.plan',
        string='Planificaciones APS',
        compute='_compute_aps_traceability',
        readonly=True,
    )
    aps_production_ids = fields.Many2many(
        'mrp.production',
        string='Órdenes de fabricación APS',
        compute='_compute_aps_traceability',
        readonly=True,
    )
    aps_purchase_order_ids = fields.Many2many(
        'purchase.order',
        string='Órdenes de compra APS',
        compute='_compute_aps_traceability',
        readonly=True,
    )
    aps_picking_ids = fields.Many2many(
        'stock.picking',
        string='Transferencias APS',
        compute='_compute_aps_traceability',
        readonly=True,
    )
    aps_plan_count = fields.Integer(compute='_compute_aps_traceability')
    aps_mo_count = fields.Integer(compute='_compute_aps_traceability')
    aps_po_count = fields.Integer(compute='_compute_aps_traceability')
    aps_picking_count = fields.Integer(compute='_compute_aps_traceability')

    @api.depends(
        'order_line.aps_planning_line_ids',
        'order_line.aps_planning_line_ids.plan_id',
        'order_line.aps_planning_line_ids.created_production_id',
        'order_line.aps_planning_line_ids.created_purchase_line_id',
        'order_line.aps_planning_line_ids.created_picking_ids',
    )
    def _compute_aps_traceability(self):
        PlanLine = self.env['mrp.planning.plan.line']
        for order in self:
            sale_lines = order.order_line.filtered(lambda line: not line.display_type)
            lines = sale_lines.mapped('aps_planning_line_ids')
            if sale_lines:
                lines |= PlanLine.search([
                    ('sale_line_id', 'in', sale_lines.ids),
                ])
            order.aps_plan_ids = lines.mapped('plan_id')
            order.aps_production_ids = lines.mapped('created_production_id')
            order.aps_purchase_order_ids = lines.mapped(
                'created_purchase_line_id.order_id'
            )
            order.aps_picking_ids = lines.mapped('created_picking_ids')
            order.aps_plan_count = len(order.aps_plan_ids)
            order.aps_mo_count = len(order.aps_production_ids)
            order.aps_po_count = len(order.aps_purchase_order_ids)
            order.aps_picking_count = len(order.aps_picking_ids)

    def _aps_open_records(self, model, records, name):
        self.ensure_one()
        if not records:
            return False
        action = {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': model,
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', records.ids)],
            'target': 'current',
        }
        if len(records) == 1:
            action.update({
                'res_id': records.id,
                'view_mode': 'form',
                'views': [(False, 'form')],
            })
        return action

    def action_open_aps_plans(self):
        self.ensure_one()
        return self._aps_open_records(
            'mrp.planning.plan', self.aps_plan_ids, 'Planificaciones APS'
        )

    def action_open_aps_productions(self):
        self.ensure_one()
        return self._aps_open_records(
            'mrp.production', self.aps_production_ids, 'Órdenes de fabricación APS'
        )

    def action_open_aps_purchases(self):
        self.ensure_one()
        return self._aps_open_records(
            'purchase.order', self.aps_purchase_order_ids, 'Órdenes de compra APS'
        )

    def action_open_aps_pickings(self):
        self.ensure_one()
        return self._aps_open_records(
            'stock.picking', self.aps_picking_ids, 'Transferencias APS'
        )
