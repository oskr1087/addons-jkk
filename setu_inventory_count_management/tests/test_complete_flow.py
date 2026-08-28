# -*- coding: utf-8 -*-
import unittest

from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta


@tagged('post_install', '-at_install')
class TestInventoryCount(TransactionCase):

    def setUp(self):
        super(TestInventoryCount, self).setUp()
        # Create test data
        self.company = self.env['res.company'].create({'name': 'Test Company'})
        self.warehouse = self.env['stock.warehouse'].create({
            'name': 'Test Warehouse',
            'code': 'TWH'
        })
        self.location = self.env['stock.location'].create({
            'name': 'Test Location',
            'usage': 'internal',
            'location_id': self.warehouse.lot_stock_id.id
        })
        self.product = self.env['product.product'].create({
            'name': 'Test Product',
            'type': 'consu',
            'tracking': 'none'
        })
        self.user = self.env['res.users'].create({
            'name': 'Test User',
            'login': 'test_user',
            'company_id': self.company.id,
            'company_ids': [(6, 0, [self.company.id])]
        })
        self.approver = self.env['res.users'].create({
            'name': 'Approver User',
            'login': 'approver_user',
            'company_id': self.company.id,
            'company_ids': [(6, 0, [self.company.id])]
        })
        # Create main stock location (using warehouse's default stock location)
        self.stock_location = self.warehouse.lot_stock_id

        # Create products with different tracking methods
        self.product_lot = self.env['product.product'].create({
            'name': 'Lot Product',
            'type': 'consu',
            'is_storable': True,
            'tracking': 'lot',
        })

        self.product_serial = self.env['product.product'].create({
            'name': 'Serial Product',
            'type': 'consu',
            'is_storable': True,
            'tracking': 'serial',
        })

        # Create lot and serial numbers
        self.lot1 = self.env['stock.lot'].create({
            'name': 'LOT001',
            'product_id': self.product_lot.id,
            'company_id': self.company.id,
        })

        self.serial1 = self.env['stock.lot'].create({
            'name': 'SERIAL001',
            'product_id': self.product_serial.id,
            'company_id': self.company.id,
        })

        self.serial2 = self.env['stock.lot'].create({
            'name': 'SERIAL002',
            'product_id': self.product_serial.id,
            'company_id': self.company.id,
        })

        # Create additional users for sessions
        self.user1 = self.env['res.users'].create({
            'name': 'User 1',
            'login': 'user1',
            'company_id': self.company.id,
            'company_ids': [(6, 0, [self.company.id])]
        })

        self.user2 = self.env['res.users'].create({
            'name': 'User 2',
            'login': 'user2',
            'company_id': self.company.id,
            'company_ids': [(6, 0, [self.company.id])]
        })


    def test_inventory_count_creation(self):
        """Test creation of inventory count"""
        inventory_count = self.env['setu.stock.inventory.count'].create({
            'name': 'TEST001',
            'warehouse_id': self.warehouse.id,
            'location_id': self.location.id,
            'approver_id': self.approver.id,
            'type': 'Single Session'
        })
        self.assertEqual(inventory_count.state, 'Draft')

    def test_session_creation(self):
        """Test creation of inventory session"""
        inventory_count = self.env['setu.stock.inventory.count'].create({
            'name': 'TEST001',
            'warehouse_id': self.warehouse.id,
            'location_id': self.location.id,
            'approver_id': self.approver.id,
            'type': 'Single Session'
        })

        session = self.env['setu.inventory.count.session'].create({
            'name': 'SESSION001',
            'inventory_count_id': inventory_count.id,
            'location_id': self.location.id,
            'warehouse_id': self.warehouse.id
        })
        self.assertEqual(session.state, 'Draft')

    def test_session_workflow(self):
        """Test session workflow from start to submit"""
        inventory_count = self.env['setu.stock.inventory.count'].create({
            'name': 'TEST001',
            'warehouse_id': self.warehouse.id,
            'location_id': self.location.id,
            'approver_id': self.approver.id,
            'type': 'Single Session'
        })

        session = self.env['setu.inventory.count.session'].create({
            'name': 'SESSION001',
            'inventory_count_id': inventory_count.id,
            'location_id': self.location.id,
            'warehouse_id': self.warehouse.id
        })

        # Start session
        session.start()
        self.assertEqual(session.state, 'In Progress')

        # Create session line
        session_line = self.env['setu.inventory.count.session.line'].create({
            'session_id': session.id,
            'product_id': self.product.id,
            'location_id': self.location.id,
            'scanned_qty': 10,
            'product_scanned': True,
            'theoretical_qty': 10
        })

        # Submit session
        session.submit()
        self.assertEqual(session.state, 'Submitted')

    def test_barcode_scanning(self):
        """Test barcode scanning functionality"""
        inventory_count = self.env['setu.stock.inventory.count'].create({
            'name': 'TEST001',
            'warehouse_id': self.warehouse.id,
            'location_id': self.location.id,
            'approver_id': self.approver.id,
            'type': 'Single Session',
            'use_barcode_scanner': True
        })

        session = self.env['setu.inventory.count.session'].create({
            'name': 'SESSION001',
            'inventory_count_id': inventory_count.id,
            'location_id': self.location.id,
            'warehouse_id': self.warehouse.id,
            'use_barcode_scanner': True
        })

        session.start()
        # Simulate barcode scan
        session.on_barcode_scanned(self.product.barcode)

    def test_inventory_approval(self):
        """Test inventory approval process"""
        inventory_count = self.env['setu.stock.inventory.count'].create({
            'name': 'TEST001',
            'warehouse_id': self.warehouse.id,
            'location_id': self.location.id,
            'approver_id': self.approver.id,
            'type': 'Single Session'
        })

        # Complete counting and request approval
        inventory_count.complete_counting()
        self.assertEqual(inventory_count.state, 'To Be Approved')

        # Approve inventory count
        inventory_count.approve_inventory_count()
        self.assertEqual(inventory_count.state, 'Approved')

    def test_discrepancy_calculation(self):
        """Test discrepancy calculation"""
        inventory_count = self.env['setu.stock.inventory.count'].create({
            'name': 'TEST001',
            'warehouse_id': self.warehouse.id,
            'location_id': self.location.id,
            'approver_id': self.approver.id,
            'type': 'Single Session'
        })

        # Create count line with discrepancy
        count_line = self.env['setu.stock.inventory.count.line'].create({
            'inventory_count_id': inventory_count.id,
            'product_id': self.product.id,
            'location_id': self.location.id,
            'theoretical_qty': 10,
            'counted_qty': 8
        })

        self.assertTrue(count_line.is_discrepancy_found)
        self.assertEqual(count_line.difference_qty, -2)

    def test_planner_functionality(self):
        """Test inventory count planner"""
        planner = self.env['setu.stock.inventory.count.planner'].create({
            'name': 'Test Planner',
            'warehouse_id': self.warehouse.id,
            'location_id': self.location.id,
            'approver_id': self.approver.id,
            'type': 'Single Session',
            'planing_frequency': 30
        })

        # Verify planner
        planner.verify_inventory_count_planing()
        self.assertEqual(planner.state, 'verified')

        # Create inventory count from planner
        planner.create_inventory_count()

    def test_multi_session_functionality(self):
        """Test multi-session functionality"""
        inventory_count = self.env['setu.stock.inventory.count'].create({
            'name': 'TEST001',
            'warehouse_id': self.warehouse.id,
            'location_id': self.location.id,
            'approver_id': self.approver.id,
            'type': 'Multi Session'
        })

        # Create multiple sessions
        session1 = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': inventory_count.id,
            'location_id': self.location.id,
            'warehouse_id': self.warehouse.id
        })

        session2 = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': inventory_count.id,
            'location_id': self.location.id,
            'warehouse_id': self.warehouse.id
        })

        self.assertEqual(len(inventory_count.session_ids), 2)

    def test_inventory_adjustment(self):
        """Test inventory adjustment creation"""
        inventory_count = self.env['setu.stock.inventory.count'].create({
            'name': 'TEST001',
            'warehouse_id': self.warehouse.id,
            'location_id': self.location.id,
            'approver_id': self.approver.id,
            'type': 'Single Session'
        })

        # Create count line with discrepancy
        count_line = self.env['setu.stock.inventory.count.line'].create({
            'inventory_count_id': inventory_count.id,
            'product_id': self.product.id,
            'location_id': self.location.id,
            'theoretical_qty': 10,
            'counted_qty': 8,
            'state': 'Approve'
        })

        # Create inventory adjustment
        inventory_count.create_inventory_adj()
        self.assertTrue(inventory_count.inventory_adj_ids)


    def test_error_cases(self):
        """Test various error cases"""
        inventory_count = self.env['setu.stock.inventory.count'].create({
            'name': 'TEST001',
            'warehouse_id': self.warehouse.id,
            'location_id': self.location.id,
            'approver_id': self.approver.id,
            'type': 'Single Session'
        })

        # Test cannot delete non-draft inventory count
        inventory_count.state = 'In Progress'
        with self.assertRaises(ValidationError):
            inventory_count.unlink()

    def test_multi_session_rejection_resession(self):
        # Create a multi-session inventory count
        inventory_count = self.env['setu.stock.inventory.count'].create({
            'name': 'TEST/MULTI/001',
            'type': 'Multi Session',
            'warehouse_id': self.warehouse.id,
            'location_id': self.location.id,
            'approver_id': self.approver.id,
            'use_barcode_scanner': True,
        })

        session1 = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': inventory_count.id,
            'location_id': self.location.id,
            'warehouse_id': self.warehouse.id,
            'user_ids': [(6, 0, [self.user1.id])],
            'use_barcode_scanner': True,
            'type': 'Multi Session',
        })
        session2 = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': inventory_count.id,
            'location_id': self.location.id,
            'warehouse_id': self.warehouse.id,
            'user_ids': [(6, 0, [self.user2.id])],
            'use_barcode_scanner': True,
            'type': 'Multi Session',
        })

        session1.start()
        session2.start()

        session_line1 = self.env['setu.inventory.count.session.line'].create({
            'session_id': session1.id,
            'inventory_count_id': inventory_count.id,
            'product_id': self.product_lot.id,
            'location_id': self.location.id,
            'lot_id': self.lot1.id,
            'scanned_qty': 10,
            'product_scanned': True,
            'theoretical_qty': 10,
            'state': 'Approve',
        })
        session_line2 = self.env['setu.inventory.count.session.line'].create({
            'session_id': session2.id,
            'inventory_count_id': inventory_count.id,
            'product_id': self.product_serial.id,
            'location_id': self.location.id,
            'serial_number_ids': [(6, 0, [self.serial1.id, self.serial2.id])],
            'scanned_qty': 2,
            'product_scanned': True,
            'theoretical_qty': 2,
            'state': 'Reject',
        })

        session1.submit()
        session1.validate_session()
        session2.submit()
        action = session2.validate_session()
        self.assertIsInstance(action, dict)
        self.assertEqual(session2.state, 'Submitted')
        self.assertTrue(session2.re_open_session_bool)

        wiz = self.env['setu.inventory.session.validate.wizard'] \
            .with_context(active_id=session2.id) \
            .create({'session_id': session2.id, 'user_ids': [(6, 0, [self.user2.id])]})
        wiz.with_context(active_id=session2.id).create_re_session()

        resession = self.env['setu.inventory.count.session'].search(
            [('session_id', '=', session2.id)], order='id desc', limit=1
        )
        self.assertTrue(resession, "Re-session was not created")
        self.assertTrue(resession.session_line_ids, "Re-session has no lines copied from rejected ones")

        resession_line = resession.session_line_ids[0]
        if resession_line.product_id.tracking == 'none':
            resession_line.scanned_qty = max(1, resession_line.scanned_qty)
        resession_line.write({'state': 'Approve'})
        resession.submit()
        resession.validate_session()
        self.assertEqual(resession.state, 'Done')

        if inventory_count.pending_item_count:
            inventory_count.action_mark_pending_as_zero()
        inventory_count.complete_counting()
        if inventory_count.difference_item_count:
            inventory_count.action_accept_adjustment_candidates()

        # El flujo vigente no permite aprobar mientras queden líneas de
        # revisión abiertas, incluso si el snapshot ya fue aceptado.
        pending_review = inventory_count.line_ids.filtered(
            lambda line: line.state == 'Pending Review'
        )
        if pending_review:
            pending_review.write({'state': 'Approve'})

        inventory_count.approve_inventory_count()
        self.assertIn(inventory_count.state, ('Approved', 'Inventory Adjusted'))
if __name__ == '__main__':
    unittest.main()
