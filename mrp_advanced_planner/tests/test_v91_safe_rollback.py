from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV91SafeRollback(TransactionCase):

    def test_plan_has_atomic_rollback_precheck(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        self.assertIn('def _aps_rollback_blockers', source)
        self.assertIn('def _aps_rollback_lines', source)
        block = source.split('def _aps_rollback_lines', 1)[1].split(
            'def action_cancel_plan', 1
        )[0]
        self.assertLess(
            block.find('_aps_rollback_blockers'),
            block.find('_aps_cancel_documents_for_lines'),
        )

    def test_done_stock_and_received_purchase_block_rollback(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        self.assertIn("if mo.state == 'done'", source)
        self.assertIn("qty_received", source)
        self.assertIn("if picking.state == 'done'", source)
        self.assertIn("('state', '=', 'consumed')", source)

    def test_line_action_releases_so_by_unlinking_relations(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_lines.py').read_text()
        self.assertIn('def action_remove_from_plan', source)
        plan = (root / 'models' / 'planning_plan.py').read_text()
        self.assertIn("source_sale_line_ids", plan)
        self.assertIn("lines.with_context(", plan)

    def test_purchase_rollback_is_line_scoped(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        block = source.split(
            'def _aps_cancel_documents_for_lines', 1
        )[1].split(
            'def _aps_cleanup_generated_purchase_plan', 1
        )[0]
        self.assertIn(
            "('planning_plan_line_id', 'in', lines.ids)",
            block,
        )
        self.assertIn('purchase_lines.unlink()', block)

    def test_ui_has_simple_remove_and_cancel_actions(self):
        root = Path(__file__).parents[1]
        xml = (root / 'views' / 'planning_plan_views.xml').read_text()
        self.assertIn('name="action_remove_from_plan"', xml)
        self.assertIn('name="action_cancel_plan"', xml)
        self.assertIn('Retirar de planificación', xml)
        self.assertIn('Cancelar planificación', xml)
