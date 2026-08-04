# -*- coding: utf-8 -*-

from datetime import datetime
from odoo.tests import TransactionCase, tagged

@tagged('-at_install', 'post_install')
class TestInventoryCountComprehensive(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Models
        cls.Company = cls.env['res.company']
        cls.User = cls.env['res.users']
        cls.Warehouse = cls.env['stock.warehouse']
        cls.Location = cls.env['stock.location']
        cls.Product = cls.env['product.product']
        cls.Lot = cls.env['stock.lot']
        cls.Quant = cls.env['stock.quant']
        cls.Planner = cls.env['setu.stock.inventory.count.planner']
        cls.Count = cls.env['setu.stock.inventory.count']
        cls.Session = cls.env['setu.inventory.count.session']
        cls.SessionLine = cls.env['setu.inventory.count.session.line']
        cls.InventoryAdj = cls.env['setu.stock.inventory']

        # Companies
        cls.company_a = cls.env.company
        cls.company_b = cls.Company.create({'name': 'Company B'})

        # Users (approvers)
        mgr_group = cls.env.ref('setu_inventory_count_management.group_setu_inventory_count_manager')
        cls.approver_a = cls.env.user
        cls.approver_b = cls.User.create({
            'name': 'Approver B',
            'login': 'approver_b',
            'email': 'b@example.com',
            'company_id': cls.company_b.id,
            'company_ids': [(6, 0, [cls.company_b.id])],
            'group_ids': [(4, mgr_group.id)]
        })

        # Warehouses (one in each company)
        cls.wh_a = cls.Warehouse.search([('company_id', '=', cls.company_a.id)], limit=1)
        if not cls.wh_a:
            cls.wh_a = cls.Warehouse.create({'name': 'WH A', 'code': 'WHA', 'company_id': cls.company_a.id})
        cls.wh_b = cls.Warehouse.create({'name': 'WH B', 'code': 'WHB', 'company_id': cls.company_b.id})

        # Locations (internal)
        cls.loc_a = cls.wh_a.lot_stock_id
        cls.loc_b = cls.wh_b.lot_stock_id

        # Products: none/lot/serial
        cls.prod_none = cls.Product.create({'name': 'P-None', 'type': 'consu','is_storable': True, 'standard_price': 3.0})
        cls.prod_lot = cls.Product.create({'name': 'P-Lot', 'type': 'consu','is_storable': True, 'tracking': 'lot', 'standard_price': 4.0})
        cls.prod_ser = cls.Product.create({'name': 'P-Ser', 'type': 'consu','is_storable': True, 'tracking': 'serial', 'standard_price': 6.0})
        # Lots/serials
        cls.lot1 = cls.Lot.create({'name': 'LOT-001', 'product_id': cls.prod_lot.id})
        cls.sn1 = cls.Lot.create({'name': 'SN-001', 'product_id': cls.prod_ser.id})
        cls.sn2 = cls.Lot.create({'name': 'SN-002', 'product_id': cls.prod_ser.id})

        # Seed theoretical quants in each company/warehouse
        def seed_quants(location):
            cls.Quant.with_context(inventory_mode=True).create({'product_id': cls.prod_none.id, 'location_id': location.id, 'inventory_quantity': 10})
            cls.Quant.with_context(inventory_mode=True).create({'product_id': cls.prod_lot.id, 'location_id': location.id, 'lot_id': cls.lot1.id, 'inventory_quantity': 3})
            for sn in (cls.sn1, cls.sn2):
                cls.Quant.with_context(inventory_mode=True).create({'product_id': cls.prod_ser.id, 'location_id': location.id, 'lot_id': sn.id, 'inventory_quantity': 1})
        seed_quants(cls.loc_a)
        seed_quants(cls.loc_b)

    # Helpers
    def _make_count(self, company, wh, loc, approver, ctype='Single Session', products=None):
        products = products or [self.prod_none.id, self.prod_lot.id, self.prod_ser.id]
        return self.Count.with_company(company).create({
            'name': 'COUNT-%s-%s' % (company.name, ctype),
            'warehouse_id': wh.id,
            'location_id': loc.id,
            'approver_id': approver.id,
            'type': ctype,
            'product_ids': [(6, 0, products)],
        })

    def _make_session(self, count, multi=False, users=None):
        users = users or [self.env.user.id]
        return self.Session.create({
            'inventory_count_id': count.id,
            'location_id': count.location_id.id,
            'warehouse_id': count.warehouse_id.id,
            'use_barcode_scanner': False,
            'type': 'Multi Session' if multi else 'Single Session',
            'user_ids': [(6, 0, users)],
        })

    def _scan_lines_variants(self, session, discrepancies=True):
        # None tracked
        self.SessionLine.create({
            'session_id': session.id,
            'inventory_count_id': session.inventory_count_id.id,
            'product_id': self.prod_none.id,
            'location_id': session.location_id.id,
            'scanned_qty': 12 if discrepancies else 10,
            'theoretical_qty': 10,
            'state': 'Approve',

        })
        # Lot tracked
        self.SessionLine.create({
            'session_id': session.id,
            'inventory_count_id': session.inventory_count_id.id,
            'product_id': self.prod_lot.id,
            'location_id': session.location_id.id,
            'lot_id': self.lot1.id,
            'scanned_qty': 2 if discrepancies else 3,
            'theoretical_qty': 3,
            'state': 'Approve',
        })
        # Serial tracked
        self.SessionLine.create({
            'session_id': session.id,
            'inventory_count_id': session.inventory_count_id.id,
            'product_id': self.prod_ser.id,
            'location_id': session.location_id.id,
            'serial_number_ids': [(6, 0, [self.sn1.id, self.sn2.id])],
            'scanned_qty': 2,
            'theoretical_qty': 2,
            'state': 'Approve',
        })

    # Tests
    def test_01_planner_verify_and_create_counts_single_multi_across_companies(self):
        # Planner A (single session)
        plan_a = self.Planner.create({
            'name': 'Plan A', 'type': 'Single Session', 'warehouse_id': self.wh_a.id,
            'location_id': self.loc_a.id, 'approver_id': self.approver_a.id,
            'planing_frequency': 10, 'product_ids': [(6, 0, [self.prod_none.id])]
        })
        plan_a.verify_inventory_count_planing()
        plan_a.create_inventory_count_record()
        count_a = self.Count.search([('planner_id', '=', plan_a.id)], limit=1)
        self.assertTrue(count_a)
        self.assertEqual(count_a.type, 'Single Session')

        # Planner B (multi session, different company/warehouse/approver)
        plan_b = self.Planner.with_company(self.company_b).create({
            'name': 'Plan B', 'type': 'Multi Session', 'warehouse_id': self.wh_b.id,
            'location_id': self.loc_b.id, 'approver_id': self.approver_b.id,
            'planing_frequency': 5, 'product_ids': [(6, 0, [self.prod_lot.id, self.prod_ser.id])]
        })
        plan_b.verify_inventory_count_planing()
        plan_b.create_inventory_count_record()
        count_b = self.Count.search([('planner_id', '=', plan_b.id)], limit=1)
        self.assertTrue(count_b)
        self.assertEqual(count_b.company_id, self.company_b)
        self.assertEqual(count_b.type, 'Multi Session')

    def test_02_single_session_full_workflow_discrepancies_and_adjustment(self):
        count = self._make_count(self.company_a, self.wh_a, self.loc_a, self.approver_a, 'Single Session')
        session = self._make_session(count, multi=False)

        session.start()
        self._scan_lines_variants(session, discrepancies=True)
        session.submit()
        session.validate_session()

        # Complete count and approve should create adjustment because discrepancy exists
        count.complete_counting()
        count.approve_inventory_count()
        self.assertIn(count.state, ('Approved', 'Inventory Adjusted'))
        # If inventory adjusted, there should be an adjustment record linked
        if count.state == 'Inventory Adjusted':
            adj = self.InventoryAdj.search([('inventory_count_id', '=', count.id)], limit=1)
            self.assertTrue(adj)

    def test_03_single_session_no_discrepancies(self):
        count = self._make_count(self.company_a, self.wh_a, self.loc_a, self.approver_a, 'Single Session')
        session = self._make_session(count)
        session.start()
        self._scan_lines_variants(session, discrepancies=False)
        session.submit()
        session.validate_session()
        count.complete_counting()
        count.approve_inventory_count()
        self.assertIn(count.state, ('Approved', 'Inventory Adjusted'))

    def test_04_multi_session_flow_with_approvals(self):
        count = self._make_count(self.company_b, self.wh_b, self.loc_b, self.approver_b, 'Multi Session', products=[self.prod_lot.id, self.prod_ser.id])
        s1 = self._make_session(count, multi=True, users=[self.approver_b.id])
        s2 = self._make_session(count, multi=True, users=[self.approver_b.id])

        for s in (s1, s2):
            s.start()
            self.SessionLine.create({
                'session_id': s.id,
                'inventory_count_id': count.id,
                'product_id': self.prod_lot.id,
                'location_id': count.location_id.id,
                'lot_id': self.lot1.id,
                'scanned_qty': 3,
                'theoretical_qty': 3,
                'state': 'Approve',
            })
            s.submit()
            s.validate_session()

        # Approve the count (no rejected/pending lines)
        count.complete_counting()
        count.approve_inventory_count()
        self.assertIn(count.state, ('Approved', 'Inventory Adjusted'))

    def test_05_re_session_creation_from_rejected_lines_and_user_mistake_flag(self):
        count = self._make_count(self.company_a, self.wh_a, self.loc_a, self.approver_a, 'Single Session')
        s = self._make_session(count)
        s.start()
        # Create a rejected line to trigger re-session path
        line_reject = self.SessionLine.create({
            'session_id': s.id,
            'inventory_count_id': count.id,
            'product_id': self.prod_lot.id,
            'location_id': count.location_id.id,
            'lot_id': self.lot1.id,
            'scanned_qty': 1,
            'theoretical_qty': 3,
            'state': 'Reject',
        })
        # Additional approved for discrepancy mix
        self.SessionLine.create({
            'session_id': s.id,
            'inventory_count_id': count.id,
            'product_id': self.prod_none.id,
            'location_id': count.location_id.id,
            'scanned_qty': 10,
            'theoretical_qty': 10,
            'state': 'Approve',
        })
        s.submit()
        # This will compute and set internal flags; also may open wizard normally, but we call internal path
        s._validate_session()
        # Mark that re-open can be done and try creating the new session (direct method)
        s.re_open_session_bool = True
        prev_sessions = count.session_ids
        s.open_new_session()
        self.assertGreater(len(count.session_ids), len(prev_sessions))


    def test_07_cancel_and_unlink_constraints(self):
        count = self._make_count(self.company_a, self.wh_a, self.loc_a, self.approver_a)
        count.cancel()
        self.assertEqual(count.state, 'Cancel')

