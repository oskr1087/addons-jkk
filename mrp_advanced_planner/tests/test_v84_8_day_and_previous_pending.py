from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV848DayAndPreviousPending(TransactionCase):

    def test_wizard_includes_previous_pending_dates(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'wizard' / 'planning_calendar_day_wizard.py'
        ).read_text()
        block = source.split('def _pending_lines(self):', 1)[1].split(
            '@api.depends', 1
        )[0]
        self.assertIn(
            "('planning_delivery_date', '<', end)",
            block,
        )
        self.assertNotIn(
            "('planning_delivery_date', '>=', start)",
            block,
        )

    def test_wizard_still_excludes_already_planned_lines(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'wizard' / 'planning_calendar_day_wizard.py'
        ).read_text()
        self.assertIn(
            'not line.aps_plan_ids',
            source,
        )
