from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV127ExistingRootSubMO(TransactionCase):

    def test_existing_root_support_is_kept_in_manufacturing_execution(self):
        root = Path(__file__).parents[1]
        mrp = (root / 'models' / 'mrp_extensions.py').read_text()
        plan = (root / 'models' / 'planning_plan.py').read_text()

        self.assertIn(
            'def _aps_launch_missing_component_procurements',
            mrp,
        )
        manufacture = plan.split('def action_create_manufacturing', 1)[1].split(
            'def _ensure_product_purchase_vendor', 1
        )[0]
        self.assertIn('mo._aps_launch_missing_component_procurements()', manufacture)

    def test_no_manual_generate_submo_button(self):
        root = Path(__file__).parents[1]
        view = (root / 'views' / 'planning_plan_views.xml').read_text()
        self.assertNotIn('string="Generar sub-OF"', view)
