from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV123PurchaseSupplyCommitment(TransactionCase):

    def test_component_sourcing_subtracts_other_mo_waiting_raw_demand(self):
        root = Path(__file__).parents[1]
        source = (root / 'services' / 'component_sourcing.py').read_text()
        self.assertIn(
            'def _other_mo_unreserved_raw_demand',
            source,
        )
        self.assertIn(
            "- other_mo_unreserved[key]",
            source,
        )

    def test_po_confirmation_links_receipt_to_exact_component_moves(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'mrp_extensions.py').read_text()
        method = source.split(
            'def _aps_link_purchase_moves_to_component_demand', 1
        )[1].split('def action_open_planning_sale_orders', 1)[0]
        self.assertIn("'move_dest_ids':", method)
        self.assertIn('generated_purchase_plan_line_id', method)
        self.assertIn('component._aps_lot_production()', method)

    def test_receipt_does_not_assign_every_aps_mo(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'lot_reservation.py').read_text()
        method = source.split(
            'def _aps_reassign_received_material_to_productions', 1
        )[1].split('def button_validate', 1)[0]
        self.assertNotIn(
            "('advanced_plan_id', '!=', False)",
            method,
        )
        self.assertIn('move.move_dest_ids', method)
        self.assertIn('source_manufacturing_plan_id', method)
