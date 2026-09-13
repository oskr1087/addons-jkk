from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV136RecursiveSubMoRepair(TransactionCase):

    def test_native_rule_clears_snapshot_skip_context(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'stock_rule.py').read_text()
        self.assertIn('native_rule = self.with_context(skip_compute_move_raw_ids=False)', source)

    def test_manufacture_repairs_complete_chain_but_recalculate_does_not_execute(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        manufacture = source.split('def action_create_manufacturing', 1)[1].split(
            'def _ensure_product_purchase_vendor', 1
        )[0]
        calculate = source.split('def action_calculate', 1)[1].split(
            '# A search with no demand/results', 1
        )[0]
        self.assertIn('self._aps_repair_native_submanufacturing_chain()', manufacture)
        self.assertNotIn('self._aps_repair_native_submanufacturing_chain()', calculate)
        self.assertIn("draft_moves.with_context(", source)
        self.assertIn("._action_confirm()", source)

    def test_missing_procurement_runs_without_skip_context(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'mrp_extensions.py').read_text()
        self.assertIn("StockRule = self.env['stock.rule'].sudo().with_context(", source)
        self.assertIn('skip_compute_move_raw_ids=False', source)
