# -*- coding: utf-8 -*-
from pathlib import Path

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestPermissionViewAlignment(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_user = cls.env.ref(
            "setu_inventory_count_management.group_setu_inventory_count_user"
        )
        cls.group_manager = cls.env.ref(
            "setu_inventory_count_management.group_setu_inventory_count_manager"
        )
        cls.group_admin = cls.env.ref(
            "setu_inventory_count_management.group_setu_inventory_count_admin"
        )

        cls.operator = cls.env["res.users"].create({
            "name": "Operador Alineación",
            "login": "operator_permission_alignment",
            "group_ids": [(6, 0, [cls.group_user.id])],
        })
        cls.manager = cls.env["res.users"].create({
            "name": "Controlador Alineación",
            "login": "manager_permission_alignment",
            "group_ids": [(6, 0, [cls.group_manager.id])],
        })
        cls.admin = cls.env["res.users"].create({
            "name": "Administrador Alineación",
            "login": "admin_permission_alignment",
            "group_ids": [(6, 0, [cls.group_admin.id])],
        })

        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.scope = cls.env["stock.location"].create({
            "name": "ALIGNMENT SCOPE",
            "usage": "internal",
            "location_id": cls.warehouse.lot_stock_id.id,
            "company_id": cls.env.company.id,
        })
        cls.count = cls.env["setu.stock.inventory.count"].sudo().with_context(
            setu_creating_recount=True
        ).create({
            "warehouse_id": cls.warehouse.id,
            "location_id": cls.scope.id,
            "approver_id": cls.manager.id,
            "type": "Single Session",
        })
        cls.session = cls.env["setu.inventory.count.session"].sudo().create({
            "inventory_count_id": cls.count.id,
            "warehouse_id": cls.warehouse.id,
            "location_id": cls.scope.id,
            "approver_id": cls.manager.id,
            "user_ids": [(6, 0, [cls.operator.id])],
            "use_barcode_scanner": True,
        })

    def test_01_operator_count_acl_is_read_only(self):
        Count = self.env["setu.stock.inventory.count"].with_user(self.operator)
        Count.check_access("read")
        for operation in ("write", "create", "unlink"):
            with self.assertRaises(AccessError):
                Count.check_access(operation)

    def test_02_operator_session_acl_matches_execution(self):
        Session = self.env["setu.inventory.count.session"].with_user(self.operator)
        Session.check_access("read")
        Session.check_access("write")
        with self.assertRaises(AccessError):
            Session.check_access("create")
        with self.assertRaises(AccessError):
            Session.check_access("unlink")

    def test_03_operator_cannot_reconfigure_session(self):
        session = self.session.with_user(self.operator)
        for values in (
            {"user_ids": [(6, 0, [self.operator.id])]},
            {"location_id": self.scope.id},
            {"warehouse_id": self.warehouse.id},
            {"approver_id": self.operator.id},
            {"type": "Single Session"},
        ):
            with self.assertRaises(AccessError):
                session.write(values)

    def test_04_manager_can_reconfigure_draft_session(self):
        session = self.session.with_user(self.manager)
        session.write({"user_ids": [(6, 0, [self.operator.id])]})
        self.assertIn(self.operator, session.user_ids)

    def test_05_operator_cannot_delete_physical_lines(self):
        Line = self.env[
            "setu.inventory.count.session.line"
        ].with_user(self.operator)
        with self.assertRaises(AccessError):
            Line.check_access("unlink")

    def test_06_manager_count_acl_is_full(self):
        Count = self.env["setu.stock.inventory.count"].with_user(self.manager)
        for operation in ("read", "write", "create", "unlink"):
            Count.check_access(operation)

    def test_07_admin_inherits_manager_and_user(self):
        self.assertTrue(
            self.admin.has_group("setu_inventory_count_management.group_setu_inventory_count_user")
        )
        self.assertTrue(
            self.admin.has_group("setu_inventory_count_management.group_setu_inventory_count_manager")
        )
        self.assertTrue(
            self.admin.has_group("setu_inventory_count_management.group_setu_inventory_count_admin")
        )

    def test_08_session_xml_has_no_delete_for_scan_lines(self):
        module_path = Path(__file__).resolve().parents[1]
        xml = (
            module_path / "views/setu_inventory_count_session_views.xml"
        ).read_text(encoding="utf-8")
        self.assertNotIn('delete="true" editable="bottom"', xml)
        self.assertIn('delete="false" editable="bottom"', xml)

    def test_09_menu_profile_groups_are_explicit(self):
        module_path = Path(__file__).resolve().parents[1]
        count_xml = (
            module_path / "views/setu_stock_inventory_count_views.xml"
        ).read_text(encoding="utf-8")
        session_xml = (
            module_path / "views/setu_inventory_count_session_views.xml"
        ).read_text(encoding="utf-8")
        settings_xml = (
            module_path / "views/res_config_settings_views.xml"
        ).read_text(encoding="utf-8")

        self.assertIn('id="setu_inventory_count_root"', count_xml)
        self.assertIn('groups="setu_inventory_count_management.group_setu_inventory_count_user"', count_xml)
        self.assertIn('id="inventory_count_session_menu"', session_xml)
        self.assertIn('groups="setu_inventory_count_management.group_setu_inventory_count_user"', session_xml)
        self.assertIn('groups="setu_inventory_count_management.group_setu_inventory_count_admin"', settings_xml)
