from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV138RecalculateFabricateRecursiveIdentity(TransactionCase):

    def test_native_child_syncs_snapshot_before_confirm(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'stock_rule.py').read_text()
        self.assertIn("mo.state == 'draft'", source)
        self.assertIn('._aps_sync_raw_moves()', source)

    def test_recalculate_repairs_legacy_raw_move_identity(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        self.assertIn('mo._aps_adopt_existing_raw_moves()', source)
        self.assertIn('ManufacturingSnapshotBuilder(self).ensure_complete(snapshot_lines)', source)

    def test_existing_raw_moves_can_be_adopted_by_bom_line(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'mrp_extensions.py').read_text()
        self.assertIn('def _aps_adopt_existing_raw_moves(self):', source)
        self.assertIn('move.bom_line_id == component.source_bom_line_id', source)
        self.assertIn("'aps_planning_component_id': component.id", source)
