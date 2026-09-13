from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV99NoDuplicateSnapshotOnManufacture(TransactionCase):

    def test_root_matching_does_not_compare_many2one_to_false(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'services' / 'manufacturing_snapshot.py'
        ).read_text()
        ensure = source.split('def ensure_complete', 1)[1].split(
            'def build', 1
        )[0]
        self.assertIn(
            'lambda component: not component.parent_line_id',
            ensure,
        )
        self.assertIn(
            'component.parent_line_id.id == parent.id',
            ensure,
        )
        self.assertNotIn(
            'component.parent_line_id == parent',
            ensure,
        )

    def test_bom_line_matching_is_by_id(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'services' / 'manufacturing_snapshot.py'
        ).read_text()
        ensure = source.split('def ensure_complete', 1)[1].split(
            'def build', 1
        )[0]
        self.assertIn(
            'row.source_bom_line_id.id == bl.id',
            ensure,
        )

    def test_duplicate_snapshot_is_blocked_before_mo(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        action = source.split(
            'def action_create_manufacturing', 1
        )[1].split('def _ensure_product_purchase_vendor', 1)[0]
        self.assertIn(
            '_aps_validate_no_duplicate_engineering_rows(lines)',
            action,
        )
        self.assertLess(
            action.find('_aps_validate_no_duplicate_engineering_rows(lines)'),
            action.find("self.env['mrp.production'].with_context"),
        )
