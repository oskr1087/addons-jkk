# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

@tagged("post_install", "-at_install")
class TestActionStateMatrix(TransactionCase):
    def test_action_flags_exist(self):
        Count = self.env["setu.stock.inventory.count"]
        for name in ("can_review_actions", "can_send_to_recount",
                     "can_manage_relocations", "can_view_financial_preview"):
            self.assertIn(name, Count._fields)

    def test_review_actions_have_rpc_guard(self):
        module = Path(__file__).resolve().parents[1]
        code = (module / "models/inventory_count_workflow.py").read_text(encoding="utf-8")
        self.assertIn("def _ensure_review_action_state", code)
        self.assertIn("El conteo está cerrado", code)

    def test_closed_review_toolbar_hidden(self):
        module = Path(__file__).resolve().parents[1]
        view = (module / "views/inventory_count_snapshot_views.xml").read_text(encoding="utf-8")
        self.assertIn('invisible="not can_review_actions"', view)
        self.assertIn('invisible="not can_send_to_recount"', view)
        self.assertIn('readonly="not parent.can_review_actions"', view)
