# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestRecountFinalizeFlow(TransactionCase):

    def test_finalize_recount_action_exists(self):
        module = Path(__file__).resolve().parents[1]
        workflow = (module / "models/inventory_count_workflow.py").read_text(encoding="utf-8")
        view = (module / "views/inventory_count_snapshot_views.xml").read_text(encoding="utf-8")

        self.assertIn("def action_finalize_recount", workflow)
        self.assertIn('name="action_finalize_recount"', view)
        self.assertIn('string="Finalizar reconteo"', view)
        self.assertIn("session._finalize_pda_session_fast()", workflow)
        self.assertIn('"recount_finalized": True', workflow)

    def test_recount_decision_is_transferred_to_parent(self):
        module = Path(__file__).resolve().parents[1]
        py = (module / "models/setu_stock_inventory_count.py").read_text(encoding="utf-8")

        self.assertIn('child.review_decision in ("adjust", "discard")', py)
        self.assertIn('"review_decision": parent_decision', py)
        self.assertIn('"recount_required": False', py)
        self.assertIn('"review_selected": False', py)
