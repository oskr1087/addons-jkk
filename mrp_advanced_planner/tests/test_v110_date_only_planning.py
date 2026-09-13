from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV110DateOnlyPlanning(TransactionCase):

    def test_sale_delivery_is_date(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'sale_extensions.py').read_text()
        self.assertIn('planning_delivery_date = fields.Date(', source)
        self.assertNotIn('planning_delivery_date = fields.Datetime(', source)

    def test_plan_horizon_and_requirement_are_dates(self):
        root = Path(__file__).parents[1]
        plan = (root / 'models' / 'planning_plan.py').read_text()
        line = (root / 'models' / 'planning_lines.py').read_text()
        self.assertIn("date_end = fields.Date(", plan)
        self.assertIn("date_start = fields.Date(", plan)
        self.assertIn("date_required = fields.Date(", line)

    def test_calendar_wizard_has_no_utc_day_bounds(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'wizard' / 'planning_calendar_day_wizard.py'
        ).read_text()
        self.assertNotIn('_utc_day_bounds', source)
        self.assertNotIn('pytz', source)
        self.assertIn(
            "('planning_delivery_date', '<=', self.planning_date)",
            source,
        )
        self.assertIn("'date_end': self.planning_date", source)

    def test_sale_cutoff_is_direct_date_comparison(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'services' / 'simple_planning_engine.py'
        ).read_text()
        self.assertIn(
            'line.planning_delivery_date <= self.plan.date_end',
            source,
        )
