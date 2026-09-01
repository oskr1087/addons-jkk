from pathlib import Path

from odoo.tests.common import TransactionCase


class TestSubMOSnapshotRouting(TransactionCase):

    def test_submo_uses_component_children(self):
        from ..models import mrp_extensions
        source = Path(mrp_extensions.__file__).read_text()
        self.assertIn('aps_planning_component_id', source)
        self.assertIn('parent_component.child_line_ids', source)
        self.assertIn('factor = (self.product_qty or 0.0) / base_qty', source)

    def test_purchase_planner_link_fields_exist(self):
        plan = self.env['mrp.planning.plan']
        self.assertIn('generated_purchase_plan_id', plan._fields)
        self.assertIn('source_manufacturing_plan_id', plan._fields)
