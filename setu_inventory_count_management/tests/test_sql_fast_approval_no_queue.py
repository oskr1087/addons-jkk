# -*- coding: utf-8 -*-
from pathlib import Path

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSQLFastApprovalNoQueue(TransactionCase):

    def test_01_accept_uses_sql_not_per_snapshot_materialization(self):
        module = Path(__file__).resolve().parents[1]
        src = (module / "models/inventory_count_workflow.py").read_text(encoding="utf-8")
        method = src.split("def action_accept_adjustment_candidates", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("UPDATE", method)
        self.assertNotIn("_ensure_count_line_for_snapshot_adjustment", method)
        self.assertNotIn("for snapshot_line in candidates", method)

    def test_02_approval_creates_adjustment_from_snapshot(self):
        module = Path(__file__).resolve().parents[1]
        src = (module / "models/inventory_count_workflow.py").read_text(encoding="utf-8")
        self.assertIn("_create_inventory_adj_from_snapshot_fast", src)
        self.assertIn("InventoryLine.with_context", src)
        self.assertIn(".create(vals_list)", src)

    def test_03_queue_helper_does_not_create_jobs(self):
        module = Path(__file__).resolve().parents[1]
        src = (module / "models/inventory_count_background_job.py").read_text(encoding="utf-8")
        method = src.split("def _queue_background_inventory_job", 1)[1].split("\n    def ", 1)[0]
        self.assertNotIn("Job.create", method)
        self.assertIn("no crea nuevas colas", method)

    def test_04_old_cron_is_inactive(self):
        module = Path(__file__).resolve().parents[1]
        xml = (module / "data/ir_cron.xml").read_text(encoding="utf-8")
        block = xml.split('id="ir_cron_inventory_count_background_jobs"', 1)[1].split("</record>", 1)[0]
        self.assertIn('<field name="active">False</field>', block)
