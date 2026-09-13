from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV112NonStockableNeverRequiresLot(TransactionCase):

    def test_aps_finalization_excludes_nonstockable_from_lot_coverage(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'mrp_extensions.py').read_text()
        method = source.split(
            'def _aps_validate_lot_reservation_coverage', 1
        )[1].split('def button_mark_done', 1)[0]
        self.assertIn('component.product_id.is_storable', method)

    def test_stock_move_line_skips_native_lot_requirement_only_for_aps_nonstockable(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'lot_reservation.py').read_text()
        method = source.split(
            'def _exclude_requiring_lot', 1
        )[1].split('def _aps_source_warehouse', 1)[0]
        self.assertIn('production.advanced_plan_id', method)
        self.assertIn('not self.product_id.is_storable', method)
        self.assertIn('return super()._exclude_requiring_lot()', method)

    def test_component_lot_helpers_ignore_nonstockable(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_lines.py').read_text()
        self.assertIn('not self.product_id.is_storable', source)

    def test_native_submo_lot_sync_only_uses_storable_products(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'stock_rule.py').read_text()
        self.assertIn('component.product_id.is_storable', source)
