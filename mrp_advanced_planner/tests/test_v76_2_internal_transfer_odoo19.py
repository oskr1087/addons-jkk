from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV762InternalTransferOdoo19(TransactionCase):

    def test_stock_move_has_no_legacy_name_field(self):
        self.assertNotIn('name', self.env['stock.move']._fields)

    def test_aps_transfer_does_not_send_name_to_stock_move(self):
        from ..models import planning_lines
        source = Path(planning_lines.__file__).read_text()
        start = source.index('def action_create_transfer')
        end = source.find('\n    def ', start + 10)
        block = source[start:end if end > 0 else len(source)]
        move_start = block.index('move_vals = {')
        move_end = block.index('}', move_start)
        move_block = block[move_start:move_end]
        self.assertNotIn("'name':", move_block)
        self.assertIn("'origin':", block)
