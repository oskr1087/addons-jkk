# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestInventoryAdjustmentAccountMoveLink(TransactionCase):

    def test_account_move_smart_button_action_without_entries(self):
        inventory = self.env["setu.stock.inventory"].create({
            "name": "ADJ TEST ACCOUNT LINK",
            "location_id": self.env["stock.warehouse"].search(
                [("company_id", "=", self.env.company.id)], limit=1
            ).lot_stock_id.id,
            "company_id": self.env.company.id,
        })
        inventory._compute_account_move_ids()
        self.assertEqual(inventory.account_move_count, 0)

        action = inventory.action_open_account_moves()
        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(action["tag"], "display_notification")

    def test_compute_account_moves_does_not_crash_without_valuation_model(self):
        inventory = self.env["setu.stock.inventory"].create({
            "name": "ADJ TEST DEFENSIVE ACCOUNT LINK",
            "location_id": self.env["stock.warehouse"].search(
                [("company_id", "=", self.env.company.id)], limit=1
            ).lot_stock_id.id,
            "company_id": self.env.company.id,
        })

        # La prueba principal es que el compute siempre pueda ejecutarse
        # sin romper la lectura del formulario.
        inventory._compute_account_move_ids()
        self.assertGreaterEqual(inventory.account_move_count, 0)
