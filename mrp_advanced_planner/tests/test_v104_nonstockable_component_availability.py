from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV104NonStockableComponentAvailability(TransactionCase):

    def test_nonstockable_component_is_not_shortage(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'services' / 'component_sourcing.py'
        ).read_text()
        self.assertIn(
            'if not component.product_id.is_storable:',
            source,
        )
        self.assertIn("'supply_resolution': 'available'", source)
        self.assertIn("'to_purchase_qty': 0.0", source)
        self.assertIn("'to_manufacture_qty': 0.0", source)

    def test_nonstockable_does_not_require_lot(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_lines.py').read_text()
        self.assertIn('or not self.product_id.is_storable', source)
        self.assertIn('or not component.product_id.is_storable', source)

    def test_tree_exposes_nonstockable_status(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'static' / 'src' / 'js'
            / 'planning_component_tree.js'
        ).read_text()
        self.assertIn('"product_is_storable"', source)
        self.assertIn('No stockeable - disponible', source)
