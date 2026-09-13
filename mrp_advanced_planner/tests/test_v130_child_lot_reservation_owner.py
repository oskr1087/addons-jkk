from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV130ChildLotReservationOwner(TransactionCase):

    def test_native_child_reassigns_direct_reservations_before_sync(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'stock_rule.py').read_text()

        method = source.split(
            'def _aps_enrich_and_confirm_native_submos', 1
        )[1].split('def _run_manufacture', 1)[0]

        self.assertIn('child_reservations = direct_components.mapped', method)
        self.assertIn("'production_id': mo.id", method)
        self.assertIn('._aps_sync_default_lot_reservations()', method)

        self.assertLess(
            method.index('child_reservations = direct_components.mapped'),
            method.index('._aps_sync_default_lot_reservations()'),
        )

    def test_existing_child_chain_repairs_reservation_owner(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()

        method = source.split(
            'def _aps_link_manufacturing_chain', 1
        )[1].split('def action_open_component_productions', 1)[0]

        self.assertIn("child_mo._aps_snapshot_components()", method)
        self.assertIn("'production_id': child_mo.id", method)
