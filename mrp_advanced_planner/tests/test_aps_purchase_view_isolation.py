from pathlib import Path

from odoo.tests.common import TransactionCase


class TestAPSPurchaseViewIsolation(TransactionCase):

    def test_dedicated_purchase_views_exist(self):
        list_view = self.env.ref(
            'mrp_advanced_planner.view_purchase_order_aps_list'
        )
        form_view = self.env.ref(
            'mrp_advanced_planner.view_purchase_order_aps_form'
        )
        self.assertEqual(list_view.model, 'purchase.order')
        self.assertEqual(form_view.model, 'purchase.order')

    def test_aps_purchase_views_do_not_reference_optional_payment_field(self):
        module_root = Path(__file__).parents[1]
        source = (
            module_root / 'views' / 'aps_purchase_order_views.xml'
        ).read_text()
        self.assertNotIn('estimated_payment_date', source)

    def test_plan_action_uses_explicit_purchase_views(self):
        from ..models import planning_plan
        source = Path(planning_plan.__file__).read_text()
        self.assertIn('view_purchase_order_aps_list', source)
        self.assertIn('view_purchase_order_aps_form', source)
