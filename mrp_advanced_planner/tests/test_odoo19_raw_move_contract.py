from pathlib import Path

from odoo.tests.common import TransactionCase


class TestOdoo19RawMoveContract(TransactionCase):

    def test_aps_builder_uses_native_move_value_builder(self):
        from ..models import mrp_extensions
        source = Path(mrp_extensions.__file__).read_text()
        self.assertIn('self._get_move_raw_values(', source)
        self.assertIn("move_vals.update({", source)
        self.assertIn("'aps_planning_component_id': component.id", source)

    def test_aps_mo_skips_native_bom_raw_compute(self):
        from ..models import mrp_extensions
        source = Path(mrp_extensions.__file__).read_text()
        self.assertIn('skip_compute_move_raw_ids=True', source)
        self.assertIn('def _aps_sync_raw_moves', source)

    def test_stock_move_keeps_snapshot_origin(self):
        move = self.env['stock.move']
        self.assertIn('aps_planning_component_id', move._fields)
