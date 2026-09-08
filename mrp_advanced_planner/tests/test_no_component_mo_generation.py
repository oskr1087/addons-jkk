from pathlib import Path

from odoo.tests.common import TransactionCase


class TestComponentMOGeneration(TransactionCase):

    def test_manufacturing_action_creates_child_mos(self):
        from ..models import planning_plan
        source = Path(planning_plan.__file__).read_text()
        start = source.find('def action_create_manufacturing')
        end = source.find('def _ensure_product_purchase_vendor', start)
        action_source = source[start:end]

        self.assertIn(
            '_create_component_manufacturing_orders()',
            action_source,
        )
        self.assertIn(
            '_sync_component_purchase_plan()',
            action_source,
        )

    def test_child_mos_are_created_before_finished_mo_loop(self):
        from ..models import planning_plan
        source = Path(planning_plan.__file__).read_text()
        start = source.find('def action_create_manufacturing')
        end = source.find('def _ensure_product_purchase_vendor', start)
        action_source = source[start:end]
        child_pos = action_source.find(
            '_create_component_manufacturing_orders()'
        )
        root_pos = action_source.find('for line in lines:')
        self.assertGreaterEqual(child_pos, 0)
        self.assertGreater(root_pos, child_pos)

    def test_component_classification_drives_sub_mos(self):
        model = self.env['mrp.planning.production.component']
        self.assertIn('to_manufacture_qty', model._fields)
        self.assertIn('generated_production_id', model._fields)
