# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

@tagged("post_install", "-at_install")
class TestReviewApproveAction(TransactionCase):

    def test_approve_review_action_exists(self):
        module = Path(__file__).resolve().parents[1]
        py = (module / "models/inventory_count_workflow.py").read_text(encoding="utf-8")
        xml = (module / "views/inventory_count_snapshot_views.xml").read_text(encoding="utf-8")
        self.assertIn("def action_review_selected_approve", py)
        self.assertIn('"review_decision": "resolved"', py)
        self.assertIn('"recount_required": False', py)
        self.assertIn('name="action_review_selected_approve"', xml)
        self.assertIn('string="Aprobar revisión"', xml)
