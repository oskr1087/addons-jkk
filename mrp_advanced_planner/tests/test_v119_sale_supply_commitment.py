from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV119SaleSupplyCommitment(TransactionCase):

    def test_forecast_is_not_added_again_to_open_supply(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'sale_extensions.py').read_text()
        method = source.split(
            'def _compute_aps_sale_forecast', 1
        )[1].split('def action_open_aps_availability', 1)[0]
        self.assertNotIn('coverage = net_forecast_cover + supply_cover', method)
        self.assertIn('physical_cover = min(pending, free_qty)', method)
        self.assertIn('coverage = physical_cover + own_cover + generic_cover', method)

    def test_supply_committed_to_other_sale_is_excluded(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'sale_extensions.py').read_text()
        method = source.split(
            'def _compute_aps_sale_forecast', 1
        )[1].split('def action_open_aps_availability', 1)[0]
        self.assertIn("elif commitment == 'other':", method)
        self.assertIn('other_mo += qty', method)
        self.assertIn('other_po += qty', method)
        self.assertIn("'committed_elsewhere_qty': other_mo + other_po", method)

    def test_done_transfer_is_not_double_counted(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'sale_extensions.py').read_text()
        method = source.split(
            'def _compute_aps_sale_forecast', 1
        )[1].split('def action_open_aps_availability', 1)[0]
        self.assertIn("if move.state == 'done':", method)
        self.assertIn('continue', method)

    def test_wizard_receives_status_key_and_other_commitment(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'sale_extensions.py').read_text()
        self.assertIn("'status_key': payload.get('status') or 'uncovered'", source)
        self.assertIn("'committed_elsewhere_qty':", source)
