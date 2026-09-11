# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

@tagged("post_install", "-at_install")
class TestPendingZeroBulk(TransactionCase):
    def test_pending_zero_uses_single_sql_update(self):
        module = Path(__file__).resolve().parents[1]
        source = (module / "models/inventory_count_workflow.py").read_text(encoding="utf-8")
        method = source.split("def action_mark_pending_as_zero", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("UPDATE setu_inventory_count_snapshot_line", method)
        self.assertNotIn("CountLine.create", method)
        self.assertNotIn("for snapshot", method)
