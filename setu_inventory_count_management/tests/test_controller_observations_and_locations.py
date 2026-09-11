# -*- coding: utf-8 -*-
from pathlib import Path

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestControllerObservationsAndLocations(TransactionCase):

    def test_01_all_and_resolve_views_show_observations(self):
        module = Path(__file__).resolve().parents[1]
        xml = (module / "views/inventory_count_snapshot_views.xml").read_text(encoding="utf-8")
        self.assertGreaterEqual(xml.count('name="has_observation"'), 2)
        self.assertGreaterEqual(xml.count('name="observation_note"'), 2)
        self.assertIn("No previsto en ubicación", xml)

    def test_02_resolve_domain_includes_observations(self):
        module = Path(__file__).resolve().parents[1]
        py = (module / "models/inventory_count_snapshot.py").read_text(encoding="utf-8")
        self.assertIn('("has_observation", "=", True)', py)
        self.assertIn('"unexpected"', py)

    def test_03_location_progress_does_not_preload_empty_locations(self):
        module = Path(__file__).resolve().parents[1]
        py = (module / "models/inventory_count_location_flow.py").read_text(encoding="utf-8")
        self.assertIn("relevant_locations", py)
        self.assertIn("scanned_locations", py)
        self.assertIn("active_locations", py)
        self.assertNotIn("locations = count._snapshot_scope_locations()\\n            existing", py)

    def test_04_qr_syncs_unexpected_snapshot_immediately(self):
        module = Path(__file__).resolve().parents[1]
        py = (module / "models/pda_counting.py").read_text(encoding="utf-8")
        self.assertIn("_ensure_snapshot_lines_for_session_line(line)", py)
        self.assertIn("_refresh_from_session_lines()", py)
