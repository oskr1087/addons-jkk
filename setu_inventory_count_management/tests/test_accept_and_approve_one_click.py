# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestAcceptAndApproveOneClick(TransactionCase):

    def test_accept_and_approve_closes_residual_pending_review(self):
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)],
            limit=1,
        )
        location = self.env["stock.location"].create({
            "name": "One Click Approval",
            "usage": "internal",
            "location_id": warehouse.lot_stock_id.id,
            "company_id": self.env.company.id,
        })
        product = self.env["product.product"].create({
            "name": "Producto One Click",
            "type": "consu",
            "is_storable": True,
        })

        count = self.env["setu.stock.inventory.count"].with_context(
            setu_creating_recount=True,
        ).create({
            "warehouse_id": warehouse.id,
            "location_id": location.id,
            "approver_id": self.env.user.id,
            "type": "Single Session",
        })

        header = count._get_snapshot_header(create=True)
        self.env["setu.inventory.count.snapshot.line"].sudo().create({
            "snapshot_id": header.id,
            "product_id": product.id,
            "location_id": location.id,
            "expected_qty": 10.0,
            "counted_qty": 8.0,
            "difference_qty": -2.0,
            "scan_count": 1,
            "status": "difference",
            "unexpected": False,
        })
        header.write({"ready": True})

        # Simular línea legacy que quedó pendiente de una versión anterior.
        legacy = self.env["setu.stock.inventory.count.line"].create({
            "inventory_count_id": count.id,
            "product_id": product.id,
            "location_id": location.id,
            "theoretical_qty": 10.0,
            "qty_in_stock": 10.0,
            "counted_qty": 8.0,
            "state": "Pending Review",
            "is_system_generated": True,
        })

        count.write({"state": "To Be Approved"})

        count.action_accept_and_approve()

        legacy.invalidate_recordset()
        count.invalidate_recordset()

        self.assertEqual(legacy.state, "Approve")
        self.assertIn(count.state, ("Approved", "Inventory Adjusted"))
        self.assertFalse(
            count.line_ids.filtered(lambda line: line.state == "Pending Review")
        )

    def test_accept_context_resolves_last_moment_pending_review(self):
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        location = self.env["stock.location"].create({
            "name": "Last Moment Pending",
            "usage": "internal",
            "location_id": warehouse.lot_stock_id.id,
            "company_id": self.env.company.id,
        })
        product = self.env["product.product"].create({
            "name": "Producto Last Moment",
            "type": "consu",
            "is_storable": True,
        })
        count = self.env["setu.stock.inventory.count"].with_context(
            setu_creating_recount=True,
        ).create({
            "warehouse_id": warehouse.id,
            "location_id": location.id,
            "approver_id": self.env.user.id,
            "type": "Single Session",
        })
        self.env["setu.stock.inventory.count.line"].create({
            "inventory_count_id": count.id,
            "product_id": product.id,
            "location_id": location.id,
            "theoretical_qty": 10.0,
            "qty_in_stock": 10.0,
            "counted_qty": 8.0,
            "state": "Pending Review",
            "is_system_generated": True,
        })
        count.state = "To Be Approved"

        count.with_context(
            setu_accept_all_differences=True
        ).approve_inventory_count()

        self.assertFalse(
            count.line_ids.filtered(
                lambda line: line.state == "Pending Review"
            )
        )
        self.assertIn(count.state, ("Approved", "Inventory Adjusted"))

    def test_clean_snapshot_ignores_stale_pending_review(self):
        """KPI 0 diferencias debe prevalecer sobre Pending Review legacy."""
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        location = self.env["stock.location"].create({
            "name": "Snapshot Clean Legacy Pending",
            "usage": "internal",
            "location_id": warehouse.lot_stock_id.id,
            "company_id": self.env.company.id,
        })
        product = self.env["product.product"].create({
            "name": "Producto Snapshot Clean",
            "type": "consu",
            "is_storable": True,
        })

        count = self.env["setu.stock.inventory.count"].with_context(
            setu_creating_recount=True,
        ).create({
            "warehouse_id": warehouse.id,
            "location_id": location.id,
            "approver_id": self.env.user.id,
            "type": "Single Session",
        })

        header = count._get_snapshot_header(create=True)
        self.env["setu.inventory.count.snapshot.line"].sudo().create({
            "snapshot_id": header.id,
            "product_id": product.id,
            "location_id": location.id,
            "expected_qty": 10.0,
            "counted_qty": 10.0,
            "difference_qty": 0.0,
            "scan_count": 1,
            "status": "matched",
            "unexpected": False,
        })
        header.write({"ready": True})

        legacy = self.env["setu.stock.inventory.count.line"].create({
            "inventory_count_id": count.id,
            "product_id": product.id,
            "location_id": location.id,
            "theoretical_qty": 10.0,
            "qty_in_stock": 10.0,
            "counted_qty": 10.0,
            "state": "Pending Review",
            "is_system_generated": True,
        })

        count.state = "To Be Approved"
        count._refresh_persistent_kpis()

        self.assertEqual(count.adjustment_candidate_count, 0)
        self.assertEqual(count.difference_item_count, 0)

        count.action_approve_without_differences()

        legacy.invalidate_recordset(["state"])
        count.invalidate_recordset(["state"])

        self.assertEqual(legacy.state, "Approve")
        self.assertEqual(count.state, "Approved")
        self.assertFalse(count.inventory_adj_ids)
