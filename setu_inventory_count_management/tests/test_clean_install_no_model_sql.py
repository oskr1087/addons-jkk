# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

@tagged("post_install", "-at_install")
class TestCleanInstallNoModelSQL(TransactionCase):

    def test_pda_counting_has_no_init_sql_migration(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "models/pda_counting.py").read_text(encoding="utf-8")
        self.assertNotIn("def init(self):", source)
        self.assertNotIn("UPDATE setu_stock_inventory_count", source)
        self.assertNotIn("UPDATE setu_inventory_count_session", source)
