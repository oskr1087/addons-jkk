from pathlib import Path
from odoo.tests.common import TransactionCase

class TestV108DateEndLocalTimezone(TransactionCase):
    def test_local_timezone_for_create_date(self):
        s=(Path(__file__).parents[1]/'models'/'planning_plan.py').read_text()
        self.assertIn('fields.Datetime.context_timestamp(', s)
        self.assertIn('creation_date = local_created_dt.date()', s)
        self.assertNotIn('fields.Date.to_date(plan.create_date)', s)
