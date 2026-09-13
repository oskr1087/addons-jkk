from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV100NativeSubMoWithComponents(TransactionCase):

    def test_native_submo_is_enriched_after_odoo_creation(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'stock_rule.py').read_text()
        self.assertIn(
            'result = super()._run_manufacture(procurements)',
            source,
        )
        self.assertIn(
            'self._aps_enrich_and_confirm_native_submos(procurements)',
            source,
        )

    def test_child_mo_uses_exact_aps_component_subtree(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'stock_rule.py').read_text()
        self.assertIn("'aps_component_snapshot': True", source)
        self.assertIn("'aps_planning_component_id': component.id", source)
        self.assertIn('direct_components = mo._aps_snapshot_components()', source)

    def test_draft_native_child_is_confirmed(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'stock_rule.py').read_text()
        self.assertIn("if mo.state == 'draft':", source)
        self.assertIn('mo.action_confirm()', source)

    def test_recursive_traceability_uses_parent_mo(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'stock_rule.py').read_text()
        self.assertIn("moves.mapped('raw_material_production_id')[:1]", source)
        self.assertIn("'aps_parent_production_id'", source)
