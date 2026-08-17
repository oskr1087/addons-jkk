from collections import defaultdict

from .odoo19_compat import find_bom


class SimplePlanningEngine:
    """Aggregate pending sale demand by product across the warehouses selected on the plan."""

    def __init__(self, plan):
        self.plan = plan
        self.env = plan.env

    def run(self):
        self.plan._ensure_warehouse_ids()
        self.plan.line_ids.unlink()

        warehouses = self.plan.warehouse_ids
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
        sale_lines = SaleLine.search(domain, order='planning_delivery_date asc, order_id asc, sequence asc, id asc')

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
            pending = line.product_uom_id._compute_quantity(pending_sale_uom, line.product_id.uom_id)
            if pending <= 0:
                continue
            row = grouped[line.product_id.id]
            row['sale_lines'] |= line
            row['sales_qty'] += pending
            row['by_warehouse'][line.order_id.warehouse_id.id] += pending
            if not row['date_required'] or line.planning_delivery_date < row['date_required']:
                row['date_required'] = line.planning_delivery_date

        if not grouped:
            return 0

        products = self.env['product.product'].browse(list(grouped))
        stock_by_product_wh = defaultdict(float)
        for warehouse in warehouses:
            for product in products:
                product_ctx = product.with_context(
                    location=warehouse.lot_stock_id.id,
                    warehouse=warehouse.id,
                    company_owned=True,
                )
                free_qty = getattr(product_ctx, 'free_qty', product_ctx.qty_available)
                stock_by_product_wh[(product.id, warehouse.id)] = max(free_qty, 0.0)

        # Open MOs by product/warehouse. Only MOs expected within the planning horizon are considered.
        mo_by_product_wh = defaultdict(float)
        Production = self.env['mrp.production']
        state_selection = Production._fields['state'].selection
        if callable(state_selection):
            state_selection = state_selection(self.env)
        valid_states = [s for s in ('confirmed', 'progress', 'to_close') if s in dict(state_selection)]
        picking_to_wh = {wh.manu_type_id.id: wh.id for wh in warehouses if wh.manu_type_id}
        if picking_to_wh and valid_states:
            mos = Production.search([
                ('company_id', '=', self.plan.company_id.id),
                ('product_id', 'in', products.ids),
                ('state', 'in', valid_states),
                ('picking_type_id', 'in', list(picking_to_wh)),
            ])
            for mo in mos:
                due = getattr(mo, 'date_finished', False) or getattr(mo, 'date_deadline', False) or getattr(mo, 'date_start', False)
                if due and due > self.plan.date_end:
                    continue
                produced = getattr(mo, 'qty_produced', 0.0) or 0.0
                remaining = max((mo.product_qty or 0.0) - produced, 0.0)
                if mo.product_uom_id and mo.product_uom_id != mo.product_id.uom_id:
                    remaining = mo.product_uom_id._compute_quantity(remaining, mo.product_id.uom_id)
                mo_by_product_wh[(mo.product_id.id, picking_to_wh[mo.picking_type_id.id])] += remaining

        Line = self.env['mrp.planning.plan.line']
        Detail = self.env['mrp.planning.plan.line.warehouse']
        created = Line
        for product in products.sorted(key=lambda p: (p.default_code or '', p.display_name, p.id)):
            source = grouped[product.id]
            details = []
            total_stock = 0.0
            total_open_mo = 0.0
            total_shortage = 0.0
            total_excess = 0.0
            target_wh = warehouses[:1]
            largest_shortage = -1.0

            for warehouse in warehouses:
                demand = source['by_warehouse'].get(warehouse.id, 0.0)
                stock = stock_by_product_wh[(product.id, warehouse.id)]
                open_mo = mo_by_product_wh[(product.id, warehouse.id)]
                shortage = max(demand - stock - open_mo, 0.0)
                excess = max(stock - demand, 0.0)
                total_stock += stock
                total_open_mo += open_mo
                total_shortage += shortage
                total_excess += excess
                if shortage > largest_shortage:
                    largest_shortage = shortage
                    target_wh = warehouse
                details.append((warehouse, demand, stock, open_mo, shortage, excess))

            net_requirement = max(source['sales_qty'] - total_stock - total_open_mo, 0.0)
            move_suggested = min(total_shortage, total_excess)
            bom = find_bom(self.env, product, company_id=self.plan.company_id.id)

            manufacture = purchase = move = False
            planner_qty = 0.0
            if net_requirement > 0:
                if bom:
                    manufacture = True
                else:
                    purchase = True
                planner_qty = net_requirement
            elif move_suggested > 0:
                move = True
                planner_qty = move_suggested

            purchase_vendor = False
            if purchase:
                seller = product.with_company(self.plan.company_id)._select_seller(
                    quantity=planner_qty or 1.0,
                    date=fields.Date.context_today(self.plan),
                    uom_id=product.uom_id,
                )
                purchase_vendor = seller.partner_id if seller else False

            sale_lines = source['sale_lines']
            line = Line.create({
                'plan_id': self.plan.id,
                'sale_line_id': sale_lines[:1].id,
                'sale_line_ids': [(6, 0, sale_lines.ids)],
                'product_id': product.id,
                'target_warehouse_id': target_wh.id if target_wh else False,
                'sales_qty': source['sales_qty'],
                'demand_qty': source['sales_qty'],
                'stock_qty': total_stock,
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
                'source_reference': '%s pedidos / %s líneas de venta' % (len(sale_lines.mapped('order_id')), len(sale_lines)),
                'bom_id': bom.id if bom else False,
                'state': 'planned',
            })
            created |= line
            Detail.create([{
                'planning_line_id': line.id,
                'warehouse_id': warehouse.id,
                'demand_qty': demand,
                'stock_qty': stock,
                'open_mo_qty': open_mo,
                'local_shortage_qty': shortage,
                'transferable_excess_qty': excess,
            } for warehouse, demand, stock, open_mo, shortage, excess in details])

        return len(created)
