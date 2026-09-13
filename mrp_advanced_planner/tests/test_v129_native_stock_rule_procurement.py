from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV129NativeStockRuleProcurement(TransactionCase):

    def test_native_stock_rule_dispatch_is_used(self):
        root = Path(__file__).parents[1]
        mrp = (root / 'models' / 'mrp_extensions.py').read_text()
        method = mrp.split(
            'def _aps_launch_missing_component_procurements', 1
        )[1].split('def _compute_component_purchase_count', 1)[0]

        self.assertIn('StockRule.Procurement(', method)
        self.assertIn('StockRule.run([procurement])', method)
        self.assertIn("'move_dest_ids': move", method)
        self.assertIn("'route_ids': manufacture_route", method)
        self.assertIn('component.to_manufacture_qty', method)

    def test_recalculate_logs_generated_children(self):
        root = Path(__file__).parents[1]
        plan = (root / 'models' / 'planning_plan.py').read_text()
        self.assertIn(
            'APS generó mediante abastecimiento nativo de Odoo',
            plan,
        )
