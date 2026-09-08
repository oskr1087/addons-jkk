from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV90ProcessHardening(TransactionCase):

    def test_no_stock_quant_override_is_introduced(self):
        root = Path(__file__).parents[1]
        sources = '\n'.join(
            path.read_text()
            for path in (root / 'models').glob('*.py')
        )
        self.assertNotIn("def _apply_inventory(", sources)

    def test_mo_done_refreshes_only_aps_logical_reservations(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'models' / 'mrp_extensions.py'
        ).read_text()
        self.assertIn(
            '_aps_auto_complete_pending_for_products',
            source,
        )

    def test_created_mo_lot_owner_is_validated(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'models' / 'planning_plan.py'
        ).read_text()
        self.assertIn(
            'def _aps_validate_created_mo_lot_links',
            source,
        )
        self.assertIn(
            'self._aps_validate_created_mo_lot_links(mo)',
            source,
        )

    def test_tooltips_are_business_readable(self):
        root = Path(__file__).parents[1]
        xml = (
            root / 'static' / 'src' / 'xml' /
            'planning_component_tree.xml'
        ).read_text()
        self.assertIn('Ver disponibilidad por almacén', xml)
        self.assertIn('Administrar lotes reservados', xml)
