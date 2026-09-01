from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV68SaleUnifiedAvailability(TransactionCase):

    def test_sale_line_has_unified_status_payload(self):
        model = self.env['sale.order.line']
        self.assertIn('aps_forecast_status', model._fields)
        self.assertIn('aps_stock_warehouse_tooltip', model._fields)

    def test_sale_view_uses_single_availability_widget(self):
        module_root = Path(__file__).parents[1]
        source = (module_root / 'views' / 'sale_order_views.xml').read_text()
        self.assertIn('widget="planning_sale_availability"', source)
        self.assertNotIn('string="Pronóstico"\\n                       widget="planning_stock_tooltip"', source)
        self.assertNotIn('string="En fabricación"\\n                       readonly="1"\\n                       optional="show"', source)

    def test_payload_contains_supply_sources(self):
        from ..models import sale_extensions
        source = Path(sale_extensions.__file__).read_text()
        for token in (
            "'open_mo': open_mo",
            "'open_po': open_po",
            "'transfer_qty': transfer_qty",
            "'planned_qty': planned_qty",
            "'coverage': coverage",
            "'shortage': shortage",
        ):
            self.assertIn(token, source)
