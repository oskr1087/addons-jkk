from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV73SubcontractSnapshot(TransactionCase):

    def test_batch_graph_separates_subcontract_from_internal_bom(self):
        from ..services import bom_batch
        source = Path(bom_batch.__file__).read_text()
        self.assertIn('def subcontract_bom', source)
        self.assertIn(
            "lambda bom: bom.type in ('normal', 'phantom')",
            source,
        )
        self.assertIn(
            "lambda bom: bom.type == 'subcontract'",
            source,
        )

    def test_snapshot_marks_subcontract_node(self):
        from ..services import manufacturing_snapshot
        source = Path(manufacturing_snapshot.__file__).read_text()
        self.assertIn("'is_subcontracted': is_subcontracted", source)
        self.assertIn("'subcontract_bom_id':", source)
        self.assertIn('bom_override=subcontract_bom', source)

    def test_sourcing_purchases_subcontract_parent(self):
        from ..services import component_sourcing
        source = Path(component_sourcing.__file__).read_text()
        self.assertIn("elif is_subcontracted:", source)
        self.assertIn("to_buy = residual_after_move", source)
        self.assertIn("resolution = (", source)
