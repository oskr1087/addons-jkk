# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestInventoryAdjustmentAccountingFlow(TransactionCase):

    def _inventory(self):
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        location = self.env["stock.location"].create({
            "name": "Adjustment Accounting Test",
            "usage": "internal",
            "location_id": warehouse.lot_stock_id.id,
            "company_id": self.env.company.id,
        })
        product = self.env["product.product"].create({
            "name": "Producto Ajuste Contable",
            "type": "consu",
            "is_storable": True,
        })
        inventory = self.env["setu.stock.inventory"].create({
            "name": "ADJ TEST ACCOUNTING",
            "location_id": location.id,
            "company_id": self.env.company.id,
            "line_ids": [(0, 0, {
                "product_id": product.id,
                "product_uom_id": product.uom_id.id,
                "location_id": location.id,
                "theoretical_qty": 0.0,
                "product_qty": 5.0,
            })],
        })
        inventory.action_start()
        return inventory

    def test_01_manual_validate_always_applies_inventory(self):
        inventory = self._inventory()
        self.env["ir.config_parameter"].sudo().set_param(
            "setu_inventory_count_management.auto_inventory_adjustment",
            False,
        )

        Quant = type(self.env["stock.quant"])
        original = Quant.action_apply_inventory
        calls = []

        def tracked_apply(recordset, *args, **kwargs):
            calls.append(recordset.ids)
            return original(recordset, *args, **kwargs)

        with patch.object(Quant, "action_apply_inventory", tracked_apply):
            inventory.action_validate()

        self.assertEqual(inventory.state, "done")
        self.assertTrue(calls, "Validar debe ejecutar action_apply_inventory aunque el modo automático esté desactivado.")

    def test_02_validate_generates_stock_moves(self):
        inventory = self._inventory()
        inventory.action_validate()
        self.assertEqual(inventory.state, "done")
        self.assertTrue(inventory.move_ids, "El ajuste validado debe generar movimientos de stock.")
        self.assertTrue(inventory.move_ids.filtered(lambda move: move.state == "done"))
