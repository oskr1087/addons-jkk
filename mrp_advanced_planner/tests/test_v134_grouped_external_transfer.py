# -*- coding: utf-8 -*-

from pathlib import Path
import unittest


class TestV134GroupedExternalTransferStatic(unittest.TestCase):
    """Static regression coverage for grouped APS external transfers."""

    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]

    def test_model_keeps_individual_and_grouped_actions(self):
        lines = (self.root / "models" / "planning_lines.py").read_text()
        plan = (self.root / "models" / "planning_plan.py").read_text()
        self.assertIn("def action_create_transfer(self):", lines)
        self.assertIn("selected_for_transfer = fields.Boolean", lines)
        self.assertIn("def action_create_selected_external_transfers(self):", plan)
        self.assertIn("len(routes) != 1", plan)
        self.assertIn("qty_by_product", plan)

    def test_view_exposes_both_transfer_flows(self):
        view = (self.root / "views" / "planning_plan_views.xml").read_text()
        self.assertIn('name="action_create_selected_external_transfers"', view)
        self.assertIn('string="Transferir seleccionados"', view)
        self.assertIn('name="selected_for_transfer"', view)
        self.assertIn('name="action_create_transfer"', view)
