# -*- coding: utf-8 -*-
from pathlib import Path

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestPDACompactLayout(TransactionCase):

    def test_simulator_is_before_recent_scans_and_qr_is_compact(self):
        module = Path(__file__).resolve().parents[1]
        xml = (
            module / "static/src/xml/pda_fast_count.xml"
        ).read_text(encoding="utf-8")
        css = (
            module / "static/src/css/barcode.scss"
        ).read_text(encoding="utf-8")

        simulator_pos = xml.index("setu_pda_mobile_simulator")
        recent_pos = xml.index("setu_pda_mobile_recent", simulator_pos)

        self.assertLess(simulator_pos, recent_pos)
        self.assertIn("SIMULAR LECTURA", xml)
        self.assertIn("ARTÍCULO/LOTE/CANTIDAD", xml)
        self.assertIn("min-height: 150px;", css)
        self.assertIn("grid-template-columns: minmax(0, 1fr) auto;", css)
