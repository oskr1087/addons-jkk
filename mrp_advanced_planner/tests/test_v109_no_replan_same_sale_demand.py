from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV109NoReplanSameSaleDemand(TransactionCase):

    def test_cross_plan_committed_sale_lines_are_excluded(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'services' / 'simple_planning_engine.py'
        ).read_text()
        self.assertIn(
            'def _sale_lines_already_committed_to_aps',
            source,
        )
        self.assertIn(
            "('plan_id', '!=', self.plan.id)",
            source,
        )
        self.assertIn(
            "line.plan_id.state in ('calculated', 'finalized')",
            source,
        )
        self.assertIn(
            "line.created_production_id.state != 'cancel'",
            source,
        )

    def test_sale_demand_removes_committed_lines_before_grouping(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'services' / 'simple_planning_engine.py'
        ).read_text()
        sale = source.split(
            'def _sale_demand', 1
        )[1].split('def _selected_sale_outgoing_by_warehouse', 1)[0]
        self.assertIn(
            'committed_sale_lines = self._sale_lines_already_committed_to_aps',
            sale,
        )
        self.assertIn(
            'sale_lines -= committed_sale_lines',
            sale,
        )

    def test_cancelled_plan_does_not_block_sale_line(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'services' / 'simple_planning_engine.py'
        ).read_text()
        method = source.split(
            'def _sale_lines_already_committed_to_aps', 1
        )[1].split('def _sale_demand', 1)[0]
        self.assertIn(
            "if line.plan_id.state == 'cancelled':",
            method,
        )
