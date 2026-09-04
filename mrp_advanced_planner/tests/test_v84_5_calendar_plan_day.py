from datetime import datetime

from odoo.tests.common import TransactionCase


class TestV845CalendarPlanDay(TransactionCase):

    def test_plan_has_explicit_sale_line_scope(self):
        self.assertIn(
            'source_sale_line_ids',
            self.env['mrp.planning.plan']._fields,
        )

    def test_day_wizard_model_and_action_exist(self):
        self.assertIn(
            'planning_date',
            self.env['mrp.planning.calendar.day.wizard']._fields,
        )
        self.assertTrue(
            self.env.ref(
                'mrp_advanced_planner.action_mrp_planning_calendar_day_wizard'
            )
        )

    def test_status_filter_remains_searchable(self):
        self.env['sale.order.line'].search([
            ('aps_plan_count', '=', 0),
        ], limit=1)
