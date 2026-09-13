from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV128SubMOOnlyOnRecalculate(TransactionCase):

    def test_recalculate_is_analysis_only(self):
        root = Path(__file__).parents[1]
        plan = (root / 'models' / 'planning_plan.py').read_text()

        section = plan.split(
            'result_count = SimplePlanningEngine(self).run()', 1
        )[1].split(
            '# A search with no demand/results', 1
        )[0]

        self.assertNotIn('_aps_launch_missing_component_procurements()', section)
        self.assertNotIn('_aps_repair_native_submanufacturing_chain()', section)

    def test_manual_generate_submo_button_removed(self):
        root = Path(__file__).parents[1]
        view = (root / 'views' / 'planning_plan_views.xml').read_text()
        self.assertNotIn('string="Generar sub-OF"', view)

    def test_odoo19_uses_stock_rule_procurement(self):
        root = Path(__file__).parents[1]
        mrp = (root / 'models' / 'mrp_extensions.py').read_text()
        method = mrp.split(
            'def _aps_launch_missing_component_procurements', 1
        )[1].split('def _compute_component_purchase_count', 1)[0]

        self.assertIn("StockRule = self.env['stock.rule'].sudo().with_context(", method)
        self.assertIn('StockRule.Procurement(', method)
        self.assertIn('StockRule.run([procurement])', method)
        self.assertNotIn("self.env['procurement.group']", method)
