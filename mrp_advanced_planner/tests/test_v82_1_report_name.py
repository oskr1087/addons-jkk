from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV821ReportName(TransactionCase):

    def test_print_report_name_does_not_use_objects(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'reports' / 'stock_lot_qr_report.xml'
        ).read_text()
        self.assertNotIn('len(objects)', source)
        self.assertNotIn('objects)', source)
        self.assertIn('object.name', source)
