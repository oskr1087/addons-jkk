# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestAdminApproverCandidates(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin_group = cls.env.ref(
            "setu_inventory_count_management.group_setu_inventory_count_admin"
        )
        cls.admin_user = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Administrador Conteo Test",
            "login": "admin_count_test",
            "email": "admin_count_test@example.com",
            "company_id": cls.env.company.id,
            "company_ids": [(6, 0, [cls.env.company.id])],
            # Intentionally assign ONLY the admin profile explicitly.
            "group_ids": [(6, 0, [cls.admin_group.id])],
        })

    def test_01_admin_is_valid_count_approver(self):
        Count = self.env["setu.stock.inventory.count"].with_user(self.admin_user)
        candidates = Count._get_approver_candidates(self.env.company)
        self.assertIn(
            self.admin_user,
            candidates,
            "An inventory-count administrator must be selectable as controller.",
        )

    def test_02_admin_is_default_approver_for_own_count(self):
        Count = self.env["setu.stock.inventory.count"].with_user(self.admin_user)
        self.assertEqual(Count._default_approver(), self.admin_user.id)

    def test_03_admin_is_valid_planner_approver(self):
        Planner = self.env["setu.stock.inventory.count.planner"].with_user(self.admin_user)
        candidates = Planner._get_approver_candidates(self.env.company)
        self.assertIn(
            self.admin_user,
            candidates,
            "An inventory-count administrator must be selectable in the planner.",
        )
