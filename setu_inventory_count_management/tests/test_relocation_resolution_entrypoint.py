# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

@tagged("post_install", "-at_install")
class TestRelocationResolutionEntrypoint(TransactionCase):

    def test_count_has_relocation_entrypoint(self):
        module = Path(__file__).resolve().parents[1]
        code = (module / "models/inventory_count_location_flow.py").read_text(encoding="utf-8")
        self.assertIn("def action_open_relocation_issues", code)
        self.assertIn('"res_model": "setu.inventory.count.relocation.issue"', code)
        self.assertIn('"view_mode": "list,form"', code)

    def test_guided_banner_has_resolve_button(self):
        module = Path(__file__).resolve().parents[1]
        xml = (module / "views/inventory_count_snapshot_views.xml").read_text(encoding="utf-8")
        self.assertIn('name="action_open_relocation_issues"', xml)
        self.assertIn('string="Resolver ubicaciones"', xml)
        self.assertIn('invisible="not can_manage_relocations"', xml)

    def test_relocation_has_operational_views(self):
        module = Path(__file__).resolve().parents[1]
        xml = (module / "views/inventory_count_location_flow_views.xml").read_text(encoding="utf-8")
        self.assertIn('id="view_setu_inventory_count_relocation_issue_list"', xml)
        self.assertIn('id="view_setu_inventory_count_relocation_issue_form"', xml)
        self.assertIn('string="Generar traslado interno"', xml)
        self.assertIn('name="source_location_id"', xml)
        self.assertIn('name="quantity_to_move"', xml)
