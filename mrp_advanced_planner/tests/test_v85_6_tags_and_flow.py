from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV856TagsAndFlow(TransactionCase):

    def test_lot_summary_compute_has_dependencies(self):
        field = self.env[
            'mrp.planning.production.component'
        ]._fields['pending_lot_qty']
        self.assertEqual(field.compute, '_compute_lot_reservation_summary')
        self.assertIn('supply_resolution', field.depends)
        self.assertIn('include_in_mo', field.depends)

    def test_parent_covered_rows_have_zero_lot_target(self):
        Component = self.env['mrp.planning.production.component']
        # Structural regression: helper must use effective requirement and must
        # not fall back to gross BoM planned quantity.
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'planning_lines.py').read_text()
        block = source.split(
            'def _aps_effective_lot_target_qty', 1
        )[1].split('def _compute_lot_reservation_summary', 1)[0]
        self.assertIn('effective_required_qty', block)
        self.assertNotIn('or self.planned_qty', block)

    def test_tree_uses_real_shortage_helper(self):
        root = Path(__file__).parents[1]
        xml = (
            root / 'static' / 'src' / 'xml' /
            'planning_component_tree.xml'
        ).read_text()
        self.assertIn('getSupplyShortage(row)', xml)
        self.assertNotIn(
            'formatQty(row.availability_need_qty)',
            xml,
        )

    def test_tags_are_explicit(self):
        root = Path(__file__).parents[1]
        js = (
            root / 'static' / 'src' / 'js' /
            'planning_component_tree.js'
        ).read_text()
        for label in (
            'Lote no requerido',
            'No abastecer - padre cubierto',
            'Cubierto - lote asignado',
            'Lote disponible - asignar',
            'Revisar abastecimiento',
        ):
            self.assertIn(label, js)
