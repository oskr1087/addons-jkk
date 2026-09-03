from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV78LotReservation(TransactionCase):

    def test_component_has_lot_reservation_fields(self):
        model = self.env['mrp.planning.production.component']
        for field in (
            'lot_reservation_ids',
            'reserved_lot_qty',
            'lot_reservation_count',
            'lot_reservation_status',
            'product_tracking',
        ):
            self.assertIn(field, model._fields)

    def test_reservation_model_exists(self):
        model = self.env['mrp.planning.component.lot.reservation']
        self.assertIn('lot_id', model._fields)
        self.assertIn('reserved_qty', model._fields)
        self.assertIn('production_id', model._fields)

    def test_sourcing_triggers_default_lot_reservation(self):
        from ..services import component_sourcing
        source = Path(component_sourcing.__file__).read_text()
        self.assertIn(
            'components._aps_sync_default_lot_reservations()',
            source,
        )

    def test_other_mrp_consumption_is_guarded(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'lot_reservation.py').read_text()
        self.assertIn(
            'El lote %s está reservado por la planificación %s',
            source,
        )
        self.assertIn('_aps_validate_reserved_lot', source)

    def test_generated_mo_receives_lot_reservation_owner(self):
        from ..models import planning_plan
        source = Path(planning_plan.__file__).read_text()
        self.assertIn("'production_id': mo.id", source)
        self.assertIn("'state': 'assigned'", source)
