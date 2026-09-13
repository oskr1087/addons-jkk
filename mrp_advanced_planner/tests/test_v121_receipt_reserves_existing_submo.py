from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV121ReceiptReservesExistingSubMo(TransactionCase):

    def test_done_receipt_reassigns_active_aps_mos(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'lot_reservation.py').read_text()
        method = source.split(
            'def _aps_reassign_received_material_to_productions', 1
        )[1].split('def button_validate', 1)[0]

        self.assertIn("('advanced_plan_id', '!=', False)", method)
        self.assertIn("('move_raw_ids.product_id', 'in', received_products.ids)", method)
        self.assertIn("production.action_assign()", method)
        self.assertIn("._action_assign()", method)

    def test_receipt_syncs_tracked_lots_after_physical_reservation(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'lot_reservation.py').read_text()
        method = source.split(
            'def _aps_reassign_received_material_to_productions', 1
        )[1].split('def button_validate', 1)[0]

        self.assertIn("component.product_id.is_storable", method)
        self.assertIn("component.product_id.tracking != 'none'", method)
        self.assertIn("_aps_sync_default_lot_reservations()", method)

    def test_manual_check_availability_also_syncs_aps_lots(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'mrp_extensions.py').read_text()
        method = source.split(
            'def action_assign(self):', 1
        )[1].split('def _aps_validate_lot_reservation_coverage', 1)[0]

        self.assertIn('result = super().action_assign()', method)
        self.assertIn('_aps_sync_default_lot_reservations()', method)
