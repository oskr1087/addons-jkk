# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestInventoryCountEnhancements(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1)
        cls.product = cls.env['product.product'].create({
            'name': 'Enhanced Count Product',
            'type': 'consu',
            'is_storable': True,
            'barcode': 'ENH-COUNT-001',
            'standard_price': 10.0,
        })
        cls.manager = cls.env.user

    def _count(self, **extra):
        vals = {
            'name': 'COUNT-ENH',
            'warehouse_id': self.warehouse.id,
            'location_id': self.warehouse.lot_stock_id.id,
            'approver_id': self.manager.id,
            'type': 'Single Session',
            'product_ids': [(6, 0, self.product.ids)],
        }
        vals.update(extra)
        return self.env['setu.stock.inventory.count'].create(vals)

    def test_negative_tolerance_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._count(tolerance_mode='quantity', tolerance_quantity=-1)

    def test_quantity_tolerance_and_classification(self):
        count = self._count(tolerance_mode='quantity', tolerance_quantity=2)
        line = self.env['setu.stock.inventory.count.line'].create({
            'inventory_count_id': count.id,
            'product_id': self.product.id,
            'location_id': count.location_id.id,
            'theoretical_qty': 10,
            'qty_in_stock': 10,
            'counted_qty': 9,
        })
        self.assertEqual(line.discrepancy_type, 'shortage')
        self.assertTrue(line.within_tolerance)

    def test_scanner_source_is_recorded(self):
        count = self._count(use_barcode_scanner=True)
        session = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': count.id,
            'location_id': count.location_id.id,
            'warehouse_id': count.warehouse_id.id,
            'user_ids': [(6, 0, self.manager.ids)],
        })
        line = self.env['setu.inventory.count.session.line'].with_context(setu_scan_capture=True).create({
            'session_id': session.id,
            'inventory_count_id': count.id,
            'product_id': self.product.id,
            'location_id': count.location_id.id,
            'scanned_qty': 1,
        })
        self.assertEqual(line.capture_source, 'scanner')

    def test_manual_quantity_change_is_audited(self):
        count = self._count()
        session = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': count.id,
            'location_id': count.location_id.id,
            'warehouse_id': count.warehouse_id.id,
            'user_ids': [(6, 0, self.manager.ids)],
        })
        line = self.env['setu.inventory.count.session.line'].create({
            'session_id': session.id,
            'inventory_count_id': count.id,
            'product_id': self.product.id,
            'location_id': count.location_id.id,
            'scanned_qty': 1,
        })
        line.scanned_qty = 2
        self.assertEqual(line.manual_edit_count, 1)
        self.assertEqual(line.last_manual_edit_by, self.manager)

    def test_adjustment_generation_is_idempotent(self):
        count = self._count()
        self.env['setu.stock.inventory'].create({
            'name': 'Existing ADJ',
            'inventory_count_id': count.id,
            'location_id': count.location_id.id,
            'date': count.inventory_count_date,
        })
        with self.assertRaises(UserError):
            count.create_inventory_adj()

    def test_mobile_quantity_sets_physical_qty_and_keeps_location(self):
        count = self._count(use_barcode_scanner=True)
        session = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': count.id,
            'location_id': count.location_id.id,
            'warehouse_id': count.warehouse_id.id,
            'user_ids': [(6, 0, self.manager.ids)],
            'current_state': 'Start',
            'state': 'In Progress',
            'current_scanning_location_id': count.location_id.id,
            'current_scanning_product_id': self.product.id,
            'mobile_count_qty': 48,
        })
        session.action_mobile_confirm_qty()
        line = session.session_line_ids.filtered(lambda l: l.product_id == self.product)
        self.assertEqual(len(line), 1)
        self.assertEqual(line.scanned_qty, 48)
        self.assertTrue(line.product_scanned)
        self.assertEqual(session.current_scanning_location_id, count.location_id)
        self.assertFalse(session.current_scanning_product_id)
        self.assertEqual(session.mobile_count_qty, 1)

    def test_mobile_clear_location_resets_item_context(self):
        count = self._count(use_barcode_scanner=True)
        session = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': count.id,
            'location_id': count.location_id.id,
            'warehouse_id': count.warehouse_id.id,
            'user_ids': [(6, 0, self.manager.ids)],
            'current_scanning_location_id': count.location_id.id,
            'current_scanning_product_id': self.product.id,
            'mobile_count_qty': 10,
        })
        session.action_mobile_clear_location()
        self.assertFalse(session.current_scanning_location_id)
        self.assertFalse(session.current_scanning_product_id)
        self.assertEqual(session.mobile_count_qty, 1)

    def test_mobile_uses_count_location_without_rescanning(self):
        count = self._count(use_barcode_scanner=True)
        session = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': count.id,
            'location_id': count.location_id.id,
            'warehouse_id': count.warehouse_id.id,
            'user_ids': [(6, 0, self.manager.ids)],
        })
        session.current_scanning_location_id = False

        action = session.action_open_mobile_count()

        self.assertEqual(session.current_scanning_location_id, count.location_id)
        self.assertEqual(action['view_mode'], 'form')
        session.current_state = 'Start'
        session._compute_mobile_status()
        self.assertIn('producto', session.mobile_instruction.lower())
        self.assertNotIn('ubicación', session.mobile_instruction.lower())

    def test_count_sessions_smart_button_always_opens_kanban(self):
        count = self._count()
        session = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': count.id,
            'location_id': count.location_id.id,
            'warehouse_id': count.warehouse_id.id,
            'user_ids': [(6, 0, self.manager.ids)],
        })

        action = count.action_open_sessions()

        self.assertEqual(action['view_mode'], 'kanban,list,form')
        self.assertEqual(action['views'][0][1], 'kanban')
        self.assertEqual(action['domain'], [('id', 'in', session.ids)])
        self.assertFalse(action.get('res_id'))

    def test_pda_product_scan_selects_without_incrementing_quantity(self):
        count = self._count(use_barcode_scanner=True)
        session = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': count.id,
            'location_id': count.location_id.id,
            'warehouse_id': count.warehouse_id.id,
            'user_ids': [(6, 0, self.manager.ids)],
            'current_state': 'Start',
            'state': 'In Progress',
            'current_scanning_location_id': count.location_id.id,
        })
        line = self.env['setu.inventory.count.session.line'].create({
            'session_id': session.id,
            'inventory_count_id': count.id,
            'product_id': self.product.id,
            'location_id': count.location_id.id,
            'is_system_generated': True,
            'is_expected_snapshot': True,
            'scanned_qty': 0,
        })

        session.on_barcode_scanned(self.product.barcode)

        self.assertEqual(session.current_scanning_product_id, self.product)
        self.assertEqual(line.scanned_qty, 0)
        self.assertEqual(line.pda_status, 'pending')


    def test_phone_simulation_uses_same_pda_barcode_flow(self):
        count = self._count(use_barcode_scanner=True)
        session = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': count.id,
            'location_id': count.location_id.id,
            'warehouse_id': count.warehouse_id.id,
            'user_ids': [(6, 0, self.manager.ids)],
            'current_state': 'Start',
            'state': 'In Progress',
            'current_scanning_location_id': count.location_id.id,
            'mobile_simulation_mode': True,
            'mobile_simulated_barcode': self.product.barcode,
        })

        session.action_mobile_simulate_barcode()

        self.assertEqual(session.current_scanning_product_id, self.product)
        self.assertFalse(session.mobile_simulated_barcode)
        self.assertTrue(session.mobile_last_feedback)
        self.assertEqual(session.mobile_last_feedback_type, 'info')

    def test_mobile_quantity_shortcuts(self):
        count = self._count(use_barcode_scanner=True)
        session = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': count.id,
            'location_id': count.location_id.id,
            'warehouse_id': count.warehouse_id.id,
            'user_ids': [(6, 0, self.manager.ids)],
            'mobile_count_qty': 2,
        })

        session.action_mobile_qty_plus()
        self.assertEqual(session.mobile_count_qty, 3)
        session.action_mobile_qty_minus()
        self.assertEqual(session.mobile_count_qty, 2)
        session.action_mobile_qty_zero()
        self.assertEqual(session.mobile_count_qty, 0)
        session.action_mobile_qty_minus()
        self.assertEqual(session.mobile_count_qty, 0)

    def test_create_session_does_not_require_count_products(self):
        count = self._count()
        count.product_ids = [(5, 0, 0)]

        action = count.create_session()
        wizard = self.env['setu.inventory.session.creator'].browse(action['res_id'])

        self.assertFalse(count.product_ids)
        self.assertFalse(wizard.product_ids)
        self.assertEqual(wizard.inventory_count_id, count)

    def test_pda_session_creation_is_lightweight_and_empty(self):
        count = self._count()
        count.product_ids = [(5, 0, 0)]

        action = count.create_session()
        wizard = self.env['setu.inventory.session.creator'].browse(action['res_id'])
        wizard.user_ids = [(6, 0, self.manager.ids)]
        result = wizard.confirm()

        session = self.env['setu.inventory.count.session'].search([
            ('inventory_count_id', '=', count.id),
            ('state', '!=', 'Cancel'),
        ], limit=1)
        self.assertTrue(session)
        self.assertFalse(session.session_line_ids)
        self.assertEqual(result['res_id'], session.id)

    def test_controller_candidates_are_dynamic_and_include_current_manager(self):
        count = self._count()
        count._compute_approver_id()

        self.assertIn(self.manager, count.approver_ids)
        self.assertEqual(count.approver_id, self.manager)
        self.assertFalse(
            self.env['setu.stock.inventory.count']._fields['approver_ids'].store
        )

    def test_new_count_recovers_controller_when_not_explicitly_provided(self):
        count = self.env['setu.stock.inventory.count'].create({
            'warehouse_id': self.warehouse.id,
            'location_id': self.warehouse.lot_stock_id.id,
            'type': 'Single Session',
        })

        self.assertTrue(count.approver_id)
        self.assertIn(count.approver_id, count.approver_ids)

    def test_planner_controller_candidates_are_dynamic(self):
        planner = self.env['setu.stock.inventory.count.planner'].create({
            'name': 'PLAN-CONTROLLER',
            'warehouse_id': self.warehouse.id,
            'location_id': self.warehouse.lot_stock_id.id,
            'planing_frequency': 30,
        })
        planner._compute_approver_id()

        self.assertIn(self.manager, planner.approver_ids)
        self.assertTrue(planner.approver_id)
        self.assertFalse(
            self.env['setu.stock.inventory.count.planner']._fields['approver_ids'].store
        )

    def test_mobile_count_opens_fast_client_action(self):
        count = self._count(use_barcode_scanner=True)
        session = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': count.id,
            'location_id': count.location_id.id,
            'warehouse_id': count.warehouse_id.id,
            'user_ids': [(6, 0, self.manager.ids)],
        })

        action = session.action_open_mobile_count()

        self.assertEqual(action['type'], 'ir.actions.client')
        self.assertEqual(
            action['tag'],
            'setu_inventory_count_management.pda_fast_count',
        )
        self.assertEqual(action['params']['session_id'], session.id)

    def test_fast_pda_scan_returns_state_not_reload_action(self):
        count = self._count(use_barcode_scanner=True)
        session = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': count.id,
            'location_id': count.location_id.id,
            'warehouse_id': count.warehouse_id.id,
            'user_ids': [(6, 0, self.manager.ids)],
            'current_state': 'Start',
            'state': 'In Progress',
            'current_scanning_location_id': count.location_id.id,
        })

        state = session.pda_fast_scan(self.product.barcode)

        self.assertEqual(state['product']['id'], self.product.id)
        self.assertTrue(state['can_set_qty'])
        self.assertNotIn('type', state)
        self.assertNotIn('tag', state)

    def test_fast_pda_confirm_quantity_returns_incremental_state(self):
        count = self._count(use_barcode_scanner=True)
        session = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': count.id,
            'location_id': count.location_id.id,
            'warehouse_id': count.warehouse_id.id,
            'user_ids': [(6, 0, self.manager.ids)],
            'current_state': 'Start',
            'state': 'In Progress',
            'current_scanning_location_id': count.location_id.id,
            'current_scanning_product_id': self.product.id,
        })

        state = session.pda_fast_confirm_qty(7)

        self.assertFalse(state['product'])
        self.assertEqual(state['counted'], 1)
        self.assertEqual(state['recent'][0]['qty'], 7)
        self.assertEqual(state['feedback_type'], 'success')

    def test_count_kanban_computes_support_multiple_records(self):
        count_1 = self._count()
        count_2 = self._count()
        counts = count_1 | count_2

        counts._compute_create_session_bool()
        counts._compute_create_count_bool()

        self.assertEqual(len(counts), 2)
        self.assertTrue(all(isinstance(value, bool) for value in counts.mapped('create_session_bool')))

    def test_session_kanban_computes_support_multiple_records(self):
        count = self._count()
        session_1 = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': count.id,
            'location_id': count.location_id.id,
            'warehouse_id': count.warehouse_id.id,
            'user_ids': [(6, 0, self.manager.ids)],
        })
        session_2 = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': count.id,
            'location_id': count.location_id.id,
            'warehouse_id': count.warehouse_id.id,
            'user_ids': [(6, 0, self.manager.ids)],
        })
        sessions = session_1 | session_2

        sessions._compute_child_session_ids()
        sessions._compute_session_history_count()
        sessions._compute_re_open_session()

        self.assertEqual(len(sessions), 2)

    def _qr_lot_fixture(self):
        product = self.env['product.product'].create({
            'name': 'Producto QR por lote',
            'type': 'consu',
            'is_storable': True,
            'default_code': 'QR-PROD-001',
            'barcode': '7500000000001',
            'tracking': 'lot',
        })
        lot = self.env['stock.lot'].create({
            'name': 'LOT-QR-001',
            'product_id': product.id,
            'company_id': self.company.id,
        })
        return product, lot

    def test_qr_article_lot_quantity_loads_in_one_scan(self):
        product, lot = self._qr_lot_fixture()
        count = self._count(use_barcode_scanner=True)
        session = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': count.id,
            'location_id': count.location_id.id,
            'warehouse_id': count.warehouse_id.id,
            'user_ids': [(6, 0, self.manager.ids)],
            'current_state': 'Start',
            'state': 'In Progress',
            'current_scanning_location_id': count.location_id.id,
        })

        state = session.pda_fast_scan('QR-PROD-001/LOT-QR-001/47.70')

        self.assertEqual(session.current_scanning_product_id, product)
        self.assertEqual(session.current_scanning_lot_id, lot)
        self.assertEqual(session.mobile_count_qty, 47.70)
        self.assertTrue(session.mobile_qr_detected)
        self.assertEqual(session.mobile_qr_quantity, 47.70)
        self.assertTrue(state['qr_detected'])
        self.assertEqual(state['product']['id'], product.id)
        self.assertEqual(state['lot']['id'], lot.id)
        self.assertEqual(state['qty'], 47.70)

    def test_qr_can_find_product_by_barcode(self):
        product, lot = self._qr_lot_fixture()
        count = self._count(use_barcode_scanner=True)
        session = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': count.id,
            'location_id': count.location_id.id,
            'warehouse_id': count.warehouse_id.id,
            'user_ids': [(6, 0, self.manager.ids)],
            'current_state': 'Start',
            'state': 'In Progress',
            'current_scanning_location_id': count.location_id.id,
        })

        session.pda_fast_scan('7500000000001/LOT-QR-001/12,50')

        self.assertEqual(session.current_scanning_product_id, product)
        self.assertEqual(session.current_scanning_lot_id, lot)
        self.assertEqual(session.mobile_count_qty, 12.50)

    def test_same_product_lot_qr_is_rejected_after_confirmation(self):
        product, lot = self._qr_lot_fixture()
        count = self._count(use_barcode_scanner=True)
        session = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': count.id,
            'location_id': count.location_id.id,
            'warehouse_id': count.warehouse_id.id,
            'user_ids': [(6, 0, self.manager.ids)],
            'current_state': 'Start',
            'state': 'In Progress',
            'current_scanning_location_id': count.location_id.id,
        })

        qr = 'QR-PROD-001/LOT-QR-001/47.70'
        session.pda_fast_scan(qr)
        session.pda_fast_confirm_qty(46)

        lines = session.session_line_ids.filtered(
            lambda line: line.product_id == product and line.lot_id == lot
        )
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines.scanned_qty, 46)

        state = session.pda_fast_scan(qr)

        self.assertEqual(len(session.session_line_ids.filtered(
            lambda line: line.product_id == product and line.lot_id == lot
        )), 1)
        self.assertFalse(session.current_scanning_product_id)
        self.assertFalse(session.current_scanning_lot_id)
        self.assertEqual(state['feedback_type'], 'warning')
        self.assertIn('ya fue escaneado', state['feedback'])

    def test_same_qr_twice_before_confirm_does_not_reset_quantity(self):
        product, lot = self._qr_lot_fixture()
        count = self._count(use_barcode_scanner=True)
        session = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': count.id,
            'location_id': count.location_id.id,
            'warehouse_id': count.warehouse_id.id,
            'user_ids': [(6, 0, self.manager.ids)],
            'current_state': 'Start',
            'state': 'In Progress',
            'current_scanning_location_id': count.location_id.id,
        })

        qr = 'QR-PROD-001/LOT-QR-001/20'
        session.pda_fast_scan(qr)
        session.mobile_count_qty = 18

        state = session.pda_fast_scan(qr)

        self.assertEqual(session.current_scanning_product_id, product)
        self.assertEqual(session.current_scanning_lot_id, lot)
        self.assertEqual(session.mobile_count_qty, 18)
        self.assertEqual(state['feedback_type'], 'warning')
        self.assertIn('pendiente de confirmar', state['feedback'])

    def test_duplicate_qr_state_is_explicit_for_mobile_ui(self):
        product, lot = self._qr_lot_fixture()
        count = self._count(use_barcode_scanner=True)
        session = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': count.id,
            'location_id': count.location_id.id,
            'warehouse_id': count.warehouse_id.id,
            'user_ids': [(6, 0, self.manager.ids)],
            'current_state': 'Start',
            'state': 'In Progress',
            'current_scanning_location_id': count.location_id.id,
        })

        qr = 'QR-PROD-001/LOT-QR-001/10'
        session.pda_fast_scan(qr)
        session.pda_fast_confirm_qty(10)
        state = session.pda_fast_scan(qr)

        self.assertTrue(state['duplicate_warning'])
        self.assertEqual(state['feedback_type'], 'warning')
        self.assertFalse(state['product'])

    def test_pda_recent_list_is_limited_for_mobile_performance(self):
        product, lot = self._qr_lot_fixture()
        count = self._count(use_barcode_scanner=True)
        session = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': count.id,
            'location_id': count.location_id.id,
            'warehouse_id': count.warehouse_id.id,
            'user_ids': [(6, 0, self.manager.ids)],
            'current_state': 'Start',
            'state': 'In Progress',
            'current_scanning_location_id': count.location_id.id,
        })

        for index in range(5):
            extra_lot = self.env['stock.lot'].create({
                'name': 'LOT-MOBILE-%s' % index,
                'product_id': product.id,
                'company_id': self.company.id,
            })
            self.env['setu.inventory.count.session.line'].create({
                'session_id': session.id,
                'inventory_count_id': count.id,
                'location_id': count.location_id.id,
                'product_id': product.id,
                'lot_id': extra_lot.id,
                'scanned_qty': index + 1,
                'product_scanned': True,
            })

        state = session.pda_fast_get_state()
        self.assertLessEqual(len(state['recent']), 3)

    def test_backend_dashboard_action_is_per_count(self):
        count = self._count()
        action = count.action_open_backend_dashboard()

        self.assertEqual(action['type'], 'ir.actions.client')
        self.assertEqual(
            action['tag'],
            'setu_inventory_count_management.count_backend_dashboard',
        )
        self.assertEqual(action['params']['count_id'], count.id)

    def test_count_creation_prepares_persistent_snapshot(self):
        product, lot = self._qr_lot_fixture()

        # Stock must exist before creating the count: the count freezes that
        # expected inventory at creation time.
        warehouse = self.warehouse
        location = warehouse.lot_stock_id
        self.env['stock.quant']._update_available_quantity(
            product,
            location,
            9,
            lot_id=lot,
        )
        count = self._count(
            warehouse_id=warehouse.id,
            location_id=location.id,
            use_barcode_scanner=True,
        )

        header = self.env['setu.inventory.count.snapshot'].search([
            ('count_id', '=', count.id),
        ])
        self.assertTrue(header)
        self.assertTrue(header.ready)
        self.assertGreaterEqual(header.expected_item_count, 1)
        snapshot_line = header.line_ids.filtered(
            lambda line: line.product_id == product and line.lot_id == lot
        )
        self.assertTrue(snapshot_line)
        self.assertEqual(snapshot_line.expected_qty, 9)

    def test_dashboard_does_not_change_expected_after_stock_changes(self):
        product, lot = self._qr_lot_fixture()
        location = self.warehouse.lot_stock_id
        self.env['stock.quant']._update_available_quantity(
            product,
            location,
            9,
            lot_id=lot,
        )
        count = self._count(
            warehouse_id=self.warehouse.id,
            location_id=location.id,
            use_barcode_scanner=True,
        )
        before = count.get_backend_dashboard_data()

        # Stock moves after count creation must not alter the frozen expected
        # universe of this count.
        self.env['stock.quant']._update_available_quantity(
            product,
            location,
            5,
            lot_id=lot,
        )
        after = count.get_backend_dashboard_data()

        self.assertEqual(before['kpis']['expected'], after['kpis']['expected'])
        self.assertEqual(before['kpis']['pending'], after['kpis']['pending'])

    def test_session_reading_updates_persistent_snapshot_only(self):
        product, lot = self._qr_lot_fixture()
        location = self.warehouse.lot_stock_id
        self.env['stock.quant']._update_available_quantity(
            product,
            location,
            9,
            lot_id=lot,
        )
        count = self._count(
            warehouse_id=self.warehouse.id,
            location_id=location.id,
            use_barcode_scanner=True,
        )
        session = self.env['setu.inventory.count.session'].create({
            'inventory_count_id': count.id,
            'location_id': location.id,
            'warehouse_id': self.warehouse.id,
            'user_ids': [(6, 0, self.manager.ids)],
            'current_state': 'Start',
            'state': 'In Progress',
            'current_scanning_location_id': location.id,
        })
        self.env['setu.inventory.count.session.line'].create({
            'session_id': session.id,
            'inventory_count_id': count.id,
            'location_id': location.id,
            'product_id': product.id,
            'lot_id': lot.id,
            'scanned_qty': 8,
            'product_scanned': True,
        })

        header = self.env['setu.inventory.count.snapshot'].search([
            ('count_id', '=', count.id),
        ])
        line = header.line_ids.filtered(
            lambda item: item.product_id == product and item.lot_id == lot
        )
        self.assertEqual(line.counted_qty, 8)
        self.assertEqual(line.difference_qty, -1)
        self.assertEqual(line.status, 'difference')
        self.assertGreaterEqual(header.difference_item_count, 1)

    def test_backend_dashboard_returns_pagination_metadata(self):
        count = self._count(use_barcode_scanner=True)
        data = count.get_backend_dashboard_data(
            pending_page=1,
            difference_page=1,
            page_size=25,
        )

        self.assertIn('pagination', data)
        self.assertEqual(data['pagination']['page_size'], 25)
        self.assertEqual(data['pagination']['pending']['page'], 1)
        self.assertEqual(data['pagination']['differences']['page'], 1)

    def test_backend_dashboard_quant_opens_as_modal(self):
        product, lot = self._qr_lot_fixture()
        count = self._count(use_barcode_scanner=True)

        action = count.dashboard_open_quant(
            product.id,
            lot.id,
            count.location_id.id,
        )

        self.assertEqual(action['target'], 'new')
        self.assertEqual(action['res_model'], 'stock.quant')
        self.assertTrue(action['views'])

    def test_same_warehouse_cannot_have_two_active_counts(self):
        count_1 = self._count()
        count_2 = self._count()

        count_1.write({'state': 'In Progress'})
        self.assertTrue(count_1.warehouse_lock_active)

        with self.assertRaises(ValidationError):
            count_2.write({'state': 'In Progress'})

        self.assertEqual(count_2.state, 'Draft')

    def test_warehouse_lock_survives_reset_to_draft_until_final_state(self):
        count = self._count()
        count.write({'state': 'In Progress'})
        self.assertTrue(count.warehouse_lock_active)

        count.write({'state': 'Draft'})
        self.assertTrue(count.warehouse_lock_active)

        count.write({'state': 'Approved'})
        self.assertFalse(count.warehouse_lock_active)

    def test_locked_warehouse_blocks_outgoing_stock_move(self):
        count = self._count()
        count.write({'state': 'In Progress'})

        customer = self.env.ref('stock.stock_location_customers')
        move = self.env['stock.move'].create({
            'name': 'Movimiento bloqueado por conteo',
            'product_id': self.product.id,
            'product_uom_qty': 1.0,
            'product_uom': self.product.uom_id.id,
            'location_id': self.warehouse.lot_stock_id.id,
            'location_dest_id': customer.id,
            'company_id': self.company.id,
        })

        with self.assertRaises(UserError):
            move._check_inventory_count_warehouse_lock()

        count.write({'state': 'Approved'})
        self.assertTrue(move._check_inventory_count_warehouse_lock())

    def test_locked_warehouse_blocks_incoming_stock_move(self):
        count = self._count()
        count.write({'state': 'In Progress'})

        supplier = self.env.ref('stock.stock_location_suppliers')
        move = self.env['stock.move'].create({
            'name': 'Entrada bloqueada por conteo',
            'product_id': self.product.id,
            'product_uom_qty': 1.0,
            'product_uom': self.product.uom_id.id,
            'location_id': supplier.id,
            'location_dest_id': self.warehouse.lot_stock_id.id,
            'company_id': self.company.id,
        })

        with self.assertRaises(UserError):
            move._check_inventory_count_warehouse_lock()

    def test_to_be_approved_keeps_warehouse_locked(self):
        count = self._count()
        count.write({'state': 'In Progress'})
        count.write({'state': 'To Be Approved'})

        self.assertTrue(count.warehouse_lock_active)
        lock = self.env['setu.inventory.count.warehouse.lock'].search([
            ('count_id', '=', count.id),
        ])
        self.assertEqual(len(lock), 1)
        self.assertEqual(lock.warehouse_id, self.warehouse)

    def test_rejected_count_releases_warehouse_lock(self):
        count = self._count()
        count.write({'state': 'In Progress'})
        self.assertTrue(count.warehouse_lock_active)

        count.write({'state': 'Rejected'})
        self.assertFalse(count.warehouse_lock_active)

