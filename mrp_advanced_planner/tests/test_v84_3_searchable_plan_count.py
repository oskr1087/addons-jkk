from odoo.tests.common import TransactionCase


class TestV843SearchablePlanCount(TransactionCase):

    def test_aps_plan_count_has_search_method(self):
        field = self.env['sale.order.line']._fields['aps_plan_count']
        self.assertEqual(field.search, '_search_aps_plan_count')

    def test_pending_filter_domain_can_be_evaluated(self):
        lines = self.env['sale.order.line'].search([
            ('aps_plan_count', '=', 0),
        ], limit=1)
        self.assertTrue(lines is not None)

    def test_planned_filter_domain_can_be_evaluated(self):
        lines = self.env['sale.order.line'].search([
            ('aps_plan_count', '>', 0),
        ], limit=1)
        self.assertTrue(lines is not None)
