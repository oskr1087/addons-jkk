from odoo.tests.common import TransactionCase

from ..services.manufacturing_snapshot import ManufacturingSnapshotBuilder


class TestAPSComponentSnapshot(TransactionCase):

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

    def test_snapshot_keeps_parent_hierarchy_and_quantities(self):
        finished = self._product('APS Finished Snapshot')
        sub = self._product('APS Sub Snapshot')
        leaf = self._product('APS Leaf Snapshot')
        self._bom(finished, [(sub, 2.0)])
        self._bom(sub, [(leaf, 3.0)])

        plan = self.env['mrp.planning.plan'].create({
            'name': 'APS-SNAPSHOT-TEST',
            'plan_type': 'manufacturing',
            'warehouse_ids': [(6, 0, self.warehouse.ids)],
            'date_end': '2030-01-01 00:00:00',
        })
        line = self.env['mrp.planning.plan.line'].create({
            'plan_id': plan.id,
            'product_id': finished.id,
            'target_warehouse_id': self.warehouse.id,
            'planner_production_qty': 10.0,
            'action_manufacture': True,
        })

        snapshot = ManufacturingSnapshotBuilder(plan).build(line)
        first = snapshot.filtered(lambda c: c.product_id == sub)
        second = snapshot.filtered(lambda c: c.product_id == leaf)
        self.assertEqual(first.level, 1)
        self.assertAlmostEqual(first.planned_qty, 20.0)
        self.assertEqual(second.parent_line_id, first)
        self.assertEqual(second.level, 2)
        self.assertAlmostEqual(second.planned_qty, 60.0)

    def test_manual_component_is_tracked(self):
        product = self._product('APS Manual Component')
        finished = self._product('APS Manual Finished')
        plan = self.env['mrp.planning.plan'].create({
            'name': 'APS-MANUAL-TEST',
            'plan_type': 'manufacturing',
            'warehouse_ids': [(6, 0, self.warehouse.ids)],
            'date_end': '2030-01-01 00:00:00',
        })
        line = self.env['mrp.planning.plan.line'].create({
            'plan_id': plan.id,
            'product_id': finished.id,
            'target_warehouse_id': self.warehouse.id,
            'planner_production_qty': 1.0,
            'action_manufacture': True,
        })
        component = self.env['mrp.planning.production.component'].create({
            'plan_id': plan.id,
            'planning_line_id': line.id,
            'root_product_id': finished.id,
            'product_id': product.id,
            'product_uom_id': product.uom_id.id,
            'planned_qty': 5.0,
            'level': 1,
        })
        self.assertEqual(component.change_type, 'manual')
        self.assertTrue(component.include_in_mo)
