from collections import defaultdict

from .odoo19_compat import find_bom


class SimplePlanningEngine:
    """Plan sale-order lines by delivery date.

    Coverage is allocated chronologically per product so the same stock or open MO quantity
    is never subtracted more than once when a product exists on several sale lines.
    """

    def __init__(self, plan):
        self.plan = plan
        self.env = plan.env

    def run(self):
        self.plan.line_ids.unlink()

        SaleLine = self.env['sale.order.line']
        domain = [
            ('order_id.state', '=', 'sale'),
            ('order_id.company_id', '=', self.plan.company_id.id),
            ('product_id', '!=', False),
            ('display_type', '=', False),
            ('product_uom_qty', '>', 0),
            ('planning_delivery_date', '!=', False),
            ('planning_delivery_date', '<=', self.plan.date_end),
        ]
        sale_lines = SaleLine.search(domain, order='planning_delivery_date asc, order_id asc, sequence asc, id asc')
        sale_lines = sale_lines.filtered(
            lambda line: not line.order_id.warehouse_id or line.order_id.warehouse_id == self.plan.warehouse_id
        )

        pending_rows = []
        product_ids = set()
        for line in sale_lines:
            pending = max(line.product_uom_qty - line.qty_delivered, 0.0)
            if not pending:
                continue
            pending_product_uom = line.product_uom_id._compute_quantity(pending, line.product_id.uom_id)
            if pending_product_uom <= 0:
                continue
            pending_rows.append((line, pending_product_uom))
            product_ids.add(line.product_id.id)

        if not pending_rows:
            return 0

        products = self.env['product.product'].browse(product_ids)
        location = self.plan.warehouse_id.lot_stock_id
        available_stock = {}
        for product in products:
            product_ctx = product.with_context(
                location=location.id,
                warehouse=self.plan.warehouse_id.id,
                company_owned=True,
            )
            free_qty = getattr(product_ctx, 'free_qty', product_ctx.qty_available)
            available_stock[product.id] = max(free_qty, 0.0)

        # Open manufacturing is treated as dated supply. Only MOs due on/before a sale-line
        # delivery date can cover that line.
        Production = self.env['mrp.production']
        open_state_candidates = ['confirmed', 'progress', 'to_close']
        selection = Production._fields['state'].selection
        if callable(selection):
            selection = selection(self.env)
        valid_states = [key for key in open_state_candidates if key in dict(selection)]
        mo_domain = [
            ('company_id', '=', self.plan.company_id.id),
            ('product_id', 'in', products.ids),
            ('state', 'in', valid_states),
        ]
        if self.plan.warehouse_id.manu_type_id:
            mo_domain.append(('picking_type_id', '=', self.plan.warehouse_id.manu_type_id.id))

        mo_supply = defaultdict(list)
        for mo in Production.search(mo_domain):
            produced = getattr(mo, 'qty_produced', 0.0) or 0.0
            remaining = max(mo.product_qty - produced, 0.0)
            if mo.product_uom_id and mo.product_uom_id != mo.product_id.uom_id:
                remaining = mo.product_uom_id._compute_quantity(remaining, mo.product_id.uom_id)
            if not remaining:
                continue
            due_date = (
                getattr(mo, 'date_finished', False)
                or getattr(mo, 'date_deadline', False)
                or getattr(mo, 'date_start', False)
                or self.plan.date_end
            )
            if due_date <= self.plan.date_end:
                mo_supply[mo.product_id.id].append((due_date, remaining))
        for product_id in mo_supply:
            mo_supply[product_id].sort(key=lambda row: row[0])

        mo_index = defaultdict(int)
        mo_pool = defaultdict(float)
        vals_list = []

        for sale_line, pending_qty in pending_rows:
            product = sale_line.product_id
            product_id = product.id
            required_date = sale_line.planning_delivery_date

            # Make manufacturing supply available only when its expected date is reached.
            supplies = mo_supply[product_id]
            idx = mo_index[product_id]
            while idx < len(supplies) and supplies[idx][0] <= required_date:
                mo_pool[product_id] += supplies[idx][1]
                idx += 1
            mo_index[product_id] = idx

            stock_used = min(available_stock.get(product_id, 0.0), pending_qty)
            available_stock[product_id] = max(available_stock.get(product_id, 0.0) - stock_used, 0.0)

            remaining_after_stock = max(pending_qty - stock_used, 0.0)
            manufacturing_used = min(mo_pool[product_id], remaining_after_stock)
            mo_pool[product_id] = max(mo_pool[product_id] - manufacturing_used, 0.0)

            suggested = max(remaining_after_stock - manufacturing_used, 0.0)
            bom = find_bom(self.env, product, company_id=self.plan.company_id.id)

            vals_list.append({
                'plan_id': self.plan.id,
                'sale_line_id': sale_line.id,
                'product_id': product_id,
                'sales_qty': pending_qty,
                'demand_qty': pending_qty,
                'stock_qty': stock_used,
                'production_qty': manufacturing_used,
                'net_requirement_qty': suggested,
                'planned_production_qty': suggested,
                'date_required': required_date,
                'source_type': 'sale',
                'source_reference': f'{sale_line.order_id.name} / Línea {sale_line.id}',
                'bom_id': bom.id if bom else False,
                'state': 'planned' if bom or not suggested else 'blocked',
            })

        if vals_list:
            self.env['mrp.planning.plan.line'].create(vals_list)
        return len(vals_list)
