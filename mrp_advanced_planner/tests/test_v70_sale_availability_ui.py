from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV70SaleAvailabilityUI(TransactionCase):

    def test_wizard_has_summary_fields(self):
        model = self.env['mrp.planning.sale.availability.wizard']
        self.assertIn('status_key', model._fields)
        self.assertIn('coverage_percent', model._fields)
        self.assertIn('supply_total_qty', model._fields)

    def test_wizard_view_has_dashboard_sections(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'views' / 'sale_availability_wizard_views.xml'
        ).read_text()
        self.assertIn('o_aps_availability_kpis', source)
        self.assertIn('Inventario y pronóstico', source)
        self.assertIn('Abastecimiento', source)
        self.assertIn('Trazabilidad del abastecimiento', source)
