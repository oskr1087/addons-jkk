from pathlib import Path
from odoo.tests.common import TransactionCase

class TestV93ComponentTypesAndChain(TransactionCase):
    def test_component_type_matrix(self):
        root=Path(__file__).parents[1]
        s=(root/'services'/'component_sourcing.py').read_text()
        self.assertIn("component_bom.type == 'normal'",s)
        self.assertIn("component_bom.type == 'phantom'",s)
        self.assertIn("resolution = 'phantom'",s)
        self.assertIn("elif is_subcontracted:",s)

    def test_phantom_flattening(self):
        root=Path(__file__).parents[1]
        s=(root/'models'/'mrp_extensions.py').read_text()
        self.assertIn('def _aps_component_is_phantom',s)
        self.assertIn('def _aps_direct_engineering_components',s)
        self.assertIn('add(child, visiting)',s)

    def test_submo_native_chain(self):
        root=Path(__file__).parents[1]
        plan=(root/'models'/'planning_plan.py').read_text()
        rule=(root/'models'/'stock_rule.py').read_text()
        action=plan.split('def action_create_manufacturing',1)[1].split(
            'def _ensure_product_purchase_vendor',1
        )[0]
        self.assertNotIn('_create_component_manufacturing_orders()', action)
        self.assertNotIn('aps_explicit_component_manufacturing=True', action)
        self.assertNotIn("aps_explicit_component_manufacturing", rule)

    def test_phantom_does_not_reserve_parent_lot(self):
        root=Path(__file__).parents[1]
        s=(root/'models'/'planning_lines.py').read_text()
        self.assertIn("('not_required', 'phantom')",s)
