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
    planning_delivery_date = fields.Datetime(
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
                line.planning_delivery_date = (
                    line.order_id.commitment_date
                    or line.order_id.date_order
                    or fields.Datetime.now()
                )

    def _inverse_planning_delivery_date(self):
        for line in self:
            if line.display_type:
                line.planning_delivery_date_manual = False
                continue
            default_date = line.order_id.commitment_date or line.order_id.date_order
            # Clearing the field restores the order-level default.
            if not line.planning_delivery_date:
                line.planning_delivery_date_manual = False
                line.planning_delivery_date = default_date or fields.Datetime.now()
            else:
                line.planning_delivery_date_manual = bool(
                    not default_date or line.planning_delivery_date != default_date
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
        MrpProduction = self.env['mrp.production'].sudo()
        PurchaseLine = self.env['purchase.order.line'].sudo()
        PlanLine = self.env['mrp.planning.plan.line'].sudo()

        state_selection = MrpProduction._fields['state'].selection
        if callable(state_selection):
            state_selection = state_selection(self.env)
        mo_states = [
            state for state in ('confirmed', 'progress', 'to_close')
            if state in dict(state_selection)
        ]

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
            free_qty = float(stock_values.get('free_qty') or 0.0)
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

            # Open manufacturing for this product in the SO warehouse.
            mos = MrpProduction.search([
                ('company_id', '=', company.id),
                ('product_id', '=', product.id),
                ('state', 'in', mo_states or ['confirmed']),
                ('picking_type_id.warehouse_id', '=', warehouse.id),
            ])
            open_mo = 0.0
            mo_rows = []
            for mo in mos:
                qty = max(
                    (mo.product_qty or 0.0) - (mo.qty_produced or 0.0),
                    0.0,
                )
                if qty <= 1e-6:
                    continue
                qty = mo.product_uom_id._compute_quantity(qty, product.uom_id)
                open_mo += qty
                mo_rows.append({
                    'id': mo.id,
                    'name': mo.display_name,
                    'qty': qty,
                    'state': dict(state_selection).get(mo.state, mo.state),
                })

            # Open purchase supply for this product/warehouse.
            po_lines = PurchaseLine.search([
                ('company_id', '=', company.id),
                ('product_id', '=', product.id),
                ('order_id.state', 'in', ('draft', 'sent', 'to approve', 'purchase')),
                ('order_id.picking_type_id.warehouse_id', '=', warehouse.id),
            ])
            open_po = 0.0
            po_rows = []
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
                open_po += qty
                po_rows.append({
                    'id': po_line.order_id.id,
                    'name': po_line.order_id.display_name,
                    'qty': qty,
                    'state': po_line.order_id.state,
                })

            # APS documents specifically linked to this SO line.
            planning_lines = line.aps_planning_line_ids | PlanLine.search([
                ('sale_line_id', '=', line.id),
            ])
            aps_plans = planning_lines.mapped('plan_id')
            aps_mos = planning_lines.mapped('created_production_id')
            aps_pos = planning_lines.mapped('created_purchase_line_id.order_id')
            aps_pickings = planning_lines.mapped('created_picking_ids')

            planned_qty = sum(
                planning_lines.mapped('planner_production_qty')
            )
            transfer_qty = 0.0
            transfer_rows = []
            for picking in aps_pickings:
                qty = 0.0
                for move in picking.move_ids.filtered(
                    lambda move: move.product_id == product
                    and move.state != 'cancel'
                ):
                    qty += move.product_uom._compute_quantity(
                        move.product_uom_qty or 0.0, product.uom_id
                    )
                transfer_qty += qty
                transfer_rows.append({
                    'id': picking.id,
                    'name': picking.display_name,
                    'qty': qty,
                    'state': picking.state,
                })

            # A line-specific operational indicator. The forecast is Odoo's net
            # forecast after demand; open supply sources explain how shortages
            # are being covered.
            net_forecast_cover = max(forecast, 0.0)
            supply_cover = open_mo + open_po + transfer_qty
            coverage = net_forecast_cover + supply_cover
            shortage = max(pending - coverage, 0.0)

            has_mo = open_mo > 1e-6
            has_po = open_po > 1e-6
            has_transfer = transfer_qty > 1e-6
            source_count = sum((has_mo, has_po, has_transfer))

            if pending <= 1e-6:
                status = 'covered'
            elif forecast + 1e-6 >= pending:
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
            line.aps_open_mo_qty = open_mo
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
                'open_mo': open_mo,
                'open_po': open_po,
                'transfer_qty': transfer_qty,
                'planned_qty': planned_qty,
                'coverage': coverage,
                'shortage': shortage,
                'status': status,
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

        wizard = self.env['mrp.planning.sale.availability.wizard'].create({
            'sale_line_id': self.id,
            'product_id': self.product_id.id,
            'warehouse_id': self.order_id.warehouse_id.id,
            'status': status_labels.get(payload.get('status'), 'Sin cubrir'),
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
            line.planning_delivery_date = (
                line.order_id.commitment_date
                or line.order_id.date_order
                or fields.Datetime.now()
            )
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
