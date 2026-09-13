from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV126RecalculationRefresh(TransactionCase):

    def test_removed_sales_stay_excluded(self):
        root = Path(__file__).parents[1]
        plan = (root / 'models' / 'planning_plan.py').read_text()
        lines = (root / 'models' / 'planning_lines.py').read_text()
        engine = (root / 'services' / 'simple_planning_engine.py').read_text()

        self.assertIn('excluded_sale_line_ids = fields.Many2many', plan)
        self.assertIn("'excluded_sale_line_ids'", lines)
        self.assertIn(
            "('id', 'not in', self.plan.excluded_sale_line_ids.ids)",
            engine,
        )

    def test_recalculate_refreshes_sourcing_but_creates_no_execution_plan(self):
        root = Path(__file__).parents[1]
        plan = (root / 'models' / 'planning_plan.py').read_text()

        section = plan.split(
            'result_count = SimplePlanningEngine(self).run()', 1
        )[1].split(
            '# A search with no demand/results', 1
        )[0]

        self.assertIn('self._refresh_component_sourcing()', section)
        self.assertNotIn('self._sync_component_purchase_plan()', section)
        self.assertNotIn('_aps_repair_native_submanufacturing_chain()', section)
        self.assertNotIn('_aps_launch_missing_component_procurements()', section)

    def test_current_source_lines_respect_exclusions(self):
        root = Path(__file__).parents[1]
        plan = (root / 'models' / 'planning_plan.py').read_text()

        self.assertIn(
            'return lines - committed - self.excluded_sale_line_ids',
            plan,
        )
