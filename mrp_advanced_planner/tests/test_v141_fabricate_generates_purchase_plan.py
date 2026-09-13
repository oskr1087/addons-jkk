from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV141FabricateGeneratesPurchasePlan(TransactionCase):

    def test_calculate_remains_analysis_only(self):
        root = Path(__file__).parents[1]
        source = (root / "models" / "planning_plan.py").read_text()
        section = source.split(
            "result_count = SimplePlanningEngine(self).run()", 1
        )[1].split("# A search with no demand/results", 1)[0]
        self.assertNotIn("_sync_component_purchase_plan()", section)
        self.assertNotIn("action_create_purchases()", section)

    def test_fabricate_builds_related_purchase_plan_but_not_pos(self):
        root = Path(__file__).parents[1]
        source = (root / "models" / "planning_plan.py").read_text()
        method = source.split("def action_create_manufacturing", 1)[1].split(
            "def _ensure_product_purchase_vendor", 1
        )[0]
        self.assertIn("self._sync_component_purchase_plan()", method)
        self.assertNotIn("action_create_purchases()", method)
        self.assertNotIn("self.env['purchase.order']", method)
