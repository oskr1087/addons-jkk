from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV844CalendarStatusDates(TransactionCase):

    def test_calendar_uses_line_delivery_date(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'views' / 'sale_delivery_schedule_views.xml'
        ).read_text()
        self.assertIn(
            'date_start="planning_delivery_date"',
            source,
        )

    def test_planner_uses_same_line_delivery_date_and_cutoff(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'services' / 'simple_planning_engine.py'
        ).read_text()
        self.assertIn(
            "('planning_delivery_date', '<=', self.plan.date_end)",
            source,
        )
        self.assertIn(
            "order='planning_delivery_date asc",
            source,
        )

    def test_calendar_status_is_searchable(self):
        field = self.env['sale.order.line']._fields[
            'aps_planning_status'
        ]
        self.assertEqual(
            field.search,
            '_search_aps_planning_status',
        )

    def test_pending_and_planned_domains_are_searchable(self):
        self.env['sale.order.line'].search([
            ('aps_planning_status', '=', 'pending'),
        ], limit=1)
        self.env['sale.order.line'].search([
            ('aps_planning_status', '=', 'planned'),
        ], limit=1)
