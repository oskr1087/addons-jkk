from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV113NonStockableRootMoLotGuard(TransactionCase):

    def test_nonstockable_bypass_recognizes_all_aps_mo_traces(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'lot_reservation.py').read_text()
        method = source.split(
            'def _exclude_requiring_lot', 1
        )[1].split('def _aps_source_warehouse', 1)[0]

        self.assertIn('production.advanced_plan_id', method)
        self.assertIn('production.planning_plan_line_id', method)
        self.assertIn('production.aps_component_snapshot', method)
        self.assertIn('not self.product_id.is_storable', method)
        self.assertIn('return super()._exclude_requiring_lot()', method)
