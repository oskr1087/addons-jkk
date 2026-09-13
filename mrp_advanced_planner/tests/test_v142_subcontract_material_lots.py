from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV142SubcontractMaterialLots(TransactionCase):

    def test_subcontract_children_keep_effective_demand(self):
        from ..services import component_sourcing
        source = Path(component_sourcing.__file__).read_text()
        self.assertIn("elif is_subcontracted:", source)
        self.assertIn("descendant_demand = supply_shortage", source)
        self.assertNotIn("0.0\n                    if is_subcontracted\n                    else child.planned_qty * ratio", source)

    def test_snapshot_marks_direct_subcontract_material(self):
        from ..services import manufacturing_snapshot
        source = Path(manufacturing_snapshot.__file__).read_text()
        self.assertIn("'is_subcontract_material': bom.type == 'subcontract'", source)

    def test_component_model_has_subcontract_material_flag(self):
        Component = self.env['mrp.planning.production.component']
        self.assertIn('is_subcontract_material', Component._fields)

    def test_ui_loads_subcontract_material_flag(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / 'static/src/js/planning_component_tree.js').read_text()
        self.assertIn('"is_subcontract_material"', source)
        self.assertIn('Enviar a subcontratista', source)
        self.assertIn('Fabricar para subcontratista', source)
        self.assertIn('Comprar para subcontratista', source)
