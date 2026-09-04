from pathlib import Path
from odoo.tests.common import TransactionCase

class TestV8415DirectLotAssignment(TransactionCase):
    def test_popup_allocator_is_component_scoped(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_lines.py').read_text()
        block = source.split(
            'def action_complete_lot_reservations(self):', 1
        )[1].split('@api.depends', 1)[0]
        self.assertIn('_aps_allocate_available_lots(replace=False)', block)
        self.assertNotIn('_aps_auto_complete_pending_for_products', block)

    def test_reassign_is_component_scoped(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_lines.py').read_text()
        block = source.split(
            'def action_reassign_lot_reservations(self):', 1
        )[1].split('def _aps_allocate_available_lots', 1)[0]
        self.assertIn('_aps_allocate_available_lots(replace=True)', block)

    def test_popup_refreshes(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_lines.py').read_text()
        self.assertIn('return self.action_open_lot_reservations()', source)

    def test_available_to_assign_state(self):
        model = self.env['mrp.planning.production.component']
        selection = dict(model._fields['lot_reservation_status'].selection)
        self.assertEqual(
            selection.get('available_to_assign'),
            'Disponible para asignar',
        )
