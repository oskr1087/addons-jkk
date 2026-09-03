from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV82StockLotQrReport(TransactionCase):

    def test_stock_lot_has_pda_qr_helpers(self):
        lot = self.env['stock.lot']
        self.assertTrue(hasattr(lot, '_aps_pda_qr_payload'))
        self.assertTrue(hasattr(lot, '_aps_pda_qr_url'))

    def test_qr_payload_is_exact_lot_name(self):
        product = self.env['product.product'].create({
            'name': 'APS QR Test',
            'is_storable': True,
            'tracking': 'lot',
        })
        lot = self.env['stock.lot'].create({
            'name': 'LOT/APS/0001',
            'product_id': product.id,
        })
        self.assertEqual(lot._aps_pda_qr_payload(), 'LOT/APS/0001')
        self.assertIn('barcode_type=QR', lot._aps_pda_qr_url())
        self.assertIn('LOT%2FAPS%2F0001', lot._aps_pda_qr_url())

    def test_report_is_bound_to_stock_lot(self):
        report = self.env.ref(
            'mrp_advanced_planner.action_report_stock_lot_qr_pda'
        )
        self.assertEqual(report.model, 'stock.lot')
        self.assertEqual(report.report_type, 'qweb-pdf')

    def test_template_is_eight_labels_per_page(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'reports' / 'stock_lot_qr_templates.xml'
        ).read_text()
        self.assertIn('range(0, len(docs), 8)', source)
        self.assertIn('range(0, 8, 2)', source)
        self.assertIn('[0, 1]', source)
