from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV81RouteBasedSaleManufacturingHold(TransactionCase):

    def test_no_extra_product_configuration(self):
        self.assertNotIn(
            'aps_managed_manufacturing',
            self.env['product.template']._fields,
        )

    def test_sale_launcher_scopes_aps_context(self):
        from ..models import sale_extensions
        source = Path(sale_extensions.__file__).read_text()
        self.assertIn('aps_hold_sale_mto_manufacturing=True', source)

    def test_only_manufacture_rule_is_intercepted(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'stock_rule.py').read_text()
        self.assertIn('def _run_manufacture', source)
        self.assertNotIn('def _run_buy', source)
        self.assertIn(
            "self.env.context.get('aps_hold_sale_mto_manufacturing')",
            source,
        )
