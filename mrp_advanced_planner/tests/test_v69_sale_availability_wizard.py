from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV69SaleAvailabilityWizard(TransactionCase):
    def test_wizard_models_exist(self):
        self.assertIn('sale_line_id', self.env['mrp.planning.sale.availability.wizard']._fields)
        self.assertIn('res_model', self.env['mrp.planning.sale.availability.document']._fields)

    def test_sale_action_exists(self):
        self.assertTrue(hasattr(self.env['sale.order.line'], 'action_open_aps_availability'))

    def test_widget_uses_modal_action_not_inline_popover(self):
        module_root = Path(__file__).parents[1]
        js = (module_root / 'static/src/js/planning_sale_availability.js').read_text()
        xml = (module_root / 'static/src/xml/planning_sale_availability.xml').read_text()
        self.assertIn('action_open_aps_availability', js)
        self.assertNotIn('o_aps_supply_popover', xml)
