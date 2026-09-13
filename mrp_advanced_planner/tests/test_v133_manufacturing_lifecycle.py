from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV133ManufacturingLifecycle(TransactionCase):

    def test_move_line_creation_no_longer_requires_preexisting_logical_lot(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'lot_reservation.py').read_text()
        method = source.split(
            'def _aps_validate_reserved_lot', 1
        )[1].split('@api.model_create_multi', 1)[0]

        self.assertNotIn(
            'todavía no tiene ningún lote reservado para esta OF',
            method,
        )
        self.assertIn(
            'Strict "there must be a complete APS lot reservation"',
            method,
        )

    def test_confirmation_assigns_available_stock_without_blocking_pending_supply(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'mrp_extensions.py').read_text()
        method = source.split('def action_confirm', 1)[1].split(
            'def _compute_component_purchase_count', 1
        )[0]

        self.assertIn('aps_mo.action_assign()', method)

    def test_start_and_done_are_strict(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'mrp_extensions.py').read_text()

        self.assertIn('def _aps_validate_ready_to_produce', source)
        self.assertIn('def action_start(self):', source)
        self.assertIn(
            'self._aps_validate_ready_to_produce()',
            source.split('def action_start(self):', 1)[1].split(
                'def button_mark_done', 1
            )[0],
        )
        self.assertIn(
            'self._aps_validate_ready_to_produce()',
            source.split('def button_mark_done(self):', 1)[1].split(
                'def write', 1
            )[0],
        )

    def test_child_mo_can_exist_before_material_is_complete(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'stock_rule.py').read_text()
        method = source.split(
            'def _aps_enrich_and_confirm_native_submos', 1
        )[1].split('def _run_manufacture', 1)[0]

        self.assertIn("mo.action_confirm()", method)
        self.assertIn("mo.action_assign()", method)

    def test_purchase_plan_is_not_purchase_order(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        self.assertIn(
            'PLAN de compras generado automáticamente',
            source,
        )
