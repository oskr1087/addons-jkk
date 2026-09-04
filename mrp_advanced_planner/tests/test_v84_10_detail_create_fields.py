from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV8410DetailCreateFields(TransactionCase):

    def test_non_model_diagnostic_field_is_not_created(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'services' / 'simple_planning_engine.py'
        ).read_text()
        create_block = source.split('Detail.create([{', 1)[1].split('}])', 1)[0]
        self.assertNotIn(
            "'selected_sale_outgoing_qty'",
            create_block,
        )

    def test_shortage_formula_is_preserved(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'services' / 'simple_planning_engine.py'
        ).read_text()
        self.assertIn(
            'represented_sale_outgoing = selected_sale_outgoing[key]',
            source,
        )
        self.assertIn('- local_demand', source)
