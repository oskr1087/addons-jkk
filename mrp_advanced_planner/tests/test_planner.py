from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestSimplePlanner(TransactionCase):
    def test_plan_moves_to_calculated(self):
        plan = self.env['mrp.planning.plan'].create({
            'name': 'Planning test',
            'date_end': '2030-01-01 00:00:00',
        })
        plan.action_calculate()
        self.assertEqual(plan.state, 'calculated')

    def test_cannot_approve_draft_plan(self):
        plan = self.env['mrp.planning.plan'].create({
            'name': 'Approval test',
            'date_end': '2030-01-01 00:00:00',
        })
        with self.assertRaises(UserError):
            plan.action_open_approval()

    def test_forecast_line_can_be_deleted_before_approval(self):
        plan = self.env['mrp.planning.plan'].create({
            'name': 'Delete forecast test',
            'date_end': '2030-01-01 00:00:00',
        })
        product = self.env['product.product'].create({'name': 'Forecast product'})
        line = self.env['mrp.planning.plan.line'].create({
            'plan_id': plan.id,
            'product_id': product.id,
            'sales_qty': 10,
            'net_requirement_qty': 10,
            'planned_production_qty': 10,
        })
        line.unlink()
        self.assertFalse(line.exists())
