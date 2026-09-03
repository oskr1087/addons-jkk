# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestCountSecurityProfiles(TransactionCase):

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
            "name": "Operador Conteo Seguridad",
            "login": "operator_count_security",
            "group_ids": [(6, 0, [cls.group_user.id])],
        })
        cls.manager = cls.env["res.users"].create({
            "name": "Controlador Conteo Seguridad",
            "login": "manager_count_security",
            "group_ids": [(6, 0, [cls.group_manager.id])],
        })
        cls.admin = cls.env["res.users"].create({
            "name": "Administrador Conteo Seguridad",
            "login": "admin_count_security",
            "group_ids": [(6, 0, [cls.group_admin.id])],
        })
        cls.other_operator = cls.env["res.users"].create({
            "name": "Operador no asignado",
            "login": "other_operator_count_security",
            "group_ids": [(6, 0, [cls.group_user.id])],
        })
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.scope = cls.env["stock.location"].create({
            "name": "SECURITY COUNT SCOPE",
            "usage": "internal",
            "location_id": cls.warehouse.lot_stock_id.id,
            "company_id": cls.env.company.id,
        })
        cls.bin = cls.env["stock.location"].create({
            "name": "SECURITY BIN",
            "usage": "internal",
            "location_id": cls.scope.id,
            "company_id": cls.env.company.id,
            "barcode": "SECURITY-BIN",
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
        cls.count.sudo()._ensure_location_progress_records()

    def test_01_operator_reads_assigned_session(self):
        self.assertTrue(
            self.session.with_user(self.operator).read(["name", "state"])
        )

    def test_02_operator_creates_own_context(self):
        context = self.session.with_user(
            self.operator
        )._get_user_scan_context(create=True)
        self.assertEqual(context.user_id, self.operator)

    def test_03_operator_cannot_read_other_context(self):
        own = self.session.with_user(
            self.operator
        )._get_user_scan_context(create=True)
        other = self.session.with_user(
            self.manager
        )._get_user_scan_context(create=True)
        self.assertTrue(own.with_user(self.operator).read(["user_id"]))
        with self.assertRaises(AccessError):
            other.with_user(self.operator).read(["user_id"])

    def test_04_operator_reads_assigned_location_progress(self):
        progress = self.count.location_progress_ids[:1]
        self.assertTrue(
            progress.with_user(self.operator).read(["location_id", "state"])
        )

    def test_05_unassigned_operator_cannot_read_progress(self):
        progress = self.count.location_progress_ids[:1]
        with self.assertRaises(AccessError):
            progress.with_user(self.other_operator).read(["location_id"])

    def test_06_operator_cannot_write_count(self):
        with self.assertRaises(AccessError):
            self.count.with_user(self.operator).write({
                "approver_id": self.operator.id
            })

    def test_07_operator_cannot_generate_internal_transfer(self):
        Issue = self.env[
            "setu.inventory.count.relocation.issue"
        ].with_user(self.operator)
        with self.assertRaises(UserError):
            Issue.browse().action_create_internal_transfer()

    def test_08_manager_can_manage_location_progress(self):
        progress = self.count.location_progress_ids[:1].with_user(self.manager)
        self.assertTrue(progress.read(["state"]))
        progress.write({"started_at": progress.started_at or False})

    def test_09_manager_sees_operator_context(self):
        self.session.with_user(
            self.operator
        )._get_user_scan_context(create=True)
        contexts = self.env[
            "setu.inventory.count.session.user.context"
        ].with_user(self.manager).search([
            ("session_id", "=", self.session.id),
        ])
        self.assertIn(self.operator, contexts.mapped("user_id"))

    def test_10_admin_acl_new_models(self):
        for model_name in (
            "setu.inventory.count.session.user.context",
            "setu.inventory.count.location.progress",
            "setu.inventory.count.relocation.issue",
            "setu.inventory.count.relocation.line",
        ):
            model = self.env[model_name].with_user(self.admin)
            for operation in ("read", "write", "create", "unlink"):
                model.check_access(operation)

    def test_11_plain_internal_user_has_no_snapshot_acl(self):
        plain = self.env["res.users"].create({
            "name": "Empleado sin Conteo",
            "login": "plain_internal_count_security",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        with self.assertRaises(AccessError):
            self.env[
                "setu.inventory.count.snapshot"
            ].with_user(plain).check_access("read")
