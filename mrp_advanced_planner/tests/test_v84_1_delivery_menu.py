from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV841DeliveryMenu(TransactionCase):

    def test_delivery_schedule_menu_exists_and_is_active(self):
        menu = self.env.ref(
            'mrp_advanced_planner.menu_sale_aps_delivery_schedule'
        )
        self.assertTrue(menu.active)
        self.assertEqual(
            menu.parent_id,
            self.env.ref('sale.sale_order_menu'),
        )
        self.assertEqual(
            menu.action,
            self.env.ref(
                'mrp_advanced_planner.action_sale_order_line_aps_delivery_schedule'
            ),
        )

    def test_calendar_is_default_view(self):
        action = self.env.ref(
            'mrp_advanced_planner.action_sale_order_line_aps_delivery_schedule'
        )
        self.assertTrue(action.view_mode.startswith('calendar'))

    def test_menu_is_limited_to_sales_users(self):
        menu = self.env.ref(
            'mrp_advanced_planner.menu_sale_aps_delivery_schedule'
        )
        self.assertIn(
            self.env.ref('sales_team.group_sale_salesman'),
            menu.group_ids,
        )
