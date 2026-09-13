from pathlib import Path
from odoo.tests.common import TransactionCase

class TestV94LotReassignmentBetweenMos(TransactionCase):
    def test_reassignment_is_quantity_based_and_preserves_history(self):
        root=Path(__file__).parents[1]
        s=(root/'wizard'/'lot_reassignment_wizard.py').read_text()
        self.assertIn('take = min(donor.reserved_qty, needed)', s)
        self.assertIn("'state': 'released'", s)
        self.assertIn("'production_id': self.production_id.id", s)

    def test_consumed_lot_is_not_donor(self):
        root=Path(__file__).parents[1]
        s=(root/'wizard'/'lot_reassignment_wizard.py').read_text()
        self.assertIn('_aps_consumed_qty_for_lot', s)
        self.assertIn("donor_production.state in ('done', 'cancel')", s)

    def test_no_direct_quant_write(self):
        root=Path(__file__).parents[1]
        s=(root/'wizard'/'lot_reassignment_wizard.py').read_text()
        self.assertNotIn("stock.quant", s)
        self.assertIn('moves._do_unreserve()', s)
        self.assertIn('moves._action_assign()', s)

    def test_mo_has_reassignment_entry_point(self):
        root=Path(__file__).parents[1]
        s=(root/'models'/'mrp_extensions.py').read_text()
        self.assertIn('def action_open_aps_lot_reassignment', s)
