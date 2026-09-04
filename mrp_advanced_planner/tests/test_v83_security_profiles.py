from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV83SecurityProfiles(TransactionCase):

    def test_base_planner_group_does_not_imply_stock(self):
        group = self.env.ref('mrp_advanced_planner.group_planner_user')
        stock_group = self.env.ref('stock.group_stock_user')
        self.assertNotIn(stock_group, group.implied_ids)

    def test_functional_groups_keep_native_permissions(self):
        manufacturing = self.env.ref(
            'mrp_advanced_planner.group_planner_manufacturing_user'
        )
        purchase = self.env.ref(
            'mrp_advanced_planner.group_planner_purchase_user'
        )
        self.assertIn(
            self.env.ref('mrp.group_mrp_user'),
            manufacturing.implied_ids,
        )
        self.assertIn(
            self.env.ref('purchase.group_purchase_user'),
            purchase.implied_ids,
        )

    def test_traceability_view_is_target_permission_aware(self):
        root = Path(__file__).parents[1]
        source = (root / 'views' / 'traceability_views.xml').read_text()
        self.assertIn('groups="mrp.group_mrp_user"', source)
        self.assertIn('groups="purchase.group_purchase_user"', source)
        self.assertIn('groups="stock.group_stock_user"', source)
        self.assertIn('groups="sales_team.group_sale_salesman"', source)

    def test_qr_report_does_not_use_removed_groups_id(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'reports' / 'stock_lot_qr_report.xml'
        ).read_text()
        self.assertNotIn('<field name="groups_id"', source)
        self.assertIn(
            '<field name="binding_model_id" ref="stock.model_stock_lot"/>',
            source,
        )
