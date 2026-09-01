# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSnapshotTabFilters(TransactionCase):

    def test_01_pending_field_has_orm_domain(self):
        field = self.env["setu.stock.inventory.count"]._fields[
            "snapshot_pending_line_ids"
        ]
        self.assertEqual(field.domain, [("status", "=", "pending")])

    def test_02_to_resolve_field_has_orm_domain(self):
        field = self.env["setu.stock.inventory.count"]._fields[
            "snapshot_to_resolve_line_ids"
        ]
        self.assertEqual(
            field.domain,
            [("status", "in", ("difference", "zero", "unexpected", "duplicate"))],
        )

    def test_03_form_uses_distinct_x2many_fields(self):
        view = self.env.ref(
            "setu_inventory_count_management."
            "setu_stock_inventory_count_snapshot_form_extension"
        )
        arch = view.arch_db
        self.assertIn("snapshot_pending_line_ids", arch)
        self.assertIn("snapshot_to_resolve_line_ids", arch)

    def test_05_pending_domain_means_not_scanned(self):
        field = self.env["setu.stock.inventory.count"]._fields[
            "snapshot_pending_line_ids"
        ]
        self.assertIn(("status", "=", "pending"), field.domain)
        self.assertIn(("scan_count", "=", 0), field.domain)
        self.assertIn(("closed_as_zero", "=", False), field.domain)
