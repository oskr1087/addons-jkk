# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

@tagged("post_install", "-at_install")
class TestFastSynchronousMethodology(TransactionCase):

    def test_01_pending_zero_is_direct_sql(self):
        module = Path(__file__).resolve().parents[1]
        source = (module / "models/inventory_count_workflow.py").read_text(encoding="utf-8")
        method = source.split("def action_mark_pending_as_zero", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("UPDATE setu_inventory_count_snapshot_line", method)
        self.assertNotIn("_queue_background_inventory_job", method)

    def test_02_sync_is_direct(self):
        module = Path(__file__).resolve().parents[1]
        source = (module / "models/inventory_count_snapshot.py").read_text(encoding="utf-8")
        self.assertIn("def action_sync_sessions_fast", source)
        self.assertIn("_refresh_from_session_lines_bulk", source)

    def test_03_pda_finalize_is_direct(self):
        module = Path(__file__).resolve().parents[1]
        source = (module / "models/pda_counting.py").read_text(encoding="utf-8")
        self.assertIn("_finalize_pda_session_fast()", source)
        self.assertNotIn("'finalize_session'", source)

    def test_04_single_session_validation_remains(self):
        module = Path(__file__).resolve().parents[1]
        source = (module / "models/pda_counting.py").read_text(encoding="utf-8")
        self.assertIn("_validate_single_session_locations_before_finish", source)
