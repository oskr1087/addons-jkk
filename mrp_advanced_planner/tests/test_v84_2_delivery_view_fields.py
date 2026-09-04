from odoo.tests.common import TransactionCase


class TestV842DeliveryViewFields(TransactionCase):

    def test_sale_line_uom_field_used_by_delivery_view_exists(self):
        self.assertIn("product_uom_id", self.env["sale.order.line"]._fields)

    def test_delivery_views_are_registered(self):
        self.assertTrue(
            self.env.ref("mrp_advanced_planner.view_sale_order_line_aps_delivery_calendar")
        )
        self.assertTrue(
            self.env.ref("mrp_advanced_planner.view_sale_order_line_aps_delivery_list")
        )

    def test_calendar_remains_default(self):
        action = self.env.ref(
            "mrp_advanced_planner.action_sale_order_line_aps_delivery_schedule"
        )
        self.assertTrue(action.view_mode.startswith("calendar"))
