# -*- coding: utf-8 -*-
from pathlib import Path

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestCountOperatorUIPermissions(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_user = cls.env.ref(
            "setu_inventory_count_management.group_setu_inventory_count_user"
        )
        cls.operator = cls.env["res.users"].create({
            "name": "Operador UI Conteo",
            "login": "operator_ui_count_test",
            "group_ids": [(6, 0, [cls.group_user.id])],
        })
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.count = cls.env["setu.stock.inventory.count"].sudo().with_context(
            setu_creating_recount=True
        ).create({
            "warehouse_id": cls.warehouse.id,
            "location_id": cls.warehouse.lot_stock_id.id,
            "approver_id": cls.env.user.id,
            "type": "Single Session",
        })
        cls.session = cls.env["setu.inventory.count.session"].sudo().create({
            "inventory_count_id": cls.count.id,
            "warehouse_id": cls.warehouse.id,
            "location_id": cls.warehouse.lot_stock_id.id,
            "approver_id": cls.env.user.id,
            "user_ids": [(6, 0, [cls.operator.id])],
        })

    def test_01_operator_parent_count_opens_readonly(self):
        action = self.session.with_user(self.operator).open_inventory_count()
        self.assertEqual(action["res_id"], self.count.id)
        self.assertEqual(action["flags"]["mode"], "readonly")
        self.assertFalse(action["flags"]["create"])
        self.assertFalse(action["flags"]["edit"])
        self.assertFalse(action["flags"]["delete"])

    def test_02_count_form_does_not_offer_new_inside_record(self):
        module_path = Path(__file__).resolve().parents[1]
        view = (
            module_path / "views/setu_stock_inventory_count_views.xml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '<form string="Conteo de inventario" create="0">',
            view,
        )

    def test_03_kanban_create_session_is_manager_only(self):
        module_path = Path(__file__).resolve().parents[1]
        view = (
            module_path / "views/ux_kanban_views.xml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'groups="setu_inventory_count_management.group_setu_inventory_count_manager"',
            view,
        )
