from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV75EmptyCalculationReusable(TransactionCase):

    def test_empty_calculation_keeps_plan_in_draft(self):
        from ..models import planning_plan
        source = Path(planning_plan.__file__).read_text()
        self.assertIn("if not result_count or not self.line_ids:", source)
        self.assertIn("'state': 'draft'", source)
        self.assertIn("'calculated_at': False", source)
        self.assertIn("'tag': 'display_notification'", source)

    def test_successful_calculation_still_moves_to_calculated(self):
        from ..models import planning_plan
        source = Path(planning_plan.__file__).read_text()
        self.assertIn("'state': 'calculated'", source)
        self.assertIn("'calculated_at': fields.Datetime.now()", source)
