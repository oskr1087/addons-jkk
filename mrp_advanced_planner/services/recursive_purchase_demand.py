from collections import defaultdict

from odoo.exceptions import UserError

from .bom_batch import BatchBomGraph


class RecursivePurchaseDemandEngine:
    """Explode purchase-component demand directly from pending SO lines.

    No manufacturing planning record is read. For every pending sales product
    that has a BoM, APS first determines the real finished-product shortage in
    the selected warehouse (forecast + RFQ + other APS commitments + confirmed
    MO supply not already present in forecast). Only that shortage is exploded.

    Intermediate manufactured components are netted against their own forecast
    before their BoM is recursively exploded. Leaf components are returned as
    gross purchase demand and are netted once by the main purchase planner.
    """

    MAX_DEPTH = 30

    def __init__(self, purchase_plan, sale_demand, helpers):
        self.plan = purchase_plan
        self.env = purchase_plan.env
        self.company = purchase_plan.company_id
        self.sale_demand = sale_demand
        self.helpers = helpers
        self.graph = BatchBomGraph(self.env, self.company)
        self.graph.preload(
            self.env['product.product'].browse(list(self.sale_demand))
        )
        if self.helpers.get('prime_products'):
            self.helpers['prime_products'](self.graph.all_products())
        self._intermediate_consumed = defaultdict(float)

    def _find_bom(self, product):
        return self.graph.bom(product)

    def _component_qty(self, bom, line, parent_product, parent_qty):
        parent_bom_uom = parent_product.uom_id._compute_quantity(
            parent_qty, bom.product_uom_id
        )
        factor = parent_bom_uom / (bom.product_qty or 1.0)
        line_qty = (line.product_qty or 0.0) * factor
        return line.product_uom_id._compute_quantity(
            line_qty, line.product_id.uom_id
        )

    def _skip_line(self, line, parent_product):
        skip = getattr(line, '_skip_bom_line', None)
        if not skip:
            return False
        try:
            return bool(skip(parent_product))
        except TypeError:
            return False

    def _requirement(self, **vals):
        return self.env['mrp.planning.requirement'].create(vals)

    def _explode(self, root, product, qty, warehouse, source_label, result,
                 path=None, level=0, parent=False, visiting=None):
        if qty <= 1e-6:
            return
        if level > self.MAX_DEPTH:
            raise UserError('La explosión de LdM superó %s niveles.' % self.MAX_DEPTH)

        path = list(path or [root.display_name])
        visiting = set(visiting or ())
        if product.id in visiting:
            raise UserError(
                'Se detectó una referencia circular de LdM: %s'
                % ' → '.join(path + [product.display_name])
            )
        visiting.add(product.id)

        bom = self._find_bom(product)
        if not bom:
            return

        for bom_line in bom.sudo().bom_line_ids:
            component = bom_line.product_id
            if not component or self._skip_line(bom_line, product):
                continue
            required = self._component_qty(bom, bom_line, product, qty)
            if required <= 1e-6:
                continue

            component_path = path + [component.display_name]
            child_bom = self._find_bom(component)

            if child_bom:
                available = self.helpers['available_supply'](
                    component, warehouse
                )
                key = (component.id, warehouse.id)
                remaining_available = max(
                    available - self._intermediate_consumed[key], 0.0
                )
                used = min(required, remaining_available)
                self._intermediate_consumed[key] += used
                shortage = max(required - used, 0.0)

                req = self._requirement(
                    plan_id=self.plan.id,
                    parent_id=parent.id if parent else False,
                    parent_line_id=parent.id if parent else False,
                    product_id=component.id,
                    root_product_id=root.id,
                    warehouse_id=warehouse.id,
                    bom_id=bom.id,
                    bom_line_id=bom_line.id,
                    source_plan_name=source_label,
                    path=' → '.join(component_path),
                    level=level + 1,
                    required_qty=required,
                    available_qty=used,
                    net_qty=shortage,
                    date_required=self.plan.date_end,
                    supply_type='available' if shortage <= 1e-6 else 'make',
                )
                if shortage > 1e-6:
                    self._explode(
                        root, component, shortage, warehouse, source_label,
                        result, component_path, level + 1, req, visiting
                    )
            else:
                self._requirement(
                    plan_id=self.plan.id,
                    parent_id=parent.id if parent else False,
                    parent_line_id=parent.id if parent else False,
                    product_id=component.id,
                    root_product_id=root.id,
                    warehouse_id=warehouse.id,
                    bom_id=bom.id,
                    bom_line_id=bom_line.id,
                    source_plan_name=source_label,
                    path=' → '.join(component_path),
                    level=level + 1,
                    required_qty=required,
                    available_qty=0.0,
                    net_qty=required,
                    date_required=self.plan.date_end,
                    supply_type='buy',
                )
                row = result[component.id]
                row['gross_qty'] += required
                row['by_warehouse'][warehouse.id] += required
                row['origins'].append(
                    '%s | %s | %s | %.6g'
                    % (source_label, warehouse.display_name,
                       ' → '.join(component_path), required)
                )
                row['date_required'] = (
                    min(row['date_required'], self.plan.date_end)
                    if row['date_required'] else self.plan.date_end
                )

    def run(self):
        self.plan.requirement_ids.unlink()
        result = defaultdict(lambda: {
            'gross_qty': 0.0,
            'by_warehouse': defaultdict(float),
            'origins': [],
            'date_required': False,
        })

        Product = self.env['product.product']
        for product_id, source in self.sale_demand.items():
            product = Product.browse(product_id)
            if not self._find_bom(product):
                continue

            sale_orders = source['sale_lines'].mapped('order_id')
            source_label = ', '.join(sale_orders.mapped('name')) or 'Ventas'

            # Compute shortage separately for every selected sales warehouse.
            # The SO demand is already represented by outgoing stock moves in
            # virtual_available when Odoo has created them, so we do NOT
            # subtract sales_qty again here.
            for warehouse in self.plan.warehouse_ids:
                demand = source['by_warehouse'].get(warehouse.id, 0.0)
                if demand <= 1e-6:
                    continue
                available = self.helpers['available_supply'](
                    product, warehouse
                )
                shortage = max(demand - available, 0.0)
                if shortage <= 1e-6:
                    continue
                self._explode(
                    root=product,
                    product=product,
                    qty=shortage,
                    warehouse=warehouse,
                    source_label=source_label,
                    result=result,
                    path=[product.display_name],
                )
        return result
