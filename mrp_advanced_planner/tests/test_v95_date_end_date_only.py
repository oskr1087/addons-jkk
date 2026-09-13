from pathlib import Path
from odoo.tests.common import TransactionCase

class TestV95DateEndDateOnly(TransactionCase):
    def test_date_only_horizon(self):
        s=(Path(__file__).parents[1]/'models'/'planning_plan.py').read_text()
        self.assertIn('date_end = fields.Date(',s)
        self.assertNotIn('date_end = fields.Datetime(',s)
        self.assertIn('plan.date_end < creation_date',s)
        self.assertIn('def _aps_date_end_datetime',s)
        self.assertIn('fields.Datetime.end_of(',s)
