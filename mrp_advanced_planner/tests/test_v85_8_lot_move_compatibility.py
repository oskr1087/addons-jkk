from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV858LotMoveCompatibility(TransactionCase):

    def test_child_mo_gets_lot_owner_before_confirm(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'models' / 'planning_plan.py'
        ).read_text()
        block = source.split(
            'def _create_component_manufacturing_orders', 1
        )[1].split(
            'def action_open_component_productions', 1
        )[0]
        owner_pos = block.find("'production_id': mo.id")
        confirm_pos = block.find('.action_confirm()')
        self.assertGreaterEqual(owner_pos, 0)
        self.assertGreater(confirm_pos, owner_pos)

    def test_root_mo_does_not_take_descendant_reservations(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'models' / 'planning_plan.py'
        ).read_text()
        block = source.split(
            'def action_create_manufacturing', 1
        )[1].split(
            'def _ensure_product_purchase_vendor', 1
        )[0]
        self.assertIn(
            "mo._aps_snapshot_components().mapped(",
            block,
        )
        self.assertNotIn(
            "line.production_component_ids.mapped(",
            block,
        )

    def test_direct_mo_conflict_is_quantity_based_not_lot_exclusive(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'models' / 'lot_reservation.py'
        ).read_text()
        block = source.split(
            'def _aps_validate_reserved_lot', 1
        )[1].split(
            '@api.model_create_multi', 1
        )[0]
        self.assertIn('protected_qty', block)
        self.assertIn('operation_qty', block)
        self.assertIn('usable_outside_other_aps', block)
        self.assertNotIn(
            'A lot reserved for another APS demand may not be consumed',
            block,
        )

    def test_internal_moves_are_guarded_too(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'models' / 'lot_reservation.py'
        ).read_text()
        self.assertIn('def _aps_source_warehouse', source)
        self.assertIn("location.usage != 'internal'", source)

    def test_lot_free_rows_reconcile_odoo_and_aps_reservations(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'models' / 'planning_lines.py'
        ).read_text()
        block = source.split(
            'def _aps_lot_free_rows', 1
        )[1].split(
            'def _aps_sync_default_lot_reservations', 1
        )[0]
        self.assertIn('own_odoo_by_lot', block)
        self.assertIn('other_aps_odoo_by_lot', block)
        self.assertIn(
            'logical_other_not_materialized',
            block,
        )

    def test_receipt_completion_uses_correct_child_mo_owner(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'models' / 'lot_reservation.py'
        ).read_text()
        self.assertIn(
            'production = component._aps_lot_production()',
            source,
        )
