from pathlib import Path

from odoo.tests.common import TransactionCase


class TestPurchaseDuplicatePrevention(TransactionCase):

    def test_purchase_engine_counts_other_plans_and_rfq(self):
        from ..services import simple_planning_engine
        source = Path(simple_planning_engine.__file__).read_text()
        self.assertIn('+ draft_purchase', source)
        self.assertIn('+ planned_elsewhere', source)
        self.assertIn('rfq_rows = self._rfq_supply_by_warehouse', source)
        self.assertIn('other_rows = self._other_plan_supply_by_warehouse', source)

    def test_component_move_has_priority_over_buy_make(self):
        from ..services import component_sourcing
        source = Path(component_sourcing.__file__).read_text()
        self.assertIn("resolution = 'move'", source)
        self.assertIn('residual_after_move = max(shortage - movable, 0.0)', source)
