# -*- coding: utf-8 -*-
from pathlib import Path

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestPDAContextualSimulator(TransactionCase):

    def test_01_clear_location_method_exists(self):
        self.assertTrue(
            hasattr(
                self.env["setu.inventory.count.session"],
                "pda_fast_clear_location",
            )
        )

    def test_02_template_has_contextual_location_placeholder(self):
        module_path = Path(__file__).resolve().parents[1]
        template = (
            module_path / "static/src/xml/pda_fast_count.xml"
        ).read_text(encoding="utf-8")

        self.assertIn("Simular lectura de ubicación", template)
        self.assertIn("Código de ubicación", template)
        self.assertIn("Artículo / Lote / Cantidad", template)
        self.assertIn("Cambiar ubicación", template)
        self.assertIn('t-on-click="changeLocation"', template)

    def test_03_js_exposes_change_location(self):
        module_path = Path(__file__).resolve().parents[1]
        javascript = (
            module_path / "static/src/js/pda_fast_count.js"
        ).read_text(encoding="utf-8")

        self.assertIn("async changeLocation()", javascript)
        self.assertIn('pda_fast_clear_location', javascript)
