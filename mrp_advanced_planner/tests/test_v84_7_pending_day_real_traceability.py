from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV847PendingDayRealTraceability(TransactionCase):

    def test_wizard_does_not_filter_nonstored_count_in_base_domain(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'wizard' / 'planning_calendar_day_wizard.py'
        ).read_text()
        block = source.split('def _pending_lines(self):', 1)[1].split(
            '@api.depends', 1
        )[0]
        self.assertNotIn("('aps_plan_count', '=', 0)", block)
        self.assertIn('not line.aps_plan_ids', block)

    def test_wizard_exposes_pending_line_preview(self):
        self.assertIn(
            'pending_sale_line_ids',
            self.env['mrp.planning.calendar.day.wizard']._fields,
        )
