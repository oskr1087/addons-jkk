# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

@tagged("post_install", "-at_install")
class TestPDAKeyboardScanner(TransactionCase):
    def test_keyboard_wedge_fallback_exists(self):
        root = Path(__file__).resolve().parents[1]
        js = (root / "static/src/js/pda_fast_count.js").read_text(encoding="utf-8")
        self.assertIn('document.addEventListener("keydown"', js)
        self.assertIn("onPhysicalScannerKeydown", js)
        self.assertIn('event.key === "Enter" || event.key === "Tab"', js)
        self.assertIn("this.enqueueBarcode(value)", js)
        self.assertIn('useBus(this.barcode.bus, "barcode_scanned"', js)

    def test_keyboard_listener_is_removed(self):
        root = Path(__file__).resolve().parents[1]
        js = (root / "static/src/js/pda_fast_count.js").read_text(encoding="utf-8")
        self.assertIn('document.removeEventListener("keydown"', js)
