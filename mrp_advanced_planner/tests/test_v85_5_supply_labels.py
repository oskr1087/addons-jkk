from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV855SupplyLabels(TransactionCase):

    def test_parent_covered_label_is_explicit(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'static' / 'src' / 'js' /
            'planning_component_tree.js'
        ).read_text()
        self.assertIn('No abastecer - padre cubierto', source)
        self.assertNotIn('Cubierto nivel superior', source)

    def test_zero_effective_requirement_does_not_request_lot(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'static' / 'src' / 'js' /
            'planning_component_tree.js'
        ).read_text()
        self.assertIn('No requiere lote', source)
        self.assertNotIn('Sin reserva requerida', source)
