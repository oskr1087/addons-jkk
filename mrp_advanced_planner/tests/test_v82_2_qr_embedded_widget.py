from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV822QrEmbeddedWidget(TransactionCase):

    def test_qr_uses_qweb_barcode_widget(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'reports' / 'stock_lot_qr_templates.xml'
        ).read_text()
        self.assertIn("'widget': 'barcode'", source)
        self.assertIn("'symbology': 'QR'", source)
        self.assertIn('t-field="lot.name"', source)
        self.assertNotIn(
            't-att-src="lot._aps_pda_qr_url',
            source,
        )
