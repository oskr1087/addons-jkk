# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestControllerGuidedUX(TransactionCase):

    def test_guided_fields_exist(self):
        Count = self.env["setu.stock.inventory.count"]
        for field_name in (
            "review_pending_count",
            "adjustment_approved_count",
            "recount_review_count",
            "review_resolved_count",
            "next_action_title",
            "next_action_text",
            "can_finalize_recount",
            "recount_readiness_text",
        ):
            self.assertIn(field_name, Count._fields)

    def test_observation_is_not_a_permanent_blocker(self):
        module = Path(__file__).resolve().parents[1]
        code = (module / "models/inventory_count_snapshot.py").read_text(encoding="utf-8")
        self.assertIn('line.review_decision == "pending"', code)
        self.assertNotIn("+ len(observed_snapshots)", code)

    def test_header_buttons_follow_readiness(self):
        module = Path(__file__).resolve().parents[1]
        view = (module / "views/inventory_count_snapshot_views.xml").read_text(encoding="utf-8")
        self.assertIn('invisible="not adjustment_ready or count_id"', view)
        self.assertIn('invisible="not can_finalize_recount"', view)
        self.assertIn('string="Resolver sin ajuste"', view)
