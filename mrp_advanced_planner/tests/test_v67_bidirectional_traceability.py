from odoo.tests.common import TransactionCase


class TestV67BidirectionalTraceability(TransactionCase):

    def test_sale_line_has_inverse_aps_traceability_fields(self):
        model = self.env['sale.order.line']
        for field_name in (
            'aps_planning_line_ids',
            'aps_plan_ids',
            'aps_production_ids',
            'aps_purchase_order_ids',
            'aps_picking_ids',
        ):
            self.assertIn(field_name, model._fields)

    def test_manufacturing_has_sales_origin(self):
        model = self.env['mrp.production']
        self.assertIn('planning_sale_line_ids', model._fields)
        self.assertIn('planning_sale_order_ids', model._fields)

    def test_purchase_has_full_origin(self):
        order = self.env['purchase.order']
        line = self.env['purchase.order.line']
        for field_name in (
            'planning_plan_line_ids',
            'planning_sale_line_ids',
            'planning_sale_order_ids',
            'source_manufacturing_plan_id',
        ):
            self.assertIn(field_name, order._fields)
        for field_name in (
            'planning_plan_id',
            'planning_sale_line_ids',
            'planning_sale_order_ids',
            'source_manufacturing_plan_id',
        ):
            self.assertIn(field_name, line._fields)

    def test_plan_line_has_forward_document_links(self):
        model = self.env['mrp.planning.plan.line']
        self.assertIn('source_sale_order_ids', model._fields)
        self.assertIn('created_production_id', model._fields)
        self.assertIn('created_purchase_order_id', model._fields)
        self.assertIn('created_picking_ids', model._fields)
