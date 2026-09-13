from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV96DateDatetimeComparison(TransactionCase):

    def test_sale_delivery_date_is_normalized_before_date_comparison(self):
        root = Path(__file__).parents[1]
        source = (root / 'services' / 'simple_planning_engine.py').read_text()
        self.assertIn(
            'fields.Date.to_date(line.planning_delivery_date) <= self.plan.date_end',
            source,
        )
        self.assertNotIn(
            'line.planning_delivery_date <= self.plan.date_end',
            source,
        )
