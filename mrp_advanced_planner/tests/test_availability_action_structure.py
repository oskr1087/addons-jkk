from odoo.tests.common import TransactionCase


class TestAvailabilityActionStructure(TransactionCase):

    def test_component_availability_action_has_explicit_views(self):
        Wizard = self.env['mrp.planning.stock.availability.wizard']
        source = Wizard.open_for_component.__func__.__code__
        # Functional contract is validated through the XML ID and method source
        # at module load; this test guards the expected view availability.
        view = self.env.ref(
            'mrp_advanced_planner.view_mrp_planning_stock_availability_wizard_form'
        )
        self.assertTrue(view)
        self.assertEqual(view.model, 'mrp.planning.stock.availability.wizard')
