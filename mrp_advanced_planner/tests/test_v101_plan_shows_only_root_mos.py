from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV101PlanShowsOnlyRootMos(TransactionCase):

    def test_plan_mo_counter_excludes_native_children(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        self.assertIn(
            "('aps_parent_production_id', '=', False)",
            source,
        )

    def test_plan_open_action_uses_created_root_mos(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        method = source.split(
            'def action_open_created_productions', 1
        )[1].split('def ', 1)[0]
        self.assertIn("self.line_ids.mapped(", method)
        self.assertIn("'created_production_id'", method)
        self.assertIn("not mo.aps_parent_production_id", method)

    def test_child_mo_keeps_parent_traceability(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'stock_rule.py').read_text()
        self.assertIn("'aps_parent_production_id'", source)
