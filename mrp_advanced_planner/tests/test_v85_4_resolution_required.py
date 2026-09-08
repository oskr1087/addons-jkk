from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV854ResolutionRequired(TransactionCase):

    def test_lot_target_does_not_fallback_to_gross_bom_qty(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_lines.py').read_text()
        self.assertIn('def _aps_effective_lot_target_qty', source)
        self.assertNotIn(
            'component.effective_required_qty or component.planned_qty',
            source,
        )

    def test_no_required_ui_is_explained(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'static' / 'src' / 'js' /
            'planning_component_tree.js'
        ).read_text()
        self.assertIn('Cubierto nivel superior', source)
        self.assertIn('Sin reserva requerida', source)

    def test_not_required_pending_is_zero_in_tree(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'static' / 'src' / 'xml' /
            'planning_component_tree.xml'
        ).read_text()
        self.assertIn(
            "row.supply_resolution === 'not_required'",
            source,
        )
