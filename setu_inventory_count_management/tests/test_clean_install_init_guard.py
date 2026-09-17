# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

@tagged("post_install", "-at_install")
class TestCleanInstallInitGuard(TransactionCase):

    def test_pda_counting_init_checks_table_before_update(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "models/pda_counting.py").read_text(encoding="utf-8")
        start = source.index("    def init(self):")
        chunk = source[start:start + 1800]
        self.assertIn("SELECT to_regclass", chunk)
        self.assertIn("setu_stock_inventory_count", chunk)
        self.assertIn("if not self.env.cr.fetchone()[0]:", chunk)
        self.assertIn("return", chunk)
