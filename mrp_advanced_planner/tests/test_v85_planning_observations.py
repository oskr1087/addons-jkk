from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV85PlanningObservations(TransactionCase):

    def test_bom_precision_is_four_decimals(self):
        self.assertEqual(
            self.env['mrp.bom.line']._fields['product_qty'].digits,
            (16, 4),
        )

    def test_component_quantity_is_four_decimals(self):
        self.assertEqual(
            self.env['mrp.planning.production.component']._fields[
                'planned_qty'
            ].digits,
            (16, 4),
        )

    def test_plan_can_be_deleted_by_acl(self):
        access = self.env['ir.model.access'].search([
            ('model_id.model', '=', 'mrp.planning.plan'),
            ('group_id', '=',
             self.env.ref(
                 'mrp_advanced_planner.group_planner_user'
             ).id),
        ], limit=1)
        self.assertTrue(access.perm_unlink)

    def test_incremental_recalc_preserves_generated_lines(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'services' / 'simple_planning_engine.py'
        ).read_text()
        self.assertIn('executed_lines = self.plan.line_ids.filtered', source)
        self.assertIn('pending_lines = self.plan.line_ids - executed_lines', source)
        self.assertNotIn('self.plan.line_ids.unlink()', source)

    def test_component_rows_are_not_inline_editable(self):
        root = Path(__file__).parents[1]
        xml = (
            root / 'static' / 'src' / 'xml' /
            'planning_component_tree.xml'
        ).read_text()
        self.assertNotIn('t-on-change="(ev) => this.saveQty(row, ev)"', xml)

    def test_creation_date_is_visible(self):
        root = Path(__file__).parents[1]
        xml = (
            root / 'views' / 'planning_plan_views.xml'
        ).read_text()
        self.assertIn('Fecha creación APS', xml)

    def test_aps_mo_checks_small_component_quantities(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'models' / 'mrp_extensions.py'
        ).read_text()
        self.assertIn('requiere %(qty).4f', source)
        self.assertIn('expected_qty > 1e-9', source)
