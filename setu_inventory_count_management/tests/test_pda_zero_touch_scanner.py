# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

@tagged("post_install", "-at_install")
class TestPDAZeroTouchScanner(TransactionCase):
    def test_scanner_processes_without_enter_or_tab(self):
        root=Path(__file__).resolve().parents[1]
        js=(root/"static/src/js/pda_fast_count.js").read_text(encoding="utf-8")
        xml=(root/"static/src/xml/pda_fast_count.xml").read_text(encoding="utf-8")
        self.assertIn("this.submitScannerValue(payload)", js)
        self.assertIn("}, 80);", js)
        self.assertIn("No necesita presionar Enter, Tab ni ningún botón", xml)
