from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV8412LotPhysicalVisibility(TransactionCase):

    def test_component_exposes_physical_lot_metrics(self):
        model = self.env['mrp.planning.production.component']
        self.assertIn('physical_lot_available_qty', model._fields)
        self.assertIn('physical_lot_candidate_count', model._fields)

    def test_tree_distinguishes_supply_shortage_from_lot_pending(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'static' / 'src' / 'xml' /
            'planning_component_tree.xml'
        ).read_text()
        self.assertIn('Faltante abastecimiento', source)
        self.assertIn('Pend. lote', source)
        self.assertIn('pending_lot_qty', source)

    def test_popup_warns_when_forecast_exists_without_physical_lots(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'views' / 'planning_component_views.xml'
        ).read_text()
        self.assertIn(
            'actualmente no existe',
            source,
        )
        self.assertIn(
            'physical_lot_candidate_count',
            source,
        )
