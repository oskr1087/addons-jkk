# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestRecountWarehouseLockRegression(TransactionCase):

    def test_recount_uses_root_lock_owner(self):
        module = Path(__file__).resolve().parents[1]
        py = (module / "models/warehouse_count_lock.py").read_text(encoding="utf-8")
        self.assertIn("def _warehouse_lock_owner(self):", py)
        self.assertIn("return self.root_count_id or self.count_id or self", py)
        self.assertIn('Lock.search([("count_id", "=", owner.id)]', py)
        self.assertIn('"count_id": owner.id', py)

    def test_observation_sync_does_not_force_recount(self):
        module = Path(__file__).resolve().parents[1]
        py = (module / "models/inventory_count_workflow.py").read_text(encoding="utf-8")
        start = py.index("def _sync_observation_recount_flags")
        end = py.index("def _prepare_observed_count_lines_for_recount", start)
        block = py[start:end]
        self.assertIn('"has_observation": True', block)
        self.assertNotIn('"recount_required": True', block)
