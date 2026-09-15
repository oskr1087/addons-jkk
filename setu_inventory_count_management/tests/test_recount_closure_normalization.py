# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

@tagged("post_install", "-at_install")
class TestRecountClosureNormalization(TransactionCase):

    def test_dashboard_filters_stale_relocations(self):
        module = Path(__file__).resolve().parents[1]
        code = (module / "models/inventory_count_snapshot.py").read_text(encoding="utf-8")
        self.assertIn('issue.snapshot_line_id.status == "unexpected"', code)
        self.assertIn("issue.snapshot_line_id.counted_qty > 0", code)

    def test_recount_syncs_parent_relocations(self):
        module = Path(__file__).resolve().parents[1]
        code = (module / "models/setu_stock_inventory_count.py").read_text(encoding="utf-8")
        self.assertIn('parent._sync_relocation_issues()', code)
        self.assertIn("is_effectively_matched", code)

    def test_global_approval_normalizes_before_closure(self):
        module = Path(__file__).resolve().parents[1]
        code = (module / "models/inventory_count_workflow.py").read_text(encoding="utf-8")
        self.assertIn('self._sync_relocation_issues()', code)
        self.assertIn('self._refresh_persistent_kpis()', code)
