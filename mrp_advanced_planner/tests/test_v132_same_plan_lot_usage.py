from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV132SamePlanLotUsage(TransactionCase):

    def test_same_aps_plan_is_not_treated_as_foreign_reservation(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'lot_reservation.py').read_text()

        method = source.split(
            'def _aps_validate_reserved_lot', 1
        )[1].split('@api.model_create_multi', 1)[0]

        self.assertIn('current_plan = production.advanced_plan_id', method)
        self.assertIn(
            'reservation.plan_id == current_plan',
            method,
        )
        self.assertIn('owned |= same_plan', method)

    def test_stale_parent_owner_is_repaired_to_current_child(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'lot_reservation.py').read_text()

        method = source.split(
            'def _aps_validate_reserved_lot', 1
        )[1].split('@api.model_create_multi', 1)[0]

        self.assertIn("'production_id': production.id", method)
        self.assertIn(
            'production.aps_parent_production_id',
            method,
        )

    def test_error_wording_only_calls_other_plans_foreign(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'lot_reservation.py').read_text()
        self.assertIn(
            'Reservado por otras planificaciones APS',
            source,
        )
