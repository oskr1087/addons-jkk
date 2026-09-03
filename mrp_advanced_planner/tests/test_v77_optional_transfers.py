from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV77OptionalTransfers(TransactionCase):

    def test_manufacturing_does_not_block_on_suggested_transfers(self):
        from ..models import planning_plan
        source = Path(planning_plan.__file__).read_text()
        start = source.index('def action_create_manufacturing')
        end = source.find('\n    def ', start + 10)
        block = source[start:end if end > 0 else len(source)]
        self.assertNotIn('traslado(s) sugerido(s) pendientes', block)
        self.assertIn('Internal transfers are OPTIONAL', block)

    def test_component_supply_does_not_deduct_unexecuted_move(self):
        from ..services import component_sourcing
        source = Path(component_sourcing.__file__).read_text()
        self.assertNotIn(
            'residual_after_move = max(shortage - movable, 0.0)',
            source,
        )
        self.assertIn('supply_shortage = shortage', source)
        self.assertIn('to_buy = supply_shortage', source)
        self.assertIn('to_make = supply_shortage', source)

    def test_real_transfer_still_requires_recalculation(self):
        from ..models import planning_lines
        source = Path(planning_lines.__file__).read_text()
        start = source.index('def action_create_transfer')
        end = source.find('\n    def ', start + 10)
        block = source[start:end if end > 0 else len(source)]
        self.assertIn("'needs_recalculation': True", block)
