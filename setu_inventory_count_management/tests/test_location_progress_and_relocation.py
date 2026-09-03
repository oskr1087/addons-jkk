# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestLocationProgressAndRelocation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.scope = cls.env["stock.location"].create({
            "name": "FLOW SCOPE",
            "usage": "internal",
            "location_id": cls.warehouse.lot_stock_id.id,
            "company_id": cls.env.company.id,
        })
        cls.source = cls.env["stock.location"].create({
            "name": "FLOW SOURCE",
            "usage": "internal",
            "location_id": cls.scope.id,
            "company_id": cls.env.company.id,
            "barcode": "FLOW-SOURCE",
        })
        cls.destination = cls.env["stock.location"].create({
            "name": "FLOW DESTINATION",
            "usage": "internal",
            "location_id": cls.scope.id,
            "company_id": cls.env.company.id,
            "barcode": "FLOW-DEST",
        })
        cls.product = cls.env["product.product"].create({
            "name": "Producto movimiento ubicación",
            "type": "consu",
            "is_storable": True,
            "tracking": "lot",
        })
        cls.lot = cls.env["stock.lot"].create({
            "name": "LOT-FLOW-001",
            "product_id": cls.product.id,
            "company_id": cls.env.company.id,
        })

    def _count(self):
        count = self.env["setu.stock.inventory.count"].with_context(
            setu_creating_recount=True
        ).create({
            "warehouse_id": self.warehouse.id,
            "location_id": self.scope.id,
            "approver_id": self.env.user.id,
            "type": "Single Session",
        })
        count._ensure_location_progress_records()
        return count

    def test_01_location_progress_contains_scope_locations(self):
        count = self._count()
        locations = count.location_progress_ids.mapped("location_id")
        self.assertIn(self.source, locations)
        self.assertIn(self.destination, locations)

    def test_02_location_state_started_and_finished(self):
        count = self._count()
        progress = count._location_progress(self.source)
        self.assertEqual(progress.state, "not_started")
        progress._mark_started(self.env.user)
        progress.invalidate_recordset()
        self.assertEqual(progress.state, "in_progress")
        progress._mark_finished_by(self.env.user)
        progress.invalidate_recordset()
        self.assertEqual(progress.state, "done")

    def test_03_relocated_status_is_not_adjustment_candidate(self):
        count = self._count()
        header = count._get_snapshot_header(create=True)
        line = self.env["setu.inventory.count.snapshot.line"].create({
            "snapshot_id": header.id,
            "product_id": self.product.id,
            "lot_id": self.lot.id,
            "location_id": self.destination.id,
            "expected_qty": 0.0,
            "counted_qty": 1.0,
            "difference_qty": 1.0,
            "scan_count": 1,
            "unexpected": True,
            "status": "relocated",
            "relocation_resolved": True,
        })
        self.assertTrue(line.relocation_resolved)
        self.assertNotIn(line, count._snapshot_problem_lines())
