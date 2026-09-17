# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

@tagged("post_install", "-at_install")
class TestPDARefreshPersistence(TransactionCase):

    def test_pda_session_survives_browser_refresh(self):
        root = Path(__file__).resolve().parents[1]
        js = (root / "static/src/js/pda_fast_count.js").read_text(encoding="utf-8")
        self.assertIn("window.sessionStorage.getItem", js)
        self.assertIn("setu_inventory_count_pda_session_id", js)
        self.assertIn("actionSessionId || storedSessionId", js)
        self.assertIn("window.sessionStorage.removeItem", js)

    def test_observation_does_not_claim_automatic_recount(self):
        root = Path(__file__).resolve().parents[1]
        xml = (root / "static/src/xml/pda_fast_count.xml").read_text(encoding="utf-8")
        self.assertNotIn("Este producto irá a reconteo", xml)
        self.assertIn("pendiente de revisión por el controlador", xml)
