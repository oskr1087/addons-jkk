from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV823QrPayloadCount(TransactionCase):

    def test_qr_payload_format(self):
        product = self.env['product.product'].create({
            'name': 'APS QR Count Test',
            'default_code': 'APS-CODE-01',
            'is_storable': True,
            'tracking': 'lot',
        })
        lot = self.env['stock.lot'].create({
            'name': 'LOT-0001',
            'product_id': product.id,
        })
        payload = lot._aps_pda_qr_payload()
        self.assertTrue(payload.startswith('APS-CODE-01/LOT-0001/'))
        self.assertEqual(len(payload.split('/')), 3)

    def test_report_barcode_uses_full_payload_field(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'reports' / 'stock_lot_qr_templates.xml'
        ).read_text()
        self.assertIn('t-field="lot.aps_pda_qr_value"', source)
        self.assertIn("'symbology': 'QR'", source)

    def test_payload_uses_default_code_and_quantity(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'models' / 'stock_lot_report.py'
        ).read_text()
        self.assertIn('self.product_id.default_code', source)
        self.assertIn("return '%s/%s/%.2f'", source)
        self.assertIn("('location_id.usage', '=', 'internal')", source)
