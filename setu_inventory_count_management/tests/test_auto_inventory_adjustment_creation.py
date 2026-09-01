# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestAutomaticInventoryAdjustmentCreation(TransactionCase):

    def test_accepted_snapshot_difference_creates_adjustment_on_approval(self):
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        location = self.env["stock.location"].create({
            "name": "Auto ADJ Test",
            "usage": "internal",
            "location_id": warehouse.lot_stock_id.id,
            "company_id": self.env.company.id,
        })
        product = self.env["product.product"].create({
            "name": "Producto Auto ADJ",
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
        count.write({"state": "To Be Approved"})

        # La acción visible al usuario debe resolver y aprobar en un solo paso.
        count.action_accept_and_approve()
        line = count.line_ids.filtered(lambda l: l.product_id == product)[:1]
        self.assertTrue(line)
        self.assertEqual(line.state, "Approve")
        self.assertEqual(line.qty_in_stock, 10.0)
        self.assertEqual(line.counted_qty, 8.0)

        self.assertEqual(count.state, "Approved")
        self.assertTrue(count.inventory_adj_ids)
        adjustment = count.inventory_adj_ids[:1]
        self.assertEqual(adjustment.state, "confirm")
        self.assertTrue(adjustment.line_ids)
