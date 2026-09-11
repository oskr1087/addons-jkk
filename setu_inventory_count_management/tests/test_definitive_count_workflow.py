# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestDefinitiveCountWorkflow(TransactionCase):

    def test_review_is_unified(self):
        module = Path(__file__).resolve().parents[1]
        py = (module / "models/inventory_count_workflow.py").read_text(encoding="utf-8")
        xml = (module / "views/inventory_count_snapshot_views.xml").read_text(encoding="utf-8")
        self.assertIn("review_required", py)
        self.assertIn("review_reason", py)
        self.assertIn("review_decision", py)
        self.assertIn("Para revisión", xml)

    def test_review_multiselect_actions(self):
        module = Path(__file__).resolve().parents[1]
        py = (module / "models/inventory_count_workflow.py").read_text(encoding="utf-8")
        self.assertIn("action_review_selected_recount", py)
        self.assertIn("action_review_selected_adjust", py)
        self.assertIn("action_review_selected_discard", py)

    def test_missing_is_closed_automatically(self):
        module = Path(__file__).resolve().parents[1]
        py = (module / "models/inventory_count_snapshot.py").read_text(encoding="utf-8")
        self.assertIn("_close_unscanned_as_zero_fast", py)
        self.assertIn("status = 'zero'", py)

    def test_bus_realtime_events(self):
        module = Path(__file__).resolve().parents[1]
        py = (module / "models/inventory_count_scan_event.py").read_text(encoding="utf-8")
        js = (module / "static/src/js/count_backend_dashboard.js").read_text(encoding="utf-8")
        self.assertIn("_sendone", py)
        self.assertIn("COUNT_SCANNED", py)
        self.assertIn("bus_service", js)
        self.assertIn("addChannel", js)

    def test_global_approval_requires_review_decisions(self):
        module = Path(__file__).resolve().parents[1]
        py = (module / "models/inventory_count_workflow.py").read_text(encoding="utf-8")
        self.assertIn("action_approve_reviewed_count", py)
        self.assertIn("_validate_review_decisions", py)
