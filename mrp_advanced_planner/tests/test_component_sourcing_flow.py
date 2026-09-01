from odoo.tests.common import TransactionCase

from ..services.manufacturing_snapshot import ManufacturingSnapshotBuilder
from ..services.component_sourcing import ComponentSourcingEngine


class TestComponentSourcingFlow(TransactionCase):

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
            'company_id': self.company.id,
            'bom_line_ids': [(0, 0, {
                'product_id': component.id,
                'product_qty': qty,
                'product_uom_id': component.uom_id.id,
            }) for component, qty in components],
        })

    def _plan_line(self, product, qty):
        plan = self.env['mrp.planning.plan'].with_context(
            aps_internal_create=True
        ).create({
            'plan_type': 'manufacturing',
            'warehouse_ids': [(6, 0, self.warehouse.ids)],
            'company_id': self.company.id,
            'date_end': '2030-01-01 00:00:00',
            'state': 'calculated',
        })
        line = self.env['mrp.planning.plan.line'].create({
            'plan_id': plan.id,
            'product_id': product.id,
            'target_warehouse_id': self.warehouse.id,
            'planner_production_qty': qty,
            'action_manufacture': True,
            'date_required': '2029-12-15 00:00:00',
        })
        return plan, line

    def test_recursive_components_classify_make_and_buy(self):
        finished = self._product('APS Source Finished')
        sub = self._product('APS Source Sub')
        raw_a = self._product('APS Source Raw A')
        raw_b = self._product('APS Source Raw B')
        self._bom(sub, [(raw_b, 3.0)])
        self._bom(finished, [(sub, 2.0), (raw_a, 1.0)])

        plan, line = self._plan_line(finished, 10.0)
        ManufacturingSnapshotBuilder(plan).build(line)
        ComponentSourcingEngine(plan).run()

        sub_line = plan.production_component_ids.filtered(
            lambda c: c.product_id == sub
        )
        raw_a_line = plan.production_component_ids.filtered(
            lambda c: c.product_id == raw_a
        )
        raw_b_line = plan.production_component_ids.filtered(
            lambda c: c.product_id == raw_b
        )

        self.assertAlmostEqual(sub_line.effective_required_qty, 20.0)
        self.assertEqual(sub_line.supply_resolution, 'manufacture')
        self.assertAlmostEqual(sub_line.to_manufacture_qty, 20.0)

        self.assertEqual(raw_a_line.supply_resolution, 'purchase')
        self.assertAlmostEqual(raw_a_line.to_purchase_qty, 10.0)

        self.assertAlmostEqual(raw_b_line.effective_required_qty, 60.0)
        self.assertEqual(raw_b_line.supply_resolution, 'purchase')
        self.assertAlmostEqual(raw_b_line.to_purchase_qty, 60.0)

    def test_generated_purchase_plan_aggregates_component_demand(self):
        finished = self._product('APS Buy Finished')
        raw = self._product('APS Buy Raw')
        self._bom(finished, [(raw, 2.0)])

        plan, line = self._plan_line(finished, 10.0)
        ManufacturingSnapshotBuilder(plan).build(line)
        ComponentSourcingEngine(plan).run()
        purchase_plan = plan._sync_component_purchase_plan()

        self.assertTrue(purchase_plan)
        self.assertEqual(purchase_plan.plan_type, 'purchase')
        self.assertEqual(purchase_plan.source_manufacturing_plan_id, plan)
        buy_line = purchase_plan.line_ids.filtered(
            lambda l: l.product_id == raw
        )
        self.assertAlmostEqual(buy_line.planner_production_qty, 20.0)
        self.assertTrue(buy_line.action_purchase)
