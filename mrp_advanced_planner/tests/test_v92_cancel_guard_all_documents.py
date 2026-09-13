from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV92CancelGuardAllDocuments(TransactionCase):

    def test_whole_plan_checks_all_pickings_by_plan(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        block = source.split(
            'def _aps_rollback_blockers', 1
        )[1].split(
            'def _aps_cancel_documents_for_lines', 1
        )[0]
        self.assertIn("if whole_plan:", block)
        self.assertIn(
            "('advanced_plan_id', '=', self.id)",
            block,
        )
        self.assertIn(
            "Traslado %s: ya fue validado.",
            block,
        )

    def test_cancel_plan_uses_whole_plan_precheck(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        block = source.split(
            'def action_cancel_plan', 1
        )[1].split('def unlink', 1)[0]
        self.assertIn('whole_plan=True', block)

    def test_root_transfer_link_is_authoritative_for_line_rollback(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        block = source.split(
            'def _aps_cancel_documents_for_lines', 1
        )[1].split(
            'def _aps_cleanup_generated_purchase_plan', 1
        )[0]
        self.assertIn(
            "lines.mapped('created_picking_ids')",
            block,
        )

    def test_generated_purchase_plan_lines_are_resolved_from_components(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        self.assertIn(
            "components.mapped(\n            'generated_purchase_plan_line_id'",
            source,
        )
