from odoo.tests.common import TransactionCase


class TestSaleForecastFields(TransactionCase):

    def test_sale_line_has_aps_forecast_fields(self):
        model = self.env['sale.order.line']
        for name in (
            'aps_forecast_qty',
            'aps_open_mo_qty',
            'aps_forecast_status',
            'aps_stock_warehouse_tooltip',
        ):
            self.assertIn(name, model._fields)

    def test_component_safe_actions_exist(self):
        model = self.env['mrp.planning.production.component']
        self.assertTrue(hasattr(model, 'action_open_edit_component_by_id'))
        self.assertTrue(hasattr(model, 'action_open_availability_by_id'))
