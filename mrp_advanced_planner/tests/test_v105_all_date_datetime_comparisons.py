from pathlib import Path
from odoo.tests.common import TransactionCase

class TestV105AllDateDatetimeComparisons(TransactionCase):
    def test_due_is_normalized(self):
        s=(Path(__file__).parents[1]/'services'/'simple_planning_engine.py').read_text()
        self.assertIn('fields.Date.to_date(due) > self.plan.date_end', s)
    def test_sale_date_is_normalized(self):
        s=(Path(__file__).parents[1]/'services'/'simple_planning_engine.py').read_text()
        self.assertIn('fields.Date.to_date(line.planning_delivery_date) <= self.plan.date_end', s)
