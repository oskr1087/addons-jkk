# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestInventoryCountBatchPerformance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.location = cls.env["stock.location"].create({
            "name": "Ubicación batch performance",
            "usage": "internal",
            "location_id": cls.warehouse.lot_stock_id.id,
            "company_id": cls.env.company.id,
        })
        cls.product = cls.env["product.product"].create({
            "name": "Producto batch performance",
            "type": "consu",
            "is_storable": True,
            "tracking": "lot",
            "standard_price": 7.5,
        })
        cls.lots = cls.env["stock.lot"].create([
            {
                "name": f"BATCH-{index:03d}",
                "product_id": cls.product.id,
                "company_id": cls.env.company.id,
            }
            for index in range(1, 11)
        ])
        for lot in cls.lots:
            cls.env["stock.quant"]._update_available_quantity(
                cls.product, cls.location, 5.0, lot_id=lot
            )

    def _count_and_session(self):
        count = self.env["setu.stock.inventory.count"].create({
            "warehouse_id": self.warehouse.id,
            "location_id": self.location.id,
            "approver_id": self.env.user.id,
            "type": "Single Session",
            "use_barcode_scanner": True,
        })
        session = self.env["setu.inventory.count.session"].create({
            "inventory_count_id": count.id,
            "location_id": self.location.id,
            "warehouse_id": self.warehouse.id,
            "user_ids": [(6, 0, self.env.user.ids)],
        })
        return count, session

    def test_01_bulk_create_defers_and_flushes_snapshot_once(self):
        count, session = self._count_and_session()
        snapshots = count.snapshot_line_ids.filtered(
            lambda line: line.product_id == self.product
        )
        vals_list=[{
            "session_id":session.id,
            "inventory_count_id":count.id,
            "product_id":self.product.id,
            "location_id":self.location.id,
            "lot_id":lot.id,
            "theoretical_qty":5.0,
            "scanned_qty":5.0,
            "product_scanned":True,
        } for lot in self.lots]
        records=self.env["setu.inventory.count.session.line"].with_context(
            setu_bulk_count=True,
        ).create(vals_list)
        self.assertTrue(all(line.status=="pending" for line in snapshots))
        records._sync_persistent_count_snapshot(bulk=True)
        snapshots.invalidate_recordset()
        self.assertTrue(all(line.status=="matched" for line in snapshots))
        self.assertEqual(count.pending_item_count,0)

    def test_02_snapshot_business_keys_are_unique(self):
        count,_session=self._count_and_session()
        keys={
            (
                line.snapshot_id.id,
                line.product_id.id,
                line.location_id.id,
                line.lot_id.id if line.lot_id else False,
            )
            for line in count.snapshot_line_ids
        }
        self.assertEqual(len(keys),len(count.snapshot_line_ids))

    def test_03_composite_indexes_exist(self):
        expected={
            "setu_inv_snapshot_line_key_idx",
            "setu_inv_snapshot_line_status_idx",
            "setu_inv_snapshot_line_count_key_idx",
            "setu_inv_session_line_count_product_location_lot_idx",
            "setu_inv_session_line_session_product_location_lot_idx",
            "setu_inv_session_line_scanned_count_idx",
        }
        self.env.cr.execute(
            "SELECT indexname FROM pg_indexes WHERE indexname = ANY(%s)",
            (list(expected),),
        )
        self.assertEqual({r[0] for r in self.env.cr.fetchall()},expected)
