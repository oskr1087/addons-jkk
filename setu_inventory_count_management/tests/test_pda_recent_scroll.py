# -*- coding: utf-8 -*-
from pathlib import Path

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestPDARecentScroll(TransactionCase):

    def test_scanned_products_have_internal_scroll(self):
        module = Path(__file__).resolve().parents[1]
        css = (
            module / "static/src/css/barcode.scss"
        ).read_text(encoding="utf-8")

        self.assertIn(".setu_pda_mobile_recent {", css)
        self.assertIn("max-height: 360px;", css)
        self.assertIn("overflow-y: auto;", css)
        self.assertIn("-webkit-overflow-scrolling: touch;", css)
        self.assertIn("position: sticky;", css)
