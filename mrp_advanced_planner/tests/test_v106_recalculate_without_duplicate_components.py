from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV106RecalculateWithoutDuplicateComponents(TransactionCase):

    def test_executed_sale_lines_are_excluded_from_fresh_demand(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'services' / 'simple_planning_engine.py'
        ).read_text()
        run = source.split('def run(self):', 1)[1]
        self.assertIn('covered_direct_sale_lines', run)
        self.assertIn(
            'remaining_sale_lines =',
            run,
        )
        self.assertIn(
            'original_sale_lines - covered_direct_sale_lines',
            run,
        )

    def test_only_direct_sale_demand_is_removed(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'services' / 'simple_planning_engine.py'
        ).read_text()
        self.assertIn(
            "executed.source_type not in ('sale', 'mixed')",
            source,
        )
        self.assertIn(
            'sale_line.product_id == executed.product_id',
            source,
        )

    def test_second_root_mo_is_blocked_for_same_sale_demand(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        self.assertIn(
            'def _aps_validate_no_duplicate_executed_sale_demand',
            source,
        )
        action = source.split(
            'def action_create_manufacturing', 1
        )[1].split('def _ensure_product_purchase_vendor', 1)[0]
        self.assertIn(
            '_aps_validate_no_duplicate_executed_sale_demand(lines)',
            action,
        )
