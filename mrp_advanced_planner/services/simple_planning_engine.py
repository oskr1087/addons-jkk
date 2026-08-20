from collections import defaultdict

from odoo import fields

from .odoo19_compat import find_bom


class SimplePlanningEngine:
    """Plan using Odoo forecast quantities, not only quantities on hand.

    Odoo's ``virtual_available`` already represents:
        on hand + incoming - outgoing

    Therefore sale demand, confirmed purchases, confirmed manufacturing orders
    and confirmed internal transfers must NOT be subtracted/added a second time.

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

        grouped = defaultdict(lambda: {
            'sale_lines': self.env['sale.order.line'],
            'sales_qty': 0.0,
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
        """Informational only. Never added to net requirement (already in forecast)."""
        result = defaultdict(float)
        Production = self.env['mrp.production']
        state_selection = Production._fields['state'].selection
        if callable(state_selection):
            state_selection = state_selection(self.env)
        valid_states = [s for s in ('confirmed', 'progress', 'to_close') if s in dict(state_selection)]
        picking_to_wh = {wh.manu_type_id.id: wh.id for wh in warehouses if wh.manu_type_id}
        if not picking_to_wh or not valid_states:
            return result

        mos = Production.search([
            ('company_id', '=', self.plan.company_id.id),
            ('product_id', 'in', products.ids),
            ('state', 'in', valid_states),
            ('picking_type_id', 'in', list(picking_to_wh)),
        ])
        for mo in mos:
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
            result[(mo.product_id.id, picking_to_wh[mo.picking_type_id.id])] += remaining
        return result

    def run(self):
        self.plan._ensure_warehouse_ids()
        self.plan.line_ids.unlink()

        warehouses = self.plan.warehouse_ids
        grouped = self._sale_demand(warehouses)
        if not grouped:
            return 0

        products = self.env['product.product'].browse(list(grouped))
        odoo_forecast = self._odoo_forecast_by_warehouse(products, warehouses)
        rfq_supply = self._rfq_supply_by_warehouse(products, warehouses)
        other_plan_supply = self._other_plan_supply_by_warehouse(products, warehouses)
        open_mos = self._open_mo_information(products, warehouses)

        Line = self.env['mrp.planning.plan.line']
        Detail = self.env['mrp.planning.plan.line.warehouse']
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
                adjusted_forecast = (
                    forecast['virtual']
                    + draft_purchase
                    + planned_elsewhere
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
                    'demand': source['by_warehouse'].get(warehouse.id, 0.0),
                    'on_hand': forecast['on_hand'],
                    'free': forecast['free'],
                    'incoming': forecast['incoming'],
                    'outgoing': forecast['outgoing'],
                    'rfq': draft_purchase,
                    'other_plan': planned_elsewhere,
                    'forecast': adjusted_forecast,
                    'open_mo': open_mos[key],
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
            line = Line.create({
                'plan_id': self.plan.id,
                'sale_line_id': sale_lines[:1].id,
                'sale_line_ids': [(6, 0, sale_lines.ids)],
                'product_id': product.id,
                'target_warehouse_id': target_wh.id if target_wh else False,
                'sales_qty': source['sales_qty'],
                'demand_qty': source['sales_qty'],
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
                'date_required': source['date_required'],
                'source_type': 'sale',
                'source_reference': '%s pedidos / %s líneas de venta' % (
                    len(sale_lines.mapped('order_id')), len(sale_lines)
                ),
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
                'local_shortage_qty': row['shortage'],
                'transferable_excess_qty': row['excess'],
            } for row in details])

        return len(created)
