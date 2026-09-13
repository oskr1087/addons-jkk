from pathlib import Path
from odoo.tests.common import TransactionCase


class TestComponentMOGeneration(TransactionCase):

    def test_manufacturing_action_uses_native_child_procurement_only(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        start = source.find('def action_create_manufacturing')
        end = source.find('def _ensure_product_purchase_vendor', start)
        action_source = source[start:end]

        self.assertIn('mo._aps_launch_missing_component_procurements()', action_source)
        self.assertIn('self._aps_repair_native_submanufacturing_chain()', action_source)
        self.assertIn('_sync_component_purchase_plan()', action_source)

    def test_component_classification_drives_sub_mos(self):
        model = self.env['mrp.planning.production.component']
        self.assertIn('to_manufacture_qty', model._fields)
        self.assertIn('pending_manufacture_qty', model._fields)
        self.assertIn('generated_production_id', model._fields)
