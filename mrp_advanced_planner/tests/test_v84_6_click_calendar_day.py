from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV846ClickCalendarDay(TransactionCase):

    def test_calendar_uses_dedicated_js_class(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'views' / 'sale_delivery_schedule_views.xml'
        ).read_text()
        self.assertIn('js_class="aps_delivery_calendar"', source)
        self.assertIn('date_start="planning_delivery_date"', source)

    def test_old_plan_day_menu_is_removed(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'views' / 'planning_calendar_day_wizard_views.xml'
        ).read_text()
        self.assertNotIn('menu_sale_aps_plan_day', source)

    def test_calendar_click_controller_passes_selected_day(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'static' / 'src' / 'js' /
            'planning_delivery_calendar.js'
        ).read_text()
        self.assertIn('record?.start?.toISODate?.()', source)
        self.assertIn('default_planning_date: planningDate', source)
        self.assertIn(
            'mrp.planning.calendar.day.wizard',
            source,
        )

    def test_day_wizard_still_filters_only_unplanned_lines(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'wizard' / 'planning_calendar_day_wizard.py'
        ).read_text()
        self.assertIn("('aps_plan_count', '=', 0)", source)
        self.assertIn("('planning_delivery_date', '>=', start)", source)
        self.assertIn("('planning_delivery_date', '<', end)", source)
