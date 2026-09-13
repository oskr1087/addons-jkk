from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV103OwnApsReservedAvailability(TransactionCase):

    def test_sourcing_adds_back_own_aps_reservations(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'services' / 'component_sourcing.py'
        ).read_text()
        self.assertIn('def _own_aps_reserved', source)
        self.assertIn(
            "('advanced_plan_id', '=', self.plan.id)",
            source,
        )
        self.assertIn('+ own_aps_reserved[key]', source)

    def test_only_materialized_move_lines_are_counted(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'services' / 'component_sourcing.py'
        ).read_text()
        method = source.split(
            'def _own_aps_reserved', 1
        )[1].split('def _subcontract_bom_map', 1)[0]
        self.assertIn("moves.mapped('move_line_ids')", method)
        self.assertNotIn('product_uom_qty', method)

    def test_fallback_availability_uses_own_reserved(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_lines.py').read_text()
        compute = source.split(
            'def _compute_availability', 1
        )[1].split('def unlink', 1)[0]
        self.assertIn('._own_aps_reserved(products, warehouses)', compute)
        self.assertIn('+ own_reserved[key]', compute)

    def test_submo_refreshes_plan_after_reservation(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'stock_rule.py').read_text()
        self.assertIn("ctx['plan'].with_context(", source)
        self.assertIn(')._refresh_component_sourcing()', source)
