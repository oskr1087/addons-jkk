# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSnapshotMetricsRegression(TransactionCase):

    def test_refresh_snapshot_metrics_only_uses_existing_refresh(self):
        module = Path(__file__).resolve().parents[1]
        py = (module / "models/inventory_count_snapshot.py").read_text(encoding="utf-8")
        start = py.index("def _refresh_snapshot_metrics")
        end = py.find("\n    def ", start + 4)
        block = py[start:end if end != -1 else None]
        self.assertIn("self._refresh_persistent_kpis()", block)
        self.assertNotIn("_recompute_snapshot_aggregates", block)
        self.assertNotIn("last_snapshot_update", block)

    def test_observation_does_not_force_recount(self):
        module = Path(__file__).resolve().parents[1]
        py = (module / "models/inventory_count_scan_event.py").read_text(encoding="utf-8")
        marker = "snapshot.sudo().write({"
        start = py.index(marker)
        end = py.index("})", start) + 2
        block = py[start:end]
        self.assertIn('"has_observation"', block)
        self.assertNotIn('"recount_required"', block)
