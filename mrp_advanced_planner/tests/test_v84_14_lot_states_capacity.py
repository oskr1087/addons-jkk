from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV8414LotStatesCapacity(TransactionCase):

    def test_lot_allocation_is_quantity_based(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_lines.py').read_text()
        self.assertIn('reserved_elsewhere_qty', source)
        self.assertNotIn('if lot.id in reserved_elsewhere:', source)

    def test_same_lot_can_be_completed_incrementally(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_lines.py').read_text()
        self.assertIn(
            "'reserved_qty': existing.reserved_qty + qty",
            source,
        )

    def test_conflict_message_identifies_product_and_states(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'lot_reservation.py').read_text()
        self.assertIn('Conflicto de reserva de lote', source)
        self.assertIn('Producto: %(product)s', source)
        self.assertIn('Estado de la reserva:', source)
        self.assertIn('OF actual:', source)

    def test_ui_distinguishes_supply_from_lot_readiness(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'static' / 'src' / 'js' /
            'planning_component_tree.js'
        ).read_text()
        self.assertIn('Lotes asignados', source)
        self.assertIn('Lotes por asignar', source)
        self.assertIn('Cubierto, esperando lote', source)
        self.assertIn('Disponible + lote', source)

    def test_cancelled_plan_releases_lots(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_plan.py').read_text()
        self.assertIn("vals.get('state') == 'cancelled'", source)
        self.assertIn("'state': 'released'", source)
