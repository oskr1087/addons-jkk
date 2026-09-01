from odoo.tests.common import TransactionCase


class TestComponentAvailabilityUI(TransactionCase):

    def test_component_model_has_availability_fields(self):
        model = self.env['mrp.planning.production.component']
        for field_name in (
            'availability_qty',
            'availability_need_qty',
            'availability_status',
            'availability_label',
        ):
            self.assertIn(field_name, model._fields)

    def test_component_has_popup_action(self):
        self.assertTrue(
            hasattr(
                self.env['mrp.planning.production.component'],
                'action_open_availability',
            )
        )

    def test_wizard_supports_component_source(self):
        wizard = self.env['mrp.planning.stock.availability.wizard']
        self.assertIn('production_component_id', wizard._fields)
        self.assertIn('availability_status', wizard._fields)
