from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV97NativeSubmanufacturing(TransactionCase):

    def test_aps_creates_only_root_mo(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        action = source.split(
            'def action_create_manufacturing', 1
        )[1].split('def _ensure_product_purchase_vendor', 1)[0]
        self.assertNotIn('_create_component_manufacturing_orders()', action)
        self.assertNotIn('aps_explicit_component_manufacturing=True', action)
        self.assertIn('mo.action_confirm()', action)

    def test_component_manufacturing_is_not_suppressed(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'stock_rule.py').read_text()
        self.assertIn("aps_hold_sale_mto_manufacturing", source)
        self.assertNotIn("aps_explicit_component_manufacturing", source)

    def test_explicit_component_generator_is_compatibility_noop(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        method = source.split(
            'def _create_component_manufacturing_orders', 1
        )[1].split('def _aps_link_manufacturing_chain', 1)[0]
        self.assertIn("return self.env['mrp.production']", method)
        self.assertNotIn('.create(vals)', method)

    def test_normal_intermediate_remains_parent_raw_component(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'mrp_extensions.py').read_text()
        self.assertIn('def _aps_component_is_phantom', source)
        self.assertIn('for row in self._aps_direct_engineering_components()', source)
        self.assertIn('add(row)', source)
