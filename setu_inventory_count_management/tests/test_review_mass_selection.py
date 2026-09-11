# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestReviewMassSelection(TransactionCase):

    def test_mass_selection_actions_exist(self):
        module = Path(__file__).resolve().parents[1]
        py = (module / "models/inventory_count_workflow.py").read_text(encoding="utf-8")
        xml = (module / "views/inventory_count_snapshot_views.xml").read_text(encoding="utf-8")

        self.assertIn("def action_review_select_all", py)
        self.assertIn("def action_review_unselect_all", py)
        self.assertIn('name="action_review_select_all"', xml)
        self.assertIn('string="Seleccionar todos"', xml)
        self.assertIn('name="action_review_unselect_all"', xml)
        self.assertIn('string="Quitar selección"', xml)

    def test_selected_review_lines_only_pending(self):
        module = Path(__file__).resolve().parents[1]
        py = (module / "models/inventory_count_workflow.py").read_text(encoding="utf-8")
        start = py.index("def _selected_review_lines")
        end = py.index("def action_review_select_all", start)
        block = py[start:end]
        self.assertIn('line.review_decision == "pending"', block)
