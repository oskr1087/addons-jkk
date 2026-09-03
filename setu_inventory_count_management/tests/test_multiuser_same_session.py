# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestMultiUserSameSession(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group = cls.env.ref(
            "setu_inventory_count_management.group_setu_inventory_count_user"
        )
        cls.user_a = cls.env["res.users"].create({
            "name": "Contador A",
            "login": "contador_a_location_test",
            "group_ids": [(6, 0, [cls.group.id])],
        })
        cls.user_b = cls.env["res.users"].create({
            "name": "Contador B",
            "login": "contador_b_location_test",
            "group_ids": [(6, 0, [cls.group.id])],
        })

        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.scope = cls.env["stock.location"].create({
            "name": "MULTIUSER SCOPE",
            "usage": "internal",
            "location_id": cls.warehouse.lot_stock_id.id,
            "company_id": cls.env.company.id,
        })
        cls.loc_a = cls.env["stock.location"].create({
            "name": "MULTIUSER A",
            "usage": "internal",
            "location_id": cls.scope.id,
            "company_id": cls.env.company.id,
            "barcode": "MULTIUSER-LOC-A",
        })
        cls.loc_b = cls.env["stock.location"].create({
            "name": "MULTIUSER B",
            "usage": "internal",
            "location_id": cls.scope.id,
            "company_id": cls.env.company.id,
            "barcode": "MULTIUSER-LOC-B",
        })

        cls.count = cls.env["setu.stock.inventory.count"].with_context(
            setu_creating_recount=True
        ).create({
            "warehouse_id": cls.warehouse.id,
            "location_id": cls.scope.id,
            "approver_id": cls.env.user.id,
            "type": "Single Session",
        })
        cls.session = cls.env["setu.inventory.count.session"].create({
            "inventory_count_id": cls.count.id,
            "warehouse_id": cls.warehouse.id,
            "location_id": cls.scope.id,
            "use_barcode_scanner": True,
            "user_ids": [(6, 0, [cls.user_a.id, cls.user_b.id])],
            "state": "In Progress",
            "current_state": "Start",
        })

    def test_01_each_user_has_independent_active_location(self):
        session_a = self.session.with_user(self.user_a)
        session_b = self.session.with_user(self.user_b)

        session_a.on_barcode_scanned(self.loc_a.barcode)
        session_b.on_barcode_scanned(self.loc_b.barcode)

        session_a.invalidate_recordset()
        session_b.invalidate_recordset()

        self.assertEqual(
            session_a.current_scanning_location_id,
            self.loc_a,
        )
        self.assertEqual(
            session_b.current_scanning_location_id,
            self.loc_b,
        )

    def test_02_user_change_location_does_not_touch_other_user(self):
        session_a = self.session.with_user(self.user_a)
        session_b = self.session.with_user(self.user_b)

        session_a.on_barcode_scanned(self.loc_a.barcode)
        session_b.on_barcode_scanned(self.loc_b.barcode)

        session_a.on_barcode_scanned(self.loc_b.barcode)

        session_a.invalidate_recordset()
        session_b.invalidate_recordset()

        self.assertEqual(session_a.current_scanning_location_id, self.loc_b)
        self.assertEqual(session_b.current_scanning_location_id, self.loc_b)

        contexts = self.env[
            "setu.inventory.count.session.user.context"
        ].sudo().search([
            ("session_id", "=", self.session.id),
        ])
        self.assertEqual(len(contexts), 2)
        self.assertEqual(set(contexts.mapped("user_id")), {self.user_a, self.user_b})

    def test_03_context_unique_per_session_and_user(self):
        Context = self.env[
            "setu.inventory.count.session.user.context"
        ].sudo()
        self.session.with_user(self.user_a)._get_user_scan_context(create=True)
        self.session.with_user(self.user_a)._get_user_scan_context(create=True)

        self.assertEqual(
            Context.search_count([
                ("session_id", "=", self.session.id),
                ("user_id", "=", self.user_a.id),
            ]),
            1,
        )

    def test_04_user_pause_is_independent(self):
        session_a = self.session.with_user(self.user_a)
        session_b = self.session.with_user(self.user_b)

        session_a.pda_fast_control("pause")

        ctx_a = session_a._get_user_scan_context(create=True)
        ctx_b = session_b._get_user_scan_context(create=True)
        self.assertTrue(ctx_a.paused)
        self.assertFalse(ctx_b.paused)
        self.assertEqual(self.session.state, "In Progress")
