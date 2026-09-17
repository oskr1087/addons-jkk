# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

@tagged("post_install", "-at_install")
class TestPDARealScannerOnly(TransactionCase):
    def test_simulator_is_not_rendered(self):
        root = Path(__file__).resolve().parents[1]
        xml = (root / "static/src/xml/pda_fast_count.xml").read_text(encoding="utf-8")
        self.assertNotIn("SIMULAR LECTURA", xml)
        self.assertNotIn("SIMULAR UBICACIÓN", xml)
        self.assertNotIn("setu_pda_mobile_simulator", xml)
        self.assertNotIn("processManualBarcode", xml)

    def test_real_barcode_bus_is_active(self):
        root = Path(__file__).resolve().parents[1]
        js = (root / "static/src/js/pda_fast_count.js").read_text(encoding="utf-8")
        self.assertIn('useBus(this.barcode.bus, "barcode_scanned"', js)
        self.assertIn("this.enqueueBarcode(barcode)", js)
        self.assertIn('"pda_fast_scan"', js)
        self.assertNotIn("manualBarcode", js)
