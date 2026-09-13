from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV131ChildOwnerBeforeConfirm(TransactionCase):

    def test_child_lot_owner_is_set_before_confirm(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'stock_rule.py').read_text()

        method = source.split(
            'def _aps_enrich_and_confirm_native_submos', 1
        )[1].split('def _run_manufacture', 1)[0]

        owner_pos = method.index("'production_id': mo.id")
        confirm_pos = method.index("if mo.state == 'draft':")
        self.assertLess(owner_pos, confirm_pos)

    def test_child_direct_components_exist_before_confirm(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'stock_rule.py').read_text()

        method = source.split(
            'def _aps_enrich_and_confirm_native_submos', 1
        )[1].split('def _run_manufacture', 1)[0]

        self.assertIn(
            "direct_components = mo._aps_snapshot_components()",
            method,
        )
