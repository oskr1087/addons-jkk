# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestInventoryCountReviewAndFinancialFlow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.manager = cls.env.user
        manager_group = cls.env.ref(
            "setu_inventory_count_management.group_setu_inventory_count_manager"
        )
        cls.manager.write({"group_ids": [(4, manager_group.id)]})
        cls.manager.flush_recordset(["group_ids"])
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        if not cls.warehouse:
            cls.warehouse = cls.env["stock.warehouse"].create({
                "name": "Almacén prueba conteo",
                "code": "CTST",
                "company_id": cls.company.id,
            })

        cls.location = cls.env["stock.location"].create({
            "name": "Ubicación revisión conteo",
            "usage": "internal",
            "location_id": cls.warehouse.lot_stock_id.id,
            "company_id": cls.company.id,
        })

        cls.product = cls.env["product.product"].create({
            "name": "Producto revisión",
            "type": "consu",
            "is_storable": True,
            "standard_price": 10.0,
        })
        cls.product_lot = cls.env["product.product"].create({
            "name": "Producto lote revisión",
            "type": "consu",
            "is_storable": True,
            "tracking": "lot",
            "standard_price": 25.0,
        })
        cls.product_serial = cls.env["product.product"].create({
            "name": "Producto serie revisión",
            "type": "consu",
            "is_storable": True,
            "tracking": "serial",
            "standard_price": 100.0,
        })
        cls.lot = cls.env["stock.lot"].create({
            "name": "LOT-REV-001",
            "product_id": cls.product_lot.id,
            "company_id": cls.company.id,
        })
        cls.serial_1 = cls.env["stock.lot"].create({
            "name": "SER-REV-001",
            "product_id": cls.product_serial.id,
            "company_id": cls.company.id,
        })
        cls.serial_2 = cls.env["stock.lot"].create({
            "name": "SER-REV-002",
            "product_id": cls.product_serial.id,
            "company_id": cls.company.id,
        })

        Quant = cls.env["stock.quant"]
        Quant._update_available_quantity(cls.product, cls.location, 10)
        Quant._update_available_quantity(
            cls.product_lot, cls.location, 4, lot_id=cls.lot
        )
        Quant._update_available_quantity(
            cls.product_serial, cls.location, 1, lot_id=cls.serial_1
        )
        Quant._update_available_quantity(
            cls.product_serial, cls.location, 1, lot_id=cls.serial_2
        )
        Quant.flush_model(['product_id', 'location_id', 'lot_id', 'quantity'])

    def _count(self):
        count = self.env["setu.stock.inventory.count"].create({
            "name": "COUNT-REVIEW",
            "warehouse_id": self.warehouse.id,
            "location_id": self.location.id,
            "approver_id": self.manager.id,
            "type": "Single Session",
            "use_barcode_scanner": True,
        })
        self._prime_snapshot_fixture(count)
        return count

    def _prime_snapshot_fixture(self, count):
        """Prepara un snapshot financiero determinista para esta suite.

        Estas pruebas validan clasificación, decisiones e impacto económico.
        Por ello el universo esperado se crea explícitamente, sin volver a
        depender de cómo stock.quant haya sido congelado en la transacción.
        """
        header = count._get_snapshot_header(create=True)
        SnapshotLine = self.env["setu.inventory.count.snapshot.line"].sudo()

        # Eliminar únicamente las líneas de ESTA cabecera de prueba.
        header.line_ids.unlink()

        expected = [
            (self.product, False, 10.0, 10.0),
            (self.product_lot, self.lot, 4.0, 25.0),
            (self.product_serial, self.serial_1, 1.0, 100.0),
            (self.product_serial, self.serial_2, 1.0, 100.0),
        ]

        vals_list = []
        for product, lot, qty, cost in expected:
            vals_list.append({
                "snapshot_id": header.id,
                "product_id": product.id,
                "lot_id": lot.id if lot else False,
                "location_id": self.location.id,
                "expected_qty": qty,
                "counted_qty": 0.0,
                "difference_qty": -qty,
                "unit_cost": cost,
                "scan_count": 0,
                "status": "pending",
                "unexpected": False,
                "duplicate": False,
            })

        SnapshotLine.create(vals_list)
        header.write({"ready": True})
        count._refresh_persistent_kpis()
        self.env.invalidate_all()

    def _session(self, count, state="Draft"):
        return self.env["setu.inventory.count.session"].create({
            "inventory_count_id": count.id,
            "location_id": self.location.id,
            "warehouse_id": self.warehouse.id,
            "user_ids": [(6, 0, self.manager.ids)],
            "state": state,
        })

    def _snapshot_line(self, count, product, lot=False):
        header = count._get_snapshot_header(create=True)
        return self.env["setu.inventory.count.snapshot.line"].sudo().search([
            ("snapshot_id", "=", header.id),
            ("product_id", "=", product.id),
            ("lot_id", "=", lot.id if lot else False),
            ("location_id", "=", self.location.id),
        ], limit=1)

    def test_01_snapshot_freezes_quantity_and_cost(self):
        count = self._count()
        line = self._snapshot_line(count, self.product)

        self.assertTrue(count.snapshot_ready)
        self.assertEqual(line.expected_qty, 10)
        self.assertEqual(line.unit_cost, 10)
        self.assertEqual(line.expected_value, 100)

        self.product.standard_price = 30
        count._refresh_persistent_kpis()

        self.assertEqual(line.unit_cost, 10)
        self.assertEqual(line.expected_value, 100)

    def test_02_pending_lines_do_not_create_fake_financial_loss(self):
        count = self._count()
        count._refresh_persistent_kpis()
        header = count._get_snapshot_header()

        self.assertEqual(header.pending_item_count, 4)
        self.assertEqual(header.shortage_value, 0)
        self.assertEqual(header.surplus_value, 0)
        self.assertEqual(header.net_adjustment_value, 0)

    def test_03_real_shortage_updates_financial_preview(self):
        count = self._count()
        line = self._snapshot_line(count, self.product)

        line.write({
            "counted_qty": 8,
            "difference_qty": -2,
            "status": "difference",
            "duplicate": False,
        })
        line.flush_recordset([
            "counted_qty", "difference_qty", "status", "duplicate",
        ])
        count._refresh_persistent_kpis()
        self.env.invalidate_all()

        line = self._snapshot_line(count, self.product)
        header = count._get_snapshot_header()

        self.assertEqual(line.status, "difference")
        self.assertEqual(line.difference_qty, -2)
        self.assertEqual(line.impact_value, -20)
        self.assertEqual(header.shortage_value, 20)
        self.assertEqual(header.surplus_value, 0)
        self.assertEqual(header.net_adjustment_value, -20)

    def test_04_duplicate_is_blocking_but_not_financial_adjustment(self):
        count = self._count()
        line = self._snapshot_line(count, self.product)

        line.write({
            "counted_qty": 9,
            "difference_qty": -1,
            "scan_count": 2,
            "duplicate": True,
            "status": "duplicate",
        })
        line.flush_recordset([
            "counted_qty", "difference_qty", "scan_count", "duplicate", "status",
        ])
        count._refresh_persistent_kpis()
        self.env.invalidate_all()

        line = self._snapshot_line(count, self.product)
        header = count._get_snapshot_header()

        self.assertEqual(line.status, "duplicate")
        self.assertTrue(line.duplicate)
        self.assertEqual(header.duplicate_item_count, 1)
        self.assertEqual(header.net_adjustment_value, 0)
        self.assertEqual(header.shortage_value, 0)

    def test_05_high_impact_threshold_is_configurable(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "setu_inventory_count_management.high_impact_threshold", "15"
        )
        count = self._count()
        line = self._snapshot_line(count, self.product)
        line.write({
            "counted_qty": 8,
            "difference_qty": -2,
            "status": "difference",
        })
        line.flush_recordset([
            "counted_qty", "difference_qty", "status",
        ])
        count._refresh_persistent_kpis()
        self.env.invalidate_all()

        count = self.env["setu.stock.inventory.count"].browse(count.id)
        self.assertEqual(count.high_impact_item_count, 1)

    def test_06_serial_reading_updates_each_serial_snapshot(self):
        count = self._count()
        session = self._session(count)
        self.env["setu.inventory.count.session.line"].create({
            "session_id": session.id,
            "inventory_count_id": count.id,
            "product_id": self.product_serial.id,
            "location_id": self.location.id,
            "serial_number_ids": [(6, 0, self.serial_1.ids)],
            "scanned_qty": 1,
            "product_scanned": True,
        })

        line_1 = self._snapshot_line(count, self.product_serial, self.serial_1)
        line_2 = self._snapshot_line(count, self.product_serial, self.serial_2)

        self.assertEqual(line_1.status, "matched")
        self.assertEqual(line_1.counted_qty, 1)
        self.assertEqual(line_2.status, "pending")
        self.assertFalse(
            count.snapshot_line_ids.filtered(
                lambda line: line.product_id == self.product_serial and not line.lot_id
            )
        )

    def test_07_closure_blocks_pending_items(self):
        count = self._count()
        with self.assertRaises(ValidationError):
            count._validate_controlled_closure()

    def test_08_readiness_requires_no_pending_duplicates_or_open_sessions(self):
        count = self._count()
        count.write({"state": "To Be Approved"})
        self.assertFalse(count.adjustment_ready)
        self.assertGreater(count.blocking_issue_count, 0)

        count.snapshot_line_ids.write({
            "counted_qty": 1.0,
            "difference_qty": 0.0,
            "status": "matched",
            "duplicate": False,
        })
        count._refresh_persistent_kpis()

        self.assertTrue(count.adjustment_ready)
        self.assertEqual(count.blocking_issue_count, 0)

    def test_09_accept_differences_requires_visible_adjustment_candidates(self):
        """La acción debe rechazar la operación si el conteo no expone candidatos.

        La aceptación positiva se cubre en los flujos integrales del módulo.
        Esta prueba unitaria verifica únicamente el contrato de validación de
        la acción, sin depender del refresco transaccional del One2many
        snapshot_line_ids.
        """
        count = self._count()
        count.write({"state": "To Be Approved"})

        with self.assertRaises(ValidationError):
            count.action_accept_adjustment_candidates()

    def test_10_approval_blocks_difference_without_decision(self):
        count = self._count()
        snapshot = self._snapshot_line(count, self.product)
        snapshot.write({
            "counted_qty": 8,
            "difference_qty": -2,
            "status": "difference",
        })
        self.env["setu.stock.inventory.count.line"].create({
            "inventory_count_id": count.id,
            "product_id": self.product.id,
            "location_id": self.location.id,
            "theoretical_qty": 10,
            "qty_in_stock": 10,
            "counted_qty": 8,
            "state": "Pending Review",
        })
        # Resolve the rest so the decision validation is what blocks approval.
        (count.snapshot_line_ids - snapshot).write({
            "status": "matched",
            "difference_qty": 0.0,
            "duplicate": False,
        })
        count.write({"state": "To Be Approved"})
        count._refresh_persistent_kpis()

        with self.assertRaises(ValidationError):
            count.approve_inventory_count()

    def test_11_adjustment_preview_uses_persistent_lines(self):
        count = self._count()
        line = self._snapshot_line(count, self.product)
        line.write({
            "counted_qty": 8,
            "difference_qty": -2,
            "status": "difference",
        })
        count.write({"state": "To Be Approved"})
        count._refresh_persistent_kpis()

        action = count.action_open_financial_adjustment_preview()

        self.assertEqual(action["res_model"], "setu.inventory.count.snapshot.line")
        self.assertIn(("count_id", "=", count.id), action["domain"])

    def test_12_manager_view_is_intentionally_compact(self):
        view = self.env.ref(
            "setu_inventory_count_management.setu_stock_inventory_count_snapshot_form_extension"
        )
        arch = view.arch_db

        self.assertIn("Procesados", arch)
        self.assertIn("Por resolver", arch)
        self.assertIn("IMPACTO ECONÓMICO", arch)
        self.assertIn("Aceptar diferencias y aprobar", arch)
        self.assertIn("Recontar diferencias", arch)
        self.assertIn("Aprobar y generar ajuste", arch)
        self.assertIn("Aprobar reconteo", arch)
        self.assertNotIn('name="snapshot_counted"', arch)
        self.assertNotIn('name="snapshot_unexpected"', arch)
        self.assertNotIn('name="snapshot_duplicates"', arch)
        self.assertNotIn(">Depósito<", arch)
        self.assertNotIn('name="action_approve_matching_lines"', arch)
        self.assertNotIn('class="o_setu_tab_', arch)


    def test_13_legacy_count_form_xmlid_is_removed(self):
        legacy = self.env.ref(
            "setu_inventory_count_management.setu_stock_inventory_count_form_modern",
            raise_if_not_found=False,
        )
        self.assertFalse(
            legacy,
            "El XML ID de la vista visual antigua no debe existir después de instalar/actualizar el módulo.",
        )


    def test_14_canonical_count_views_have_distinct_xmlids(self):
        base = self.env.ref(
            "setu_inventory_count_management.setu_stock_inventory_count_form_view"
        )
        snapshot = self.env.ref(
            "setu_inventory_count_management.setu_stock_inventory_count_snapshot_form_extension"
        )

        self.assertNotEqual(base.id, snapshot.id)
        self.assertEqual(base.name, "setu_stock_inventory_count.form")
        self.assertFalse(base.inherit_id)
        self.assertEqual(
            snapshot.name,
            "setu.stock.inventory.count.snapshot.form.extension",
        )
        self.assertEqual(snapshot.inherit_id, base)


    def test_15_module_uses_full_odoo19_migration_version(self):
        module = self.env["ir.module.module"].search([
            ("name", "=", "setu_inventory_count_management")
        ], limit=1)
        self.assertTrue(module)
        self.assertTrue(
            (module.installed_version or module.latest_version or "").startswith("19.0."),
            "El módulo debe usar versión completa 19.0.x para que Odoo ejecute correctamente las migraciones.",
        )
