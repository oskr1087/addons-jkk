# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestWarehouseAdminLock(TransactionCase):

    def test_01_non_admin_cannot_change_manual_lock(self):
        user = self.env["res.users"].create({
            "name": "Operador bloqueo",
            "login": "operador_lock_test",
            "group_ids": [(6, 0, [
                self.env.ref("setu_inventory_count_management.group_setu_inventory_count_user").id
            ])],
        })
        Count = self.env["setu.stock.inventory.count"].with_user(user)
        with self.assertRaises(ValidationError):
            Count._check_warehouse_lock_admin()

    def test_02_manual_override_prevents_automatic_relock(self):
        count = self.env["setu.stock.inventory.count"].search([
            ("state", "in", ["In Progress", "To Be Approved"]),
            ("warehouse_id", "!=", False),
        ], limit=1)
        if not count:
            self.skipTest("No hay conteo activo para probar el override.")

        count.with_context(setu_admin_lock_change=True).write({
            "warehouse_lock_manual_disabled": True,
        })
        count._release_warehouse_lock()
        count._activate_warehouse_lock()
        self.assertFalse(count._warehouse_lock_record())

        count.with_context(setu_admin_lock_change=True).write({
            "warehouse_lock_manual_disabled": False,
        })
        count.with_context(force_warehouse_lock=True)._activate_warehouse_lock()
        self.assertTrue(count._warehouse_lock_record())
