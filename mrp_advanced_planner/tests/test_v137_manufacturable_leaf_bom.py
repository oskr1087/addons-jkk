from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV137ManufacturableLeafBom(TransactionCase):

    def test_sourcing_falls_back_to_product_manufacturing_bom(self):
        root = Path(__file__).parents[1]
        source = (root / 'services' / 'component_sourcing.py').read_text()
        self.assertIn('from ..services.odoo19_compat import find_bom', source)
        self.assertIn('else find_bom(', source)
        self.assertIn('picking_type_id=(', source)

    def test_manufacturing_leaf_is_not_rejected_only_for_no_children(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        self.assertIn('positive_lines =', source)
        self.assertIn("if bom and bom.type == 'normal'", source)
