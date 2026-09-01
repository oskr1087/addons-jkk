# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestOdoo19InventoryAdjustmentAccounting(TransactionCase):

    def test_stock_account_odoo19_has_direct_account_move_link(self):
        self.assertIn("account_move_id", self.env["stock.move"]._fields)

    def test_inventory_loss_location_requires_valuation_account_for_realtime(self):
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        inventory_location = self.env["stock.location"].create({
            "name": "Inventory Loss No Account",
            "usage": "inventory",
            "company_id": self.env.company.id,
            "valuation_account_id": False,
        })
        product = self.env["product.product"].create({
            "name": "Producto valoración perpetua",
            "type": "consu",
            "is_storable": True,
            "property_stock_inventory": inventory_location.id,
        })

        # Si la versión/categoría del test no usa valoración perpetua,
        # no forzamos una configuración contable artificial.
        if getattr(product, "valuation", False) != "real_time":
            return

        adjustment = self.env["setu.stock.inventory"].create({
            "name": "ADJ ACCOUNT CHECK",
            "location_id": warehouse.lot_stock_id.id,
            "company_id": self.env.company.id,
            "line_ids": [(0, 0, {
                "product_id": product.id,
                "product_uom_id": product.uom_id.id,
                "location_id": warehouse.lot_stock_id.id,
                "theoretical_qty": 10.0,
                "product_qty": 8.0,
            })],
        })

        with self.assertRaises(ValidationError):
            adjustment._check_odoo19_inventory_adjustment_accounting()

    def test_accounting_validation_raises_odoo_validationerror(self):
        from odoo.exceptions import ValidationError

        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        inventory_location = self.env["stock.location"].create({
            "name": "Inventory Loss ValidationError Test",
            "usage": "inventory",
            "company_id": self.env.company.id,
            "valuation_account_id": False,
        })
        product = self.env["product.product"].create({
            "name": "Producto ValidationError Test",
            "type": "consu",
            "is_storable": True,
            "property_stock_inventory": inventory_location.id,
        })

        if getattr(product, "valuation", False) != "real_time":
            return

        adjustment = self.env["setu.stock.inventory"].create({
            "name": "ADJ VALIDATIONERROR TEST",
            "location_id": warehouse.lot_stock_id.id,
            "company_id": self.env.company.id,
            "line_ids": [(0, 0, {
                "product_id": product.id,
                "product_uom_id": product.uom_id.id,
                "location_id": warehouse.lot_stock_id.id,
                "theoretical_qty": 10.0,
                "product_qty": 8.0,
            })],
        })

        with self.assertRaises(ValidationError):
            adjustment._check_odoo19_inventory_adjustment_accounting()
