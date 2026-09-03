from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV79PendingLotSupply(TransactionCase):

    def test_component_exposes_pending_lot_metrics(self):
        model = self.env['mrp.planning.production.component']
        for field in (
            'pending_lot_qty',
            'lot_coverage_percent',
            'lot_reservation_status',
        ):
            self.assertIn(field, model._fields)

    def test_reservation_can_autocomplete_after_receipt(self):
        model = self.env['mrp.planning.component.lot.reservation']
        self.assertTrue(
            hasattr(model, '_aps_auto_complete_pending_for_products')
        )

    def test_receipt_triggers_pending_reservation_completion(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'lot_reservation.py').read_text()
        self.assertIn('def button_validate(self):', source)
        self.assertIn(
            '_aps_auto_complete_pending_for_products',
            source,
        )

    def test_mo_done_requires_complete_lot_coverage(self):
        from ..models import mrp_extensions
        source = Path(mrp_extensions.__file__).read_text()
        self.assertIn(
            'def _aps_validate_lot_reservation_coverage',
            source,
        )
        self.assertIn('def button_mark_done(self):', source)
        self.assertIn(
            'con seguimiento por lote sin reserva completa',
            source,
        )

    def test_consumption_rejects_unreserved_lot(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'lot_reservation.py').read_text()
        self.assertIn(
            'APS todavía no tiene ningún lote reservado',
            source,
        )
