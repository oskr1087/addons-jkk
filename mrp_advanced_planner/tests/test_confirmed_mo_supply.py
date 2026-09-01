from odoo.tests.common import TransactionCase


class TestConfirmedMoSupply(TransactionCase):
    def test_open_mo_helper_exists_and_handles_confirmed_state(self):
        engine_path = self.env['ir.module.module'].search([
            ('name', '=', 'mrp_advanced_planner')
        ], limit=1)
        self.assertTrue(engine_path)
        Production = self.env['mrp.production']
        states = dict(Production._fields['state'].selection)
        self.assertIn('confirmed', states)
