# -*- coding: utf-8 -*-
from pathlib import Path

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestObservationViewsVisible(TransactionCase):

    def test_01_session_lines_show_observations(self):
        module_path = Path(__file__).resolve().parents[1]
        xml = (
            module_path / "views/setu_inventory_count_session_views.xml"
        ).read_text(encoding="utf-8")
        self.assertIn('name="has_observation"', xml)
        self.assertIn('name="observation"', xml)
        self.assertIn("Tiene observaciones", xml)

    def test_02_dashboard_shows_observation_column(self):
        module_path = Path(__file__).resolve().parents[1]
        xml = (
            module_path / "static/src/xml/count_backend_dashboard.xml"
        ).read_text(encoding="utf-8")
        self.assertIn(">Observación<", xml)
        self.assertIn("row.has_observation", xml)
        self.assertIn("row.observation", xml)

    def test_03_dashboard_backend_exposes_observation(self):
        module_path = Path(__file__).resolve().parents[1]
        py = (
            module_path / "models/count_backend_dashboard.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"has_observation"', py)
        self.assertIn('"observation"', py)
