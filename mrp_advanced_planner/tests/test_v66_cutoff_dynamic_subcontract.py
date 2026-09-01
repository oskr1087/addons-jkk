from pathlib import Path

from odoo import fields
from odoo.tests.common import TransactionCase

from ..services.simple_planning_engine import SimplePlanningEngine


class TestV66CutoffDynamicSubcontract(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.warehouse = self.env['stock.warehouse'].search([
            ('company_id', '=', self.company.id),
        ], limit=1)

    def _product(self, name):
        return self.env['product.product'].create({
            'name': name,
            'is_storable': True,
        })

    def test_sale_demand_never_reads_after_plan_end(self):
        product = self._product('APS V66 Date Product')
        partner = self.env['res.partner'].create({'name': 'APS V66 Customer'})
        order = self.env['sale.order'].create({
            'partner_id': partner.id,
            'warehouse_id': self.warehouse.id,
        })
        before = self.env['sale.order.line'].create({
            'order_id': order.id,
            'product_id': product.id,
            'product_uom_qty': 5.0,
            'product_uom_id': product.uom_id.id,
            'planning_delivery_date': '2026-09-01 10:00:00',
        })
        after = self.env['sale.order.line'].create({
            'order_id': order.id,
            'product_id': product.id,
            'product_uom_qty': 7.0,
            'product_uom_id': product.uom_id.id,
            'planning_delivery_date': '2026-09-05 10:00:00',
        })
        order.action_confirm()

        plan = self.env['mrp.planning.plan'].with_context(
            aps_internal_create=True
        ).create({
            'plan_type': 'manufacturing',
            'warehouse_ids': [(6, 0, self.warehouse.ids)],
            'company_id': self.company.id,
            'date_end': '2026-09-01 23:59:59',
        })
        grouped = SimplePlanningEngine(plan)._sale_demand(self.warehouse)
        source_lines = grouped[product.id]['sale_lines']
        self.assertIn(before, source_lines)
        self.assertNotIn(after, source_lines)
        self.assertAlmostEqual(grouped[product.id]['sales_qty'], 5.0)

    def test_component_delete_action_exists(self):
        component = self.env['mrp.planning.production.component']
        self.assertTrue(hasattr(component, 'action_delete_component_by_id'))
        self.assertIn('is_subcontracted', component._fields)
        self.assertIn('subcontract_bom_id', component._fields)

    def test_subcontract_resolution_is_supported(self):
        field = self.env['mrp.planning.production.component']._fields[
            'supply_resolution'
        ]
        selection = field.selection
        if callable(selection):
            selection = selection(self.env)
        values = dict(selection)
        self.assertIn('subcontract', values)
        self.assertIn('move_subcontract', values)

    def test_subcontract_engine_uses_subcontract_bom_type(self):
        from ..services import component_sourcing
        source = Path(component_sourcing.__file__).read_text()
        self.assertIn("('type', '=', 'subcontract')", source)
        self.assertIn("resolution = (", source)
        self.assertIn("'move_subcontract'", source)
        self.assertIn("else 'subcontract'", source)
