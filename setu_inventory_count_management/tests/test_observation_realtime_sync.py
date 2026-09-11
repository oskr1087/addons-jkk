# -*- coding: utf-8 -*-
from pathlib import Path

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestObservationRealtimeSync(TransactionCase):

    def test_01_scan_event_syncs_snapshot_observation_immediately(self):
        module = Path(__file__).resolve().parents[1]
        py = (module / "models/inventory_count_scan_event.py").read_text(encoding="utf-8")
        self.assertIn("_sync_snapshot_observation", py)
        self.assertIn('"has_observation": bool(observed_events)', py)
        self.assertIn('"observation_note"', py)
        self.assertIn('"recount_required": bool(observed_events)', py)

    def test_02_write_calls_snapshot_sync(self):
        module = Path(__file__).resolve().parents[1]
        py = (module / "models/inventory_count_scan_event.py").read_text(encoding="utf-8")
        self.assertIn('{"has_observation", "observation"} & set(vals)', py)
        self.assertIn("self._sync_snapshot_observation()", py)

    def test_03_resolve_domain_includes_observed_matched_lines(self):
        module = Path(__file__).resolve().parents[1]
        py = (module / "models/inventory_count_snapshot.py").read_text(encoding="utf-8")
        self.assertIn('("has_observation", "=", True)', py)
