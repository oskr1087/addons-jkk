from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV140CalculateNoExecution(TransactionCase):

    def test_manufacturing_calculate_has_no_execution_side_effects(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        section = source.split(
            'result_count = SimplePlanningEngine(self).run()', 1
        )[1].split('# A search with no demand/results', 1)[0]

        self.assertIn('self._refresh_component_sourcing()', section)
        self.assertNotIn('_sync_component_purchase_plan()', section)
        self.assertNotIn('_aps_launch_missing_component_procurements()', section)
        self.assertNotIn('_aps_repair_native_submanufacturing_chain()', section)
        self.assertNotIn("self.env['purchase.order']", section)

    def test_purchase_plan_can_be_prepared_from_explicit_button(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        method = source.split(
            'def action_open_generated_purchase_plan', 1
        )[1].split('def _aps_validate_no_duplicate_engineering_rows', 1)[0]
        self.assertIn('self._refresh_component_sourcing()', method)
        self.assertIn('self._sync_component_purchase_plan()', method)

    def test_fabricate_prepares_related_purchase_plan(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        method = source.split('def action_create_manufacturing', 1)[1].split(
            'def _ensure_product_purchase_vendor', 1
        )[0]
        self.assertIn('_sync_component_purchase_plan()', method)
