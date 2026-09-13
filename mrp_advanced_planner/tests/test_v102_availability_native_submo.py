from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV102AvailabilityNativeSubMo(TransactionCase):

    def test_component_resolves_native_submo_owner(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_lines.py').read_text()
        method = source.split(
            'def _aps_lot_production', 1
        )[1].split('def _aps_consumed_qty_for_lot', 1)[0]
        self.assertIn(
            "('aps_planning_component_id', '=', ancestor.id)",
            method,
        )
        self.assertIn(
            'return self.planning_line_id.created_production_id',
            method,
        )

    def test_locked_component_can_sync_lot_operationally(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_lines.py').read_text()
        self.assertIn('aps_allow_locked_lot_sync', source)

    def test_native_submo_syncs_lots_after_confirm(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'stock_rule.py').read_text()
        self.assertIn(
            '._aps_sync_default_lot_reservations()',
            source,
        )
        self.assertIn(
            'aps_allow_locked_lot_sync=True',
            source,
        )

    def test_ui_does_not_call_available_stock_unavailable_lot(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'static' / 'src' / 'js'
            / 'planning_component_tree.js'
        ).read_text()
        self.assertIn('Disponible - lote pendiente', source)
        self.assertNotIn('return "Sin disponibilidad de lote";', source)
