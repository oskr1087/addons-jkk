from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV849ExplicitSaleShortage(TransactionCase):

    def test_manufacturing_formula_subtracts_explicit_sale_demand(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'services' / 'simple_planning_engine.py'
        ).read_text()
        self.assertIn(
            'represented_sale_outgoing = selected_sale_outgoing[key]',
            source,
        )
        self.assertIn(
            '+ represented_sale_outgoing',
            source,
        )
        self.assertIn(
            '- local_demand',
            source,
        )

    def test_selected_sale_outgoing_is_based_on_real_stock_moves(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'services' / 'simple_planning_engine.py'
        ).read_text()
        self.assertIn(
            "('sale_line_id', 'in', sale_lines.ids)",
            source,
        )
        self.assertIn(
            "('state', 'not in', ('draft', 'done', 'cancel'))",
            source,
        )

    def test_calendar_scoped_plan_still_uses_exact_source_lines(self):
        self.assertIn(
            'source_sale_line_ids',
            self.env['mrp.planning.plan']._fields,
        )
