from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV145SubcontractExecution(TransactionCase):

    def test_direct_subcontract_material_make_has_execution_helper(self):
        source = Path(__file__).parents[1].joinpath(
            'models/planning_plan.py'
        ).read_text()
        self.assertIn(
            'def _aps_create_subcontract_material_manufacturing_orders',
            source,
        )
        self.assertIn('component.is_subcontract_material', source)
        self.assertIn("'aps_planning_component_id': component.id", source)
        self.assertIn('._aps_sync_raw_moves()', source)

    def test_fabricar_executes_subcontract_material_make(self):
        source = Path(__file__).parents[1].joinpath(
            'models/planning_plan.py'
        ).read_text()
        self.assertIn(
            'self._aps_create_subcontract_material_manufacturing_orders()',
            source,
        )

    def test_subcontract_purchase_prefers_bom_subcontractor(self):
        source = Path(__file__).parents[1].joinpath(
            'models/planning_plan.py'
        ).read_text()
        self.assertIn(
            "mapped('subcontract_bom_id.subcontractor_ids')",
            source,
        )
        self.assertIn(
            "component.supply_resolution in (\n                        'subcontract', 'move_subcontract'",
            source,
        )
