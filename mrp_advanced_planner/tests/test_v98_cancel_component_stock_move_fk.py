from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV98CancelComponentStockMoveFk(TransactionCase):

    def test_rollback_detaches_stock_moves_before_component_delete(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        rollback = source.split(
            'def _aps_rollback_lines', 1
        )[1].split('def action_cancel_plan', 1)[0]
        self.assertIn(
            "('aps_planning_component_id', 'in', component_subtree.ids)",
            rollback,
        )
        self.assertIn("'aps_planning_component_id': False", rollback)

    def test_component_unlink_has_rollback_fk_safety(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_lines.py').read_text()
        self.assertIn("if self.env.context.get('aps_rollback'):", source)
        self.assertIn(
            "('aps_planning_component_id', 'in', records.ids)",
            source,
        )

    def test_stock_move_fk_is_set_null(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'mrp_extensions.py').read_text()
        marker = "aps_planning_component_id = fields.Many2one("
        block = source.split(marker, 2)[-1][:500]
        self.assertIn("ondelete='set null'", block)
