from collections import defaultdict

from odoo import fields

from .odoo19_compat import find_bom


class SimplePlanningEngine:
    """Plan using Odoo forecast quantities, not only quantities on hand.

    Odoo's ``virtual_available`` already represents:
        on hand + incoming - outgoing

    Therefore sale demand, confirmed purchases and confirmed internal transfers
    must NOT be subtracted/added a second time. Confirmed/in-progress MOs are
    inspected explicitly and only the portion not yet represented by their
    finished stock move is added to the APS forecast.

    RFQs (draft/sent/to approve) are not yet stock moves, so they are added once
    as expected supply. Quantities committed by another calculated planner that
    have not yet generated a document are also added once, preventing duplicate
    planning between concurrent plans.
    """

    RFQ_STATES = ('draft', 'sent', 'to approve')

    def __init__(self, plan):
        self.plan = plan
        self.env = plan.env

    def _sale_demand(self, warehouses):
        SaleLine = self.env['sale.order.line']
        domain = [
            ('order_id.state', '=', 'sale'),
            ('order_id.company_id', '=', self.plan.company_id.id),
            ('order_id.warehouse_id', 'in', warehouses.ids),
            ('product_id', '!=', False),
            ('display_type', '=', False),
            ('product_uom_qty', '>', 0),
            ('planning_delivery_date', '!=', False),
            ('planning_delivery_date', '<=', self.plan.date_end),
        ]
        sale_lines = SaleLine.search(
            domain,
            order='planning_delivery_date asc, order_id asc, sequence asc, id asc',
        )
        # Defensive cutoff: the plan must never receive a sales line after
        # its horizon, even if another customization alters the search.
        sale_lines = sale_lines.filtered(
            lambda line:
                line.planning_delivery_date
                and line.planning_delivery_date <= self.plan.date_end
        )

        grouped = defaultdict(lambda: {
            'sale_lines': self.env['sale.order.line'],
            'sales_qty': 0.0,
            'mrp_component_qty': 0.0,
            'component_by_warehouse': defaultdict(float),
            'bom_origins': [],
            'date_required': False,
            'by_warehouse': defaultdict(float),
        })
        for line in sale_lines:
            pending_sale_uom = max(line.product_uom_qty - line.qty_delivered, 0.0)
            if pending_sale_uom <= 0:
                continue
            pending = line.product_uom_id._compute_quantity(
                pending_sale_uom, line.product_id.uom_id
            )
            if pending <= 0:
                continue
            row = grouped[line.product_id.id]
            row['sale_lines'] |= line
            row['sales_qty'] += pending
            row['by_warehouse'][line.order_id.warehouse_id.id] += pending
            if not row['date_required'] or line.planning_delivery_date < row['date_required']:
                row['date_required'] = line.planning_delivery_date
        late_lines = self.env['sale.order.line']
        for row in grouped.values():
            late_lines |= row['sale_lines'].filtered(
                lambda line:
                    line.planning_delivery_date
                    and line.planning_delivery_date > self.plan.date_end
            )
        if late_lines:
            from odoo.exceptions import UserError
            raise UserError(
                'El plan contiene líneas de venta posteriores a la fecha límite: %s'
                % ', '.join(late_lines.mapped('order_id.name'))
            )
        return grouped

    def _odoo_forecast_by_warehouse(self, products, warehouses):
        """Read Odoo's own forecast at the plan horizon per warehouse."""
        result = {}
        for warehouse in warehouses:
            rows = products.with_context(
                warehouse_id=warehouse.id,
                to_date=self.plan.date_end,
                allowed_company_ids=[self.plan.company_id.id],
                company_owned=True,
                prefetch_fields=False,
            ).read([
                'qty_available',
                'free_qty',
                'incoming_qty',
                'outgoing_qty',
                'virtual_available',
            ])
            for row in rows:
                result[(row['id'], warehouse.id)] = {
                    'on_hand': row.get('qty_available') or 0.0,
                    'free': row.get('free_qty') or 0.0,
                    'incoming': row.get('incoming_qty') or 0.0,
                    'outgoing': row.get('outgoing_qty') or 0.0,
                    'virtual': row.get('virtual_available') or 0.0,
                }
        return result

    def _internal_free_stock_by_warehouse(self, products, warehouses):
        """Physically free stock only in internal locations of selected warehouses."""
        from .internal_stock import InternalWarehouseStock
        return InternalWarehouseStock(
            self.env, self.plan.company_id
        ).quantities(products, warehouses)

    def _rfq_supply_by_warehouse(self, products, warehouses):
        """Supply still in RFQ / approval and therefore absent from stock forecast."""
        result = defaultdict(float)
        PurchaseLine = self.env['purchase.order.line']
        lines = PurchaseLine.search([
            ('company_id', '=', self.plan.company_id.id),
            ('product_id', 'in', products.ids),
            ('order_id.state', 'in', self.RFQ_STATES),
            ('order_id.picking_type_id.warehouse_id', 'in', warehouses.ids),
            '|',
            ('date_planned', '=', False),
            ('date_planned', '<=', self.plan.date_end),
        ])
        for line in lines:
            warehouse = line.order_id.picking_type_id.warehouse_id
            if not warehouse:
                continue
            pending = max((line.product_qty or 0.0) - (line.qty_received or 0.0), 0.0)
            if pending <= 0:
                continue
            qty = line.product_uom_id._compute_quantity(
                pending, line.product_id.uom_id
            )
            result[(line.product_id.id, warehouse.id)] += qty
        return result

    def _confirmed_po_supply_by_warehouse(self, products, warehouses):
        """Confirmed PO pending receipt within the plan lead-time horizon."""
        result = defaultdict(float)
        lines = self.env['purchase.order.line'].search([
            ('company_id', '=', self.plan.company_id.id),
            ('product_id', 'in', products.ids),
            ('order_id.state', '=', 'purchase'),
            ('order_id.picking_type_id.warehouse_id', 'in', warehouses.ids),
            ('date_planned', '<=', self.plan.date_end),
        ])
        for line in lines:
            warehouse = line.order_id.picking_type_id.warehouse_id
            pending = max((line.product_qty or 0.0) - (line.qty_received or 0.0), 0.0)
            if warehouse and pending > 1e-6:
                result[(line.product_id.id, warehouse.id)] += line.product_uom_id._compute_quantity(
                    pending, line.product_id.uom_id
                )
        return result

    def _other_plan_supply_by_warehouse(self, products, warehouses):
        """Reserve unexecuted supply already committed by another planner."""
        result = defaultdict(float)
        PlanLine = self.env['mrp.planning.plan.line']
        lines = PlanLine.search([
            ('plan_id', '!=', self.plan.id),
            ('plan_id.company_id', '=', self.plan.company_id.id),
            ('plan_id.state', '=', 'calculated'),
            ('product_id', 'in', products.ids),
            ('target_warehouse_id', 'in', warehouses.ids),
            ('planner_production_qty', '>', 0),
            ('date_required', '<=', self.plan.date_end),
        ])
        for line in lines:
            # Once the document exists, stock forecast (MO) or RFQ forecast
            # accounts for it. Count only planner commitments without a document.
            if line.action_manufacture and not line.created_production_id:
                result[(line.product_id.id, line.target_warehouse_id.id)] += line.planner_production_qty
            elif line.action_purchase and not line.created_purchase_line_id:
                result[(line.product_id.id, line.target_warehouse_id.id)] += line.planner_production_qty
        return result

    def _open_mo_information(self, products, warehouses):
        """Return open MO supply and the part not yet represented in stock forecast.

        Confirmed / in-progress manufacturing orders are real future supply and
        must reduce the quantity proposed by APS. Odoo normally represents them
        through the finished-product stock move and therefore in
        ``incoming_qty`` / ``virtual_available``.  We keep two quantities:

        * ``open_qty``: full remaining quantity, used for the visible "OF abiertas".
        * ``extra_qty``: only the portion whose finished stock move is still
          draft/missing and therefore is not yet represented in Odoo forecast.

        This makes confirmed MOs explicit without double-counting them.
        """
        open_qty = defaultdict(float)
        extra_qty = defaultdict(float)
        Production = self.env['mrp.production']
        state_selection = Production._fields['state'].selection
        if callable(state_selection):
            state_selection = state_selection(self.env)
        state_values = dict(state_selection)
        valid_states = [
            state for state in ('confirmed', 'progress', 'to_close')
            if state in state_values
        ]
        if not valid_states:
            return open_qty, extra_qty

        # Prefer the warehouse directly linked to the manufacturing operation
        # type. This is more robust than relying only on manu_type_id equality.
        warehouse_ids = set(warehouses.ids)
        mos = Production.search([
            ('company_id', '=', self.plan.company_id.id),
            ('product_id', 'in', products.ids),
            ('state', 'in', valid_states),
        ])
        for mo in mos:
            warehouse = mo.picking_type_id.warehouse_id
            if not warehouse or warehouse.id not in warehouse_ids:
                continue

            due = (
                getattr(mo, 'date_finished', False)
                or getattr(mo, 'date_deadline', False)
                or getattr(mo, 'date_start', False)
            )
            if due and due > self.plan.date_end:
                continue

            produced = getattr(mo, 'qty_produced', 0.0) or 0.0
            remaining = max((mo.product_qty or 0.0) - produced, 0.0)
            if mo.product_uom_id and mo.product_uom_id != mo.product_id.uom_id:
                remaining = mo.product_uom_id._compute_quantity(
                    remaining, mo.product_id.uom_id
                )
            if remaining <= 1e-6:
                continue

            key = (mo.product_id.id, warehouse.id)
            open_qty[key] += remaining

            # Determine how much of this MO is already represented by a
            # non-draft finished stock move. That part is already inside
            # virtual_available and must not be added again.
            represented = 0.0
            for move in mo.move_finished_ids.filtered(
                lambda m: m.product_id == mo.product_id
                and m.state not in ('draft', 'done', 'cancel')
            ):
                move_due = getattr(move, 'date', False)
                if move_due and move_due > self.plan.date_end:
                    continue
                move_qty = move.product_uom_qty or 0.0
                if move.product_uom and move.product_uom != mo.product_id.uom_id:
                    move_qty = move.product_uom._compute_quantity(
                        move_qty, mo.product_id.uom_id
                    )
                represented += move_qty

            extra_qty[key] += max(remaining - min(represented, remaining), 0.0)

        return open_qty, extra_qty

    def run(self):
        self.plan._ensure_warehouse_ids()
        self.plan.external_move_ids.filtered(lambda move: move.state == 'pending').unlink()
        self.plan.line_ids.unlink()

        warehouses = self.plan.warehouse_ids
        grouped = self._sale_demand(warehouses)

        if self.plan.plan_type == 'purchase':
            # Purchase component demand comes DIRECTLY from pending SO lines.
            # It never reads manufacturing planning records.
            from .recursive_purchase_demand import RecursivePurchaseDemandEngine

            purchase_available_cache = {}
            confirmed_po_cache = defaultdict(float)

            def prime_products(products_to_prime):
                missing = products_to_prime.filtered(
                    lambda product: any(
                        (product.id, warehouse.id) not in purchase_available_cache
                        for warehouse in warehouses
                    )
                )
                if not missing:
                    return
                free_rows = self._internal_free_stock_by_warehouse(
                    missing, warehouses
                )
                po_rows = self._confirmed_po_supply_by_warehouse(
                    missing, warehouses
                )
                rfq_rows = self._rfq_supply_by_warehouse(
                    missing, warehouses
                )
                other_rows = self._other_plan_supply_by_warehouse(
                    missing, warehouses
                )
                confirmed_po_cache.update(po_rows)
                for product in missing:
                    for warehouse in warehouses:
                        key = (product.id, warehouse.id)
                        purchase_available_cache[key] = (
                            free_rows[key]['free']
                            + confirmed_po_cache[key]
                            + rfq_rows[key]
                            + other_rows[key]
                        )

            def available_supply(product, warehouse):
                key = (product.id, warehouse.id)
                if key not in purchase_available_cache:
                    prime_products(product)
                return purchase_available_cache.get(key, 0.0)

            component_demand = RecursivePurchaseDemandEngine(
                self.plan,
                grouped,
                {
                    'available_supply': available_supply,
                    'prime_products': prime_products,
                },
            ).run()
            for product_id, component in component_demand.items():
                row = grouped[product_id]
                row['mrp_component_qty'] += component['gross_qty']
                for warehouse_id, qty in component['by_warehouse'].items():
                    row['component_by_warehouse'][warehouse_id] += qty
                row['bom_origins'].extend(component['origins'])
                component_date = component.get('date_required') or self.plan.date_end
                if not row['date_required'] or component_date < row['date_required']:
                    row['date_required'] = component_date

        if not grouped:
            return 0

        products = self.env['product.product'].browse(list(grouped))
        odoo_forecast = self._odoo_forecast_by_warehouse(products, warehouses)
        rfq_supply = self._rfq_supply_by_warehouse(products, warehouses)
        confirmed_po_supply = self._confirmed_po_supply_by_warehouse(products, warehouses)
        other_plan_supply = self._other_plan_supply_by_warehouse(products, warehouses)
        open_mos, extra_mo_supply = self._open_mo_information(products, warehouses)

        all_company_warehouses = self.env['stock.warehouse'].search([('company_id', '=', self.plan.company_id.id)])
        external_warehouses = all_company_warehouses - warehouses
        external_forecast = self._odoo_forecast_by_warehouse(products, external_warehouses) if external_warehouses else {}
        external_rfq = self._rfq_supply_by_warehouse(products, external_warehouses) if external_warehouses else defaultdict(float)
        external_other_plan = self._other_plan_supply_by_warehouse(products, external_warehouses) if external_warehouses else defaultdict(float)
        external_open_mos, external_extra_mo = self._open_mo_information(products, external_warehouses) if external_warehouses else (defaultdict(float), defaultdict(float))

        Line = self.env['mrp.planning.plan.line']
        Detail = self.env['mrp.planning.plan.line.warehouse']
        ExternalMove = self.env['mrp.planning.external.warehouse.move']
        created = Line

        for product in products.sorted(key=lambda p: (p.default_code or '', p.display_name, p.id)):
            source = grouped[product.id]
            details = []
            total_forecast = 0.0
            total_incoming = 0.0
            total_outgoing = 0.0
            total_rfq = 0.0
            total_other_plan = 0.0
            total_open_mo = 0.0
            total_shortage = 0.0
            total_excess = 0.0
            target_wh = warehouses[:1]
            largest_shortage = -1.0

            for warehouse in warehouses:
                key = (product.id, warehouse.id)
                forecast = odoo_forecast.get(key, {
                    'on_hand': 0.0, 'free': 0.0, 'incoming': 0.0,
                    'outgoing': 0.0, 'virtual': 0.0,
                })
                draft_purchase = rfq_supply[key]
                planned_elsewhere = other_plan_supply[key]

                # This is the single quantity used for planning.
                # Odoo's virtual_available normally already contains the
                # finished stock moves of confirmed/in-progress MOs. Add only
                # the part of open manufacturing that is not yet represented
                # in that stock forecast.
                manufacturing_not_in_forecast = extra_mo_supply[key]
                component_demand = source['component_by_warehouse'].get(
                    warehouse.id, 0.0
                )
                if self.plan.plan_type == 'purchase':
                    # Purchase precision rule: use only physically free stock
                    # (On Hand - Reserved) plus confirmed PO still in transit
                    # and due within the plan horizon. Demand is explicit.
                    local_demand = (
                        source['by_warehouse'].get(warehouse.id, 0.0)
                        + component_demand
                    )
                    confirmed_in_transit = confirmed_po_supply[key]
                    explicit_free = internal_stock_by_wh[key]['free']
                    adjusted_forecast = (
                        explicit_free
                        + confirmed_in_transit
                        + draft_purchase
                        + planned_elsewhere
                        - local_demand
                    )
                else:
                    adjusted_forecast = (
                        forecast['virtual']
                        + draft_purchase
                        + planned_elsewhere
                        + manufacturing_not_in_forecast
                    )
                shortage = max(-adjusted_forecast, 0.0)
                excess = max(adjusted_forecast, 0.0)

                total_forecast += adjusted_forecast
                total_incoming += forecast['incoming']
                total_outgoing += forecast['outgoing']
                total_rfq += draft_purchase
                total_other_plan += planned_elsewhere
                total_open_mo += open_mos[key]
                total_shortage += shortage
                total_excess += excess

                if shortage > largest_shortage:
                    largest_shortage = shortage
                    target_wh = warehouse

                details.append({
                    'warehouse': warehouse,
                    'demand': source['by_warehouse'].get(warehouse.id, 0.0) + source['component_by_warehouse'].get(warehouse.id, 0.0),
                    'on_hand': forecast['on_hand'],
                    'free': forecast['free'],
                    'incoming': forecast['incoming'],
                    'outgoing': forecast['outgoing'],
                    'rfq': draft_purchase,
                    'other_plan': planned_elsewhere,
                    'forecast': adjusted_forecast,
                    'open_mo': open_mos[key],
                    'extra_mo_supply': manufacturing_not_in_forecast,
                    'shortage': shortage,
                    'excess': excess,
                })

            # Global supply need after allowing excess in one selected warehouse
            # to cover shortage in another one.
            net_requirement = max(total_shortage - total_excess, 0.0)
            move_suggested = min(total_shortage, total_excess)
            bom = find_bom(self.env, product, company_id=self.plan.company_id.id)

            # Separate workflows:
            # - Manufacturing planner: only products with a BoM.
            # - Purchase planner: only products without a BoM; it may suggest an
            #   internal move before buying when another selected warehouse has excess.
            if self.plan.plan_type == 'manufacturing' and not bom:
                continue
            if self.plan.plan_type == 'purchase' and bom:
                continue

            manufacture = purchase = move = False
            planner_qty = 0.0
            if self.plan.plan_type == 'manufacturing':
                if net_requirement > 1e-6:
                    manufacture = True
                    planner_qty = net_requirement
            else:
                if net_requirement > 1e-6:
                    purchase = True
                    planner_qty = net_requirement
                elif move_suggested > 1e-6:
                    move = True
                    planner_qty = move_suggested

            # A planner line must represent a real action to execute.
            # Products fully covered by forecast are intentionally omitted.
            if not (manufacture or purchase or move) or planner_qty <= 1e-6:
                continue

            purchase_vendor = False
            if purchase:
                # Default vendor for APS purchase planning:
                # take the first supplier configured on the product.
                # If there are no configured suppliers, leave it empty so the
                # planner can choose any Odoo supplier manually.
                sellers = product.with_company(self.plan.company_id).seller_ids.filtered(
                    lambda seller: not seller.company_id or seller.company_id == self.plan.company_id
                ).sorted(key=lambda seller: (seller.sequence, seller.id))
                purchase_vendor = sellers[:1].partner_id if sellers else False

            sale_lines = source['sale_lines']
            direct_demand = source['sales_qty']
            component_demand_total = source['mrp_component_qty']
            total_demand = direct_demand + component_demand_total
            if direct_demand > 1e-6 and component_demand_total > 1e-6:
                source_type = 'mixed'
            elif component_demand_total > 1e-6:
                source_type = 'mrp'
            else:
                source_type = 'sale'

            source_parts = []
            if sale_lines:
                source_parts.append('%s pedidos / %s líneas de venta' % (
                    len(sale_lines.mapped('order_id')), len(sale_lines)
                ))
            if source['bom_origins']:
                source_parts.append('%s rutas de LdM' % len(source['bom_origins']))

            line = Line.create({
                'plan_id': self.plan.id,
                'sale_line_id': sale_lines[:1].id,
                'sale_line_ids': [(6, 0, sale_lines.ids)],
                'product_id': product.id,
                'target_warehouse_id': target_wh.id if target_wh else False,
                'sales_qty': total_demand,
                'demand_qty': total_demand,
                'direct_sale_demand_qty': direct_demand,
                'mrp_component_demand_qty': component_demand_total,
                'bom_origin_detail': '\n'.join(source['bom_origins']),
                # "stock_qty" intentionally stores the adjusted forecast used
                # in every decision; it is no longer an on-hand quantity.
                'stock_qty': total_forecast,
                'incoming_qty': total_incoming,
                'outgoing_qty': total_outgoing,
                'draft_purchase_qty': total_rfq,
                'other_plan_supply_qty': total_other_plan,
                'production_qty': total_open_mo,
                'net_requirement_qty': net_requirement,
                'move_suggested_qty': move_suggested,
                'planner_production_qty': planner_qty,
                'planned_production_qty': planner_qty if manufacture else 0.0,
                'planned_purchase_qty': planner_qty if purchase else 0.0,
                'action_manufacture': manufacture,
                'action_purchase': purchase,
                'action_move': move,
                'purchase_vendor_id': purchase_vendor.id if purchase_vendor else False,
                'date_required': source['date_required'] or self.plan.date_end,
                'source_type': source_type,
                'source_reference': ' + '.join(source_parts) or 'Demanda APS',
                'bom_id': bom.id if bom else False,
                'state': 'planned',
            })
            created |= line

            Detail.create([{
                'planning_line_id': line.id,
                'warehouse_id': row['warehouse'].id,
                'demand_qty': row['demand'],
                'on_hand_qty': row['on_hand'],
                'free_qty': row['free'],
                'incoming_qty': row['incoming'],
                'outgoing_qty': row['outgoing'],
                'draft_purchase_qty': row['rfq'],
                'other_plan_supply_qty': row['other_plan'],
                'stock_qty': row['forecast'],
                'open_mo_qty': row['open_mo'],
                'unforecasted_mo_qty': row.get('extra_mo_supply', 0.0),
                'local_shortage_qty': row['shortage'],
                'transferable_excess_qty': row['excess'],
            } for row in details])

            if net_requirement > 1e-6 and external_warehouses:
                selected_excess_pool = total_excess
                residual_targets = []
                for row in sorted(details, key=lambda value: value['shortage'], reverse=True):
                    residual = row['shortage']
                    covered_here = min(residual, selected_excess_pool)
                    residual -= covered_here
                    selected_excess_pool -= covered_here
                    if residual > 1e-6:
                        residual_targets.append([row['warehouse'], residual])

                external_sources = []
                for source_wh in external_warehouses:
                    ext_key = (product.id, source_wh.id)
                    forecast_row = external_forecast.get(ext_key, {
                        'on_hand': 0.0, 'free': 0.0, 'incoming': 0.0, 'outgoing': 0.0, 'virtual': 0.0,
                    })
                    adjusted_external = forecast_row['virtual'] + external_rfq[ext_key] + external_other_plan[ext_key] + external_extra_mo[ext_key]
                    transferable_now = min(max(forecast_row['free'], 0.0), max(adjusted_external, 0.0))
                    if transferable_now > 1e-6:
                        external_sources.append({
                            'warehouse': source_wh, 'available': transferable_now,
                            'on_hand': forecast_row['on_hand'], 'free': forecast_row['free'],
                            'forecast': adjusted_external, 'open_mo': external_open_mos[ext_key],
                        })

                external_sources.sort(key=lambda value: value['available'], reverse=True)
                suggestion_vals = []
                for destination_wh, destination_need in residual_targets:
                    initial_destination_need = destination_need
                    for source in external_sources:
                        if destination_need <= 1e-6:
                            break
                        if source['available'] <= 1e-6:
                            continue
                        qty = min(source['available'], destination_need)
                        if qty <= 1e-6:
                            continue
                        suggestion_vals.append({
                            'plan_id': self.plan.id, 'planning_line_id': line.id, 'product_id': product.id,
                            'source_warehouse_id': source['warehouse'].id, 'destination_warehouse_id': destination_wh.id,
                            'source_on_hand_qty': source['on_hand'], 'source_free_qty': source['free'],
                            'source_forecast_qty': source['forecast'], 'source_open_mo_qty': source['open_mo'],
                            'destination_shortage_qty': initial_destination_need, 'suggested_qty': qty, 'move_qty': qty,
                        })
                        source['available'] -= qty
                        destination_need -= qty
                if suggestion_vals:
                    ExternalMove.create(suggestion_vals)

        if self.plan.plan_type == 'manufacturing':
            manufacturing_lines = created.filtered(
                lambda line: line.action_manufacture
                and line.planner_production_qty > 1e-6
            )
            if manufacturing_lines:
                from .manufacturing_snapshot import ManufacturingSnapshotBuilder
                snapshot = ManufacturingSnapshotBuilder(self.plan).build(
                    manufacturing_lines
                )
                self.plan.message_post(body=(
                    'APS: se cargaron %s componente(s) de ingeniería para '
                    '%s producto(s) a fabricar.'
                ) % (len(snapshot), len(manufacturing_lines)))

                from .component_sourcing import ComponentSourcingEngine
                ComponentSourcingEngine(self.plan).run()

        return len(created)
