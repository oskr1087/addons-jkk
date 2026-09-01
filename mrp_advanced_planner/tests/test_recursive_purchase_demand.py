from collections import defaultdict

from odoo.tests.common import TransactionCase

from ..services.recursive_purchase_demand import RecursivePurchaseDemandEngine


class TestRecursivePurchaseDemandFromSales(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.warehouse = self.env['stock.warehouse'].search([
            ('company_id', '=', self.company.id)
        ], limit=1)

    def _product(self, name):
        return self.env['product.product'].create({
            'name': name,
            'is_storable': True,
        })

    def _bom(self, product, components):
        return self.env['mrp.bom'].create({
            'product_tmpl_id': product.product_tmpl_id.id,
            'product_id': product.id,
            'product_qty': 1.0,
            'product_uom_id': product.uom_id.id,
            'bom_line_ids': [(0, 0, {
                'product_id': component.id,
                'product_qty': qty,
                'product_uom_id': component.uom_id.id,
            }) for component, qty in components],
        })

    def test_recursive_purchase_uses_so_snapshot_not_manufacturing_plan(self):
        finished = self._product('SO Finished APS')
        sub = self._product('SO Subassembly APS')
        leaf = self._product('SO Purchased Leaf APS')
        self._bom(finished, [(sub, 2.0)])
        self._bom(sub, [(leaf, 3.0)])

        plan = self.env['mrp.planning.plan'].create({
            'name': 'BUY-FROM-SO',
            'plan_type': 'purchase',
            'warehouse_ids': [(6, 0, self.warehouse.ids)],
            'date_end': '2030-01-01 00:00:00',
        })

        fake_sale_demand = defaultdict(lambda: {
            'sale_lines': self.env['sale.order.line'],
            'sales_qty': 0.0,
            'mrp_component_qty': 0.0,
            'component_by_warehouse': defaultdict(float),
            'bom_origins': [],
            'date_required': False,
            'by_warehouse': defaultdict(float),
        })
        fake_sale_demand[finished.id]['sales_qty'] = 10.0
        fake_sale_demand[finished.id]['by_warehouse'][self.warehouse.id] = 10.0

        # Finished shortage = 10, intermediate subassembly has no supply.
        def available_supply(product, warehouse):
            if product == finished:
                return -10.0
            return 0.0

        result = RecursivePurchaseDemandEngine(
            plan, fake_sale_demand, {'available_supply': available_supply}
        ).run()

        self.assertFalse(
            self.env['mrp.planning.plan'].search_count([
                ('plan_type', '=', 'manufacturing'),
                ('name', '=', 'BUY-FROM-SO'),
            ])
        )
        self.assertIn(leaf.id, result)
        self.assertAlmostEqual(result[leaf.id]['gross_qty'], 60.0)
