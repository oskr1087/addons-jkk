# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

@tagged("post_install", "-at_install")
class TestRecountPDAEnabled(TransactionCase):

    def test_recount_creation_forces_pda(self):
        module = Path(__file__).resolve().parents[1]
        code = (module / "models/setu_stock_inventory_count.py").read_text(encoding="utf-8")
        start = code.index("def open_new_count")
        end = code.index("def action_open_user_mistake_lines", start)
        block = code[start:end]
        self.assertGreaterEqual(block.count("'use_barcode_scanner': True"), 2)

    def test_recount_is_effectively_pda_enabled(self):
        module = Path(__file__).resolve().parents[1]
        code = (module / "models/pda_counting.py").read_text(encoding="utf-8")
        self.assertIn("def _pda_scanner_enabled", code)
        self.assertIn("self.inventory_count_id.count_id", code)
        self.assertIn("if not self._pda_scanner_enabled()", code)

    def test_upgrade_backfills_existing_recounts(self):
        module = Path(__file__).resolve().parents[1]
        code = (module / "models/pda_counting.py").read_text(encoding="utf-8")
        self.assertIn("UPDATE setu_stock_inventory_count", code)
        self.assertIn("UPDATE setu_inventory_count_session AS session", code)
        self.assertIn("count.count_id IS NOT NULL", code)

    def test_recount_ux_is_identified(self):
        module = Path(__file__).resolve().parents[1]
        xml = (module / "static/src/xml/pda_fast_count.xml").read_text(encoding="utf-8")
        self.assertIn("RECONTEO PDA", xml)
        self.assertIn("Reconteo activo:", xml)
