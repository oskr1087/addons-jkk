from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV107FreezeSourcingAfterManufacture(TransactionCase):

    def test_native_submo_does_not_refresh_sourcing(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'stock_rule.py').read_text()
        method = source.split(
            'def _aps_enrich_and_confirm_native_submos', 1
        )[1].split('def _run_manufacture', 1)[0]
        self.assertNotIn('_refresh_component_sourcing()', method)
        self.assertIn('sourcing decision remains frozen', method)

    def test_lot_sync_is_still_kept(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'stock_rule.py').read_text()
        method = source.split(
            'def _aps_enrich_and_confirm_native_submos', 1
        )[1].split('def _run_manufacture', 1)[0]
        self.assertIn('._aps_sync_default_lot_reservations()', method)
        self.assertIn("'production_id': mo.id", method)

    def test_purchase_plan_explains_consolidation(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        self.assertIn(
            'APS consolida sus cantidades en una sola línea de compra',
            source,
        )
