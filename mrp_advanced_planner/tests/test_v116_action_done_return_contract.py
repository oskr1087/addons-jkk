from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV116ActionDoneReturnContract(TransactionCase):

    def test_action_done_does_not_union_none_with_recordset(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'lot_reservation.py').read_text()
        method = source.split(
            'def _action_done(self):', 1
        )[1].split('def _aps_source_warehouse', 1)[0]

        self.assertNotIn('result | aps_nonstockable', method)
        self.assertIn(
            'super(StockMoveLine, normal_lines)._action_done()',
            method,
        )
        self.assertIn('return None', method)
