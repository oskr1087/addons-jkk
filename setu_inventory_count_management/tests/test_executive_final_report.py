# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestExecutiveFinalReport(TransactionCase):

    def _count(self):
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)],
            limit=1,
        )
        location = self.env["stock.location"].create({
            "name": "Executive PDF Test",
            "usage": "internal",
            "location_id": warehouse.lot_stock_id.id,
            "company_id": self.env.company.id,
        })
        return self.env["setu.stock.inventory.count"].with_context(
            setu_creating_recount=True,
        ).create({
            "warehouse_id": warehouse.id,
            "location_id": location.id,
            "approver_id": self.env.user.id,
            "type": "Single Session",
        })

    def test_01_report_is_blocked_before_final_state(self):
        count = self._count()
        with self.assertRaises(ValidationError):
            count.action_print_executive_report()

    def test_02_report_data_groups_snapshot_by_product(self):
        count = self._count()
        product = self.env["product.product"].create({
            "name": "Producto Informe Ejecutivo",
            "type": "consu",
            "is_storable": True,
            "standard_price": 5.0,
        })
        header = count._get_snapshot_header(create=True)
        self.env["setu.inventory.count.snapshot.line"].sudo().create({
            "snapshot_id": header.id,
            "product_id": product.id,
            "location_id": count.location_id.id,
            "expected_qty": 10.0,
            "counted_qty": 8.0,
            "difference_qty": -2.0,
            "unit_cost": 5.0,
            "scan_count": 1,
            "status": "difference",
            "unexpected": False,
        })
        header.write({"ready": True})
        count.state = "Inventory Adjusted"

        data = count._get_executive_report_data()

        self.assertEqual(data["product_count"], 1)
        self.assertEqual(data["product_rows"][0]["expected_qty"], 10.0)
        self.assertEqual(data["product_rows"][0]["counted_qty"], 8.0)
        self.assertEqual(data["product_rows"][0]["difference_qty"], -2.0)
        self.assertEqual(data["product_rows"][0]["result"], "Faltante")

    def test_03_report_action_is_qweb_pdf(self):
        count = self._count()
        count.state = "Inventory Adjusted"
        action = count.action_print_executive_report()
        self.assertEqual(action["type"], "ir.actions.report")
        self.assertEqual(action["report_type"], "qweb-pdf")

    def test_04_approved_without_adjustment_can_print(self):
        count = self._count()
        count.state = "Approved"
        self.assertFalse(count.inventory_adj_ids)
        action = count.action_print_executive_report()
        self.assertEqual(action["type"], "ir.actions.report")
        data = count._get_executive_report_data()
        self.assertEqual(data["final_status_label"], "Conteo aprobado · sin ajuste requerido")

    def test_05_executive_report_uses_non_overlapping_layout(self):
        view = self.env.ref(
            "setu_inventory_count_management.report_inventory_count_executive"
        )
        arch = view.arch_db
        self.assertIn("web.basic_layout", arch)
        self.assertNotIn("web.external_layout", arch)
        self.assertIn("Posiciones con diferencia", arch)
        self.assertIn("Detalle consolidado del conteo", arch)

    def test_06_executive_report_distinguishes_no_adjustment_closure(self):
        count = self._count()
        count.state = "Approved"
        data = count._get_executive_report_data()
        self.assertEqual(data["final_status_label"], "Conteo aprobado")
        self.assertIn("ajuste", data["final_result_label"].lower())
        self.assertFalse(data["has_adjustment"])

    def test_07_executive_report_has_only_valid_t_field_expressions(self):
        import re
        from lxml import etree

        view = self.env.ref(
            "setu_inventory_count_management.report_inventory_count_executive"
        )
        arch = etree.fromstring(view.arch_db.encode())
        invalid = []
        for element in arch.xpath("//*[@t-field]"):
            expression = element.attrib["t-field"].strip()
            if not re.fullmatch(
                r"[A-Za-z_]\\w*(?:\\.[A-Za-z_]\\w*)+",
                expression,
            ):
                invalid.append(expression)
        self.assertFalse(invalid, "t-field inválidos: %s" % invalid)

    def test_08_executive_report_uses_preformatted_values(self):
        count = self._count()
        count.state = "Approved"
        data = count._get_executive_report_data()
        self.assertTrue(data["issued_at_fmt"])
        self.assertTrue(data["progress_fmt"].endswith("%"))
        self.assertTrue(data["resolution_rate_fmt"].endswith("%"))

    def test_09_executive_qweb_has_no_runtime_format_helpers(self):
        view = self.env.ref(
            "setu_inventory_count_management.report_inventory_count_executive"
        )
        arch = view.arch_db
        self.assertNotIn("format_datetime(", arch)
        self.assertNotIn("context_timestamp(", arch)
        self.assertNotIn(".strftime(", arch)
        self.assertIn("data['issued_at_fmt']", arch)
        self.assertIn("data['progress_fmt']", arch)
        self.assertIn("data['resolution_rate_fmt']", arch)
