from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV125NativeSubMOProcurement(TransactionCase):

    def test_fabricable_component_launches_native_procurement(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'mrp_extensions.py').read_text()
        self.assertIn("'procure_method'] = 'make_to_order'", source)
        self.assertIn("'route_ids'] = [(6, 0, manufacture_route.ids)]", source)
        self.assertIn("'manufacture', 'move_manufacture'", source)

    def test_submo_still_created_by_stock_rule(self):
        root = Path(__file__).parents[1]
        rule = (root / 'models' / 'stock_rule.py').read_text()
        self.assertIn('result = super()._run_manufacture(procurements)', rule)
        self.assertIn('_aps_enrich_and_confirm_native_submos(procurements)', rule)
