from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV114Odoo19ExcludeRequiringLotSemantics(TransactionCase):

    def test_aps_nonstockable_returns_false(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'lot_reservation.py').read_text()
        method = source.split(
            'def _exclude_requiring_lot', 1
        )[1].split('def _aps_source_warehouse', 1)[0]

        self.assertIn('not self.product_id.is_storable', method)
        self.assertIn('return False', method)
        self.assertIn('return super()._exclude_requiring_lot()', method)

    def test_comment_documents_odoo19_inverted_semantics(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'lot_reservation.py').read_text()
        self.assertIn(
            'if not ml._exclude_requiring_lot()',
            source,
        )
