from pathlib import Path

from odoo.tests.common import TransactionCase


class TestNoComponentMOGeneration(TransactionCase):

    def test_manufacturing_action_does_not_create_child_mos(self):
        from ..models import planning_plan
        source = Path(planning_plan.__file__).read_text()
        start = source.find('def action_create_manufacturing')
        end = source.find('def _ensure_product_purchase_vendor', start)
        action_source = source[start:end]

        self.assertNotIn(
            '_create_component_manufacturing_orders()',
            action_source,
        )
        self.assertIn(
            '_sync_component_purchase_plan()',
            action_source,
        )

    def test_component_classification_still_exists(self):
        model = self.env['mrp.planning.production.component']
        self.assertIn('supply_resolution', model._fields)
        self.assertIn('to_manufacture_qty', model._fields)
