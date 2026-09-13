from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV115NonStockableActionDone(TransactionCase):

    def test_bypass_is_only_aps_nonstockable_raw_material(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'lot_reservation.py').read_text()
        helper = source.split(
            'def _aps_is_nonstockable_tracked_consumption', 1
        )[1].split('def _action_done', 1)[0]
        self.assertIn('move.raw_material_production_id', helper)
        self.assertIn('production.advanced_plan_id', helper)
        self.assertIn('production.planning_plan_line_id', helper)
        self.assertIn('production.aps_component_snapshot', helper)
        self.assertIn('not self.product_id.is_storable', helper)
        self.assertIn("self.product_id.tracking != 'none'", helper)
        self.assertIn('not self.lot_id', helper)

    def test_action_done_splits_native_and_nonstockable_lines(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'lot_reservation.py').read_text()
        method = source.split(
            'def _action_done(self):', 1
        )[1].split('def _aps_source_warehouse', 1)[0]
        self.assertIn('normal_lines = self - aps_nonstockable', method)
        self.assertIn('super(StockMoveLine, normal_lines)._action_done()', method)
        self.assertIn("'picked': True", method)
