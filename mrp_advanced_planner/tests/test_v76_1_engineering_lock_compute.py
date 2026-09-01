import ast
from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV761EngineeringLockCompute(TransactionCase):

    def test_compute_method_belongs_to_component_model(self):
        from ..models import planning_lines
        tree = ast.parse(Path(planning_lines.__file__).read_text())
        owners = []
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                methods = {
                    item.name
                    for item in node.body
                    if isinstance(item, ast.FunctionDef)
                }
                if '_compute_engineering_locked' in methods:
                    owners.append(node.name)
        self.assertEqual(owners, ['PlanningProductionComponent'])

    def test_engineering_locked_field_compute_is_available(self):
        model = self.env['mrp.planning.production.component']
        self.assertIn('engineering_locked', model._fields)
        self.assertTrue(hasattr(model, '_compute_engineering_locked'))
