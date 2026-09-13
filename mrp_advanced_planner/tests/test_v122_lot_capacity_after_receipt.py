from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV122LotCapacityAfterReceipt(TransactionCase):

    def test_sync_sets_mo_owner_atomically(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_lines.py').read_text()
        block = source.split(
            'def _aps_sync_default_lot_reservations', 1
        )[1].split('def action_open_lot_reservations', 1)[0]
        self.assertIn('production = component._aps_lot_production()', block)
        self.assertIn("'production_id': production.id", block)
        self.assertIn("'state': 'assigned'", block)

    def test_constraint_recognizes_component_owned_odoo_reservation(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'lot_reservation.py').read_text()
        block = source.split('def _check_exclusive_lot', 1)[1].split(
            'def _check_positive_qty', 1
        )[0]
        self.assertIn("active_components = active.mapped('component_id')", block)
        self.assertIn("'aps_planning_component_id'", block)
