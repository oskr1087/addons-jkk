# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestLocationFirstCounting(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.scope = cls.env["stock.location"].create({
            "name": "LOC TEST SCOPE",
            "usage": "internal",
            "location_id": cls.warehouse.lot_stock_id.id,
            "company_id": cls.env.company.id,
            "barcode": "LOC-TEST-SCOPE",
        })
        cls.bin_a = cls.env["stock.location"].create({
            "name": "BIN A",
            "usage": "internal",
            "location_id": cls.scope.id,
            "company_id": cls.env.company.id,
            "barcode": "LOC-BIN-A",
        })
        cls.bin_b = cls.env["stock.location"].create({
            "name": "BIN B",
            "usage": "internal",
            "location_id": cls.scope.id,
            "company_id": cls.env.company.id,
            "barcode": "LOC-BIN-B",
        })
        cls.outside = cls.env["stock.location"].create({
            "name": "OUTSIDE BIN",
            "usage": "internal",
            "location_id": cls.warehouse.lot_stock_id.id,
            "company_id": cls.env.company.id,
            "barcode": "LOC-OUTSIDE",
        })
        cls.product = cls.env["product.product"].create({
            "name": "Producto ubicación obligatoria",
            "type": "consu",
            "is_storable": True,
            "barcode": "PROD-LOC-TEST",
        })

    def _session(self):
        count = self.env["setu.stock.inventory.count"].with_context(
            setu_creating_recount=True
        ).create({
            "warehouse_id": self.warehouse.id,
            "location_id": self.scope.id,
            "approver_id": self.env.user.id,
            "type": "Single Session",
        })
        return self.env["setu.inventory.count.session"].create({
            "inventory_count_id": count.id,
            "warehouse_id": self.warehouse.id,
            "location_id": self.scope.id,
            "use_barcode_scanner": True,
            "user_ids": [(6, 0, [self.env.user.id])],
        })

    def test_01_start_does_not_assign_location(self):
        session = self._session()
        session.start()
        self.assertFalse(session.current_scanning_location_id)

    def test_02_product_is_rejected_until_location_is_scanned(self):
        session = self._session()
        session.start()
        result = session.on_barcode_scanned(self.product.barcode)
        self.assertFalse(session.current_scanning_product_id)
        self.assertIn("ubicación", result["warning"]["message"].lower())

    def test_03_location_scan_activates_child_location(self):
        session = self._session()
        session.start()
        session.on_barcode_scanned(self.bin_a.barcode)
        self.assertEqual(session.current_scanning_location_id, self.bin_a)

    def test_04_location_outside_scope_is_blocked(self):
        session = self._session()
        session.start()
        with self.assertRaises(UserError):
            session.on_barcode_scanned(self.outside.barcode)

    def test_05_scanning_new_location_switches_context_and_clears_item(self):
        session = self._session()
        session.start()
        session.on_barcode_scanned(self.bin_a.barcode)
        session.on_barcode_scanned(self.product.barcode)
        self.assertEqual(session.current_scanning_product_id, self.product)

        session.on_barcode_scanned(self.bin_b.barcode)
        self.assertEqual(session.current_scanning_location_id, self.bin_b)
        self.assertFalse(session.current_scanning_product_id)
        self.assertFalse(session.current_scanning_lot_id)

    def test_06_snapshot_key_keeps_locations_separate(self):
        count = self.env["setu.stock.inventory.count"].with_context(
            setu_creating_recount=True
        ).create({
            "warehouse_id": self.warehouse.id,
            "location_id": self.scope.id,
            "approver_id": self.env.user.id,
            "type": "Single Session",
        })
        header = count._get_snapshot_header(create=True)
        Snapshot = self.env["setu.inventory.count.snapshot.line"].sudo()

        a = Snapshot.create({
            "snapshot_id": header.id,
            "product_id": self.product.id,
            "location_id": self.bin_a.id,
            "expected_qty": 10,
            "counted_qty": 0,
            "difference_qty": -10,
            "status": "pending",
        })
        b = Snapshot.create({
            "snapshot_id": header.id,
            "product_id": self.product.id,
            "location_id": self.bin_b.id,
            "expected_qty": 0,
            "counted_qty": 10,
            "difference_qty": 10,
            "unexpected": True,
            "status": "unexpected",
        })

        self.assertNotEqual(a.location_id, b.location_id)
        self.assertEqual(a.status, "pending")
        self.assertEqual(b.status, "unexpected")
