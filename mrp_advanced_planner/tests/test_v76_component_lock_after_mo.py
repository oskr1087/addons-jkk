from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV76ComponentLockAfterMO(TransactionCase):

    def test_component_model_exposes_engineering_lock(self):
        model = self.env['mrp.planning.production.component']
        self.assertIn('engineering_locked', model._fields)

    def test_backend_write_is_protected(self):
        from ..models import planning_lines
        source = Path(planning_lines.__file__).read_text()
        self.assertIn("self.filtered('engineering_locked')", source)
        self.assertIn("'product_uom_id'", source)
        self.assertIn("'parent_line_id'", source)

    def test_manual_create_is_protected_after_mo(self):
        from ..models import planning_lines
        source = Path(planning_lines.__file__).read_text()
        self.assertIn(
            "planning_line.created_production_id",
            source,
        )
        self.assertIn(
            "No puede agregar componentes",
            source,
        )

    def test_tree_loads_lock_state(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'static/src/js/planning_component_tree.js'
        ).read_text()
        self.assertIn('"engineering_locked"', source)
        self.assertIn('"created_production_id"', source)
