from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV111RecalculateAfterDoneTransfer(TransactionCase):

    def test_internal_recalculation_bypasses_manual_unlink_guard(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_lines.py').read_text()
        self.assertIn(
            "internal_recalculation = self.env.context.get(",
            source,
        )
        self.assertIn(
            "'aps_incremental_recalculation'",
            source,
        )
        self.assertIn(
            'and not internal_recalculation',
            source,
        )

    def test_recalculation_releases_only_logical_unassigned_lots(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'services' / 'simple_planning_engine.py'
        ).read_text()
        run = source.split('def run(self):', 1)[1]
        self.assertIn(
            "production_component_ids.lot_reservation_ids",
            run,
        )
        self.assertIn(
            'and not reservation.production_id',
            run,
        )
        self.assertIn(
            "'state': 'released'",
            run,
        )

    def test_generated_external_transfers_are_preserved(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_lines.py').read_text()
        component_unlink = source.split(
            'class PlanningProductionComponent', 1
        )[1].split('def action_delete_component_by_id', 1)[0]
        self.assertIn(
            "lambda move: move.state == 'pending'",
            component_unlink,
        )
        self.assertNotIn(
            "lambda move: move.state == 'generated'",
            component_unlink,
        )

    def test_recalculation_skips_nested_sourcing_refresh_while_unlinking(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_lines.py').read_text()
        self.assertIn(
            "and not self.env.context.get('aps_incremental_recalculation')",
            source,
        )
