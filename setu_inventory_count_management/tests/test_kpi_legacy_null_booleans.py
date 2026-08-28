# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestInventoryCountKpiLegacyNullBooleans(TransactionCase):

    def test_01_expected_kpis_include_legacy_null_unexpected(self):
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)],
            limit=1,
        )
        location = self.env["stock.location"].create({
            "name": "KPI Legacy NULL",
            "usage": "internal",
            "location_id": warehouse.lot_stock_id.id,
            "company_id": self.env.company.id,
        })
        product = self.env["product.product"].create({
            "name": "Producto KPI NULL",
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
        line = self.env["setu.inventory.count.snapshot.line"].sudo().create({
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

        # Simular registro histórico de una versión que dejó NULL.
        self.env.cr.execute(
            f"UPDATE {line._table} SET unexpected = NULL WHERE id = %s",
            (line.id,),
        )
        line.invalidate_recordset(["unexpected"])

        count._refresh_persistent_kpis()
        header.invalidate_recordset()

        self.assertEqual(header.expected_item_count, 1)
        self.assertEqual(header.pending_item_count, 0)
        self.assertEqual(header.counted_item_count, 1)
        self.assertEqual(header.difference_item_count, 1)
        self.assertEqual(header.progress_percent, 100.0)
