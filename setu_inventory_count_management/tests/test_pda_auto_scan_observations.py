# -*- coding: utf-8 -*-
from pathlib import Path

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestPDAAutoScanObservations(TransactionCase):

    def test_01_pda_template_has_no_confirm_button(self):
        module_path = Path(__file__).resolve().parents[1]
        xml = (
            module_path / "static/src/xml/pda_fast_count.xml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("CONFIRMAR CANTIDAD", xml)
        self.assertNotIn('t-on-click="confirmQuantity"', xml)
        self.assertIn("Tiene observaciones", xml)

    def test_02_pda_js_has_observation_rpc(self):
        module_path = Path(__file__).resolve().parents[1]
        js = (
            module_path / "static/src/js/pda_fast_count.js"
        ).read_text(encoding="utf-8")
        self.assertNotIn("async confirmQuantity()", js)
        self.assertIn("pda_fast_set_observation", js)

    def test_03_controller_dashboard_autorefresh_and_observations(self):
        module_path = Path(__file__).resolve().parents[1]
        js = (
            module_path / "static/src/js/count_backend_dashboard.js"
        ).read_text(encoding="utf-8")
        xml = (
            module_path / "static/src/xml/count_backend_dashboard.xml"
        ).read_text(encoding="utf-8")
        self.assertIn("setInterval", js)
        self.assertIn("5000", js)
        self.assertIn("Observaciones", xml)
        self.assertIn("actualiza automáticamente cada 5 segundos", xml)

    def test_04_backend_contains_exact_duplicate_logic(self):
        module_path = Path(__file__).resolve().parents[1]
        py = (
            module_path / "models/pda_counting.py"
        ).read_text(encoding="utf-8")
        self.assertIn("_find_duplicate_qr_event", py)
        self.assertIn("event.quantity - quantity", py)
        self.assertIn("_register_enriched_qr", py)

    def test_05_observations_drive_recount(self):
        module_path = Path(__file__).resolve().parents[1]
        py = (
            module_path / "models/inventory_count_workflow.py"
        ).read_text(encoding="utf-8")
        self.assertIn("_sync_observation_recount_flags", py)
        self.assertIn("_prepare_observed_count_lines_for_recount", py)
        self.assertIn("observed or self._snapshot_problem_lines()", py)
