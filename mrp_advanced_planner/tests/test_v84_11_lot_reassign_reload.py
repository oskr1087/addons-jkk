from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV8411LotReassignReload(TransactionCase):

    def test_component_has_reload_and_reassign_actions(self):
        model = self.env['mrp.planning.production.component']
        self.assertTrue(hasattr(model, 'action_complete_lot_reservations'))
        self.assertTrue(hasattr(model, 'action_reassign_lot_reservations'))

    def test_locked_component_auto_create_context_is_supported(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'lot_reservation.py').read_text()
        create_block = source.split(
            '@api.model_create_multi', 1
        )[1].split('def write(', 1)[0]
        self.assertIn(
            "aps_allow_locked_lot_reservation_write",
            create_block,
        )

    def test_dedicated_lot_management_popup_exists(self):
        self.assertTrue(
            self.env.ref(
                'mrp_advanced_planner.'
                'view_planning_component_lot_management_form'
            )
        )

    def test_reassign_blocks_after_real_consumption(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_lines.py').read_text()
        self.assertIn(
            'No puede reasignar los lotes de %s porque ya existe consumo',
            source,
        )

    def test_receipt_autocomplete_remains_enabled(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'lot_reservation.py').read_text()
        self.assertIn(
            '_aps_auto_complete_pending_for_products',
            source,
        )
        self.assertIn('def button_validate(self):', source)
