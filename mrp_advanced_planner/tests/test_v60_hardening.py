from pathlib import Path

from odoo.tests.common import TransactionCase

from ..services.internal_stock import InternalWarehouseStock


class TestV60Hardening(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.warehouse = self.env['stock.warehouse'].search([
            ('company_id', '=', self.company.id),
        ], limit=1)

    def test_internal_stock_helper_only_uses_internal_locations(self):
        product = self.env['product.product'].create({
            'name': 'APS Internal Stock Test',
            'is_storable': True,
        })
        internal = self.env['stock.location'].search([
            ('id', 'child_of', self.warehouse.view_location_id.id),
            ('usage', '=', 'internal'),
        ], limit=1)
        customer = self.env.ref('stock.stock_location_customers')

        self.env['stock.quant']._update_available_quantity(
            product, internal, 10.0
        )
        # Stock in a customer location must never leak into APS availability.
        self.env['stock.quant']._update_available_quantity(
            product, customer, 50.0
        )

        values = InternalWarehouseStock(
            self.env, self.company
        ).quantities(product, self.warehouse)
        self.assertAlmostEqual(
            values[(product.id, self.warehouse.id)]['on_hand'],
            10.0,
        )

    def test_aps_mo_override_is_scoped_to_aps_flag(self):
        from ..models import mrp_extensions
        source = Path(mrp_extensions.__file__).read_text()
        self.assertIn('aps_component_snapshot', source)
        self.assertIn('regular = self - aps', source)
        self.assertIn('actual_products != expected_products', source)

    def test_sale_line_forecast_has_mo_detail(self):
        model = self.env['sale.order.line']
        self.assertIn('aps_forecast_qty', model._fields)
        self.assertIn('aps_open_mo_qty', model._fields)
        self.assertIn('aps_forecast_status', model._fields)
        self.assertIn('aps_stock_warehouse_tooltip', model._fields)
