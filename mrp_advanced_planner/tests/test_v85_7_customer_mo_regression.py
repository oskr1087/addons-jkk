from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV857CustomerMORegression(TransactionCase):
    """Regression for PT -> Laminado -> Impresión APS manufacturing chain."""

    def test_snapshot_is_repaired_before_sourcing_and_mo_creation(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        block = source.split(
            'def action_create_manufacturing', 1
        )[1].split(
            'def _ensure_product_purchase_vendor', 1
        )[0]
        repair = block.find('ensure_complete(lines)')
        sourcing = block.find('_refresh_component_sourcing()')
        children = block.find('_create_component_manufacturing_orders()')
        self.assertGreaterEqual(repair, 0)
        self.assertGreater(sourcing, repair)
        self.assertGreater(children, sourcing)

    def test_missing_positive_bom_line_cannot_silently_disappear(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'models' / 'mrp_extensions.py'
        ).read_text()
        self.assertIn(
            'def _aps_validate_snapshot_against_bom',
            source,
        )
        self.assertIn(
            'Componentes faltantes',
            source,
        )

    def test_snapshot_repair_is_additive_not_full_rebuild(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'services' / 'manufacturing_snapshot.py'
        ).read_text()
        block = source.split(
            'def ensure_complete', 1
        )[1].split('def build', 1)[0]
        self.assertIn('source_bom_line_id', block)
        self.assertNotIn(
            "search([('planning_line_id', 'in', planning_lines.ids)]).unlink()",
            block,
        )

    def test_mto_manufacturing_is_not_duplicated_during_aps_confirmation(self):
        root = Path(__file__).parents[1]
        stock_rule = (
            root / 'models' / 'stock_rule.py'
        ).read_text()
        self.assertIn(
            'aps_explicit_component_manufacturing',
            stock_rule,
        )
