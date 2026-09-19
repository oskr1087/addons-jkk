# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

@tagged("post_install", "-at_install")
class TestPDAVisibleScannerInput(TransactionCase):
    def test_real_scanner_field_is_visible_and_automatic(self):
        root=Path(__file__).resolve().parents[1]
        xml=(root/"static/src/xml/pda_fast_count.xml").read_text(encoding="utf-8")
        js=(root/"static/src/js/pda_fast_count.js").read_text(encoding="utf-8")
        css=(root/"static/src/css/inventory_count_cockpit.scss").read_text(encoding="utf-8")
        self.assertIn("LECTURA DEL ESCÁNER", xml)
        self.assertIn("setu_pda_scanner_input", xml)
        self.assertIn("Procesar", xml)
        self.assertIn("submitScannerValue", js)
        self.assertIn("this.enqueueBarcode(value)", js)
        self.assertNotIn("opacity: 0 !important", css)
        self.assertNotIn("setu_pda_scanner_sink", xml)
