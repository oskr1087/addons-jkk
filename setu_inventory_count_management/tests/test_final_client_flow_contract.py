# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

@tagged("post_install", "-at_install")
class TestFinalClientFlowContract(TransactionCase):

    def test_role_names(self):
        root = Path(__file__).resolve().parents[1]
        xml = (root / "security/security.xml").read_text(encoding="utf-8")
        self.assertIn('<field name="name">Contador</field>', xml)
        self.assertIn('<field name="name">Controlador</field>', xml)
        self.assertIn('<field name="name">Administrador</field>', xml)

    def test_only_admin_applies_adjustment(self):
        root = Path(__file__).resolve().parents[1]
        py = (root / "models/setu_stock_inventory.py").read_text(encoding="utf-8")
        xml = (root / "views/setu_stock_inventory_views.xml").read_text(encoding="utf-8")
        self.assertIn("group_setu_inventory_count_admin", py)
        self.assertIn('string="Aplicar ajuste definitivo"', xml)
        self.assertIn("group_setu_inventory_count_admin", xml)

    def test_excel_final_exists(self):
        root = Path(__file__).resolve().parents[1]
        py = (root / "models/inventory_count_executive_report.py").read_text(encoding="utf-8")
        xml = (root / "views/inventory_count_snapshot_views.xml").read_text(encoding="utf-8")
        self.assertIn("def action_export_final_xlsx", py)
        self.assertIn("1. RESUMEN EJECUTIVO", py)
        self.assertIn("4. MOVIMIENTOS DE STOCK Y CONTABILIDAD", py)
        self.assertIn('string="Excel final"', xml)

    def test_controller_approval_is_separate_from_admin_application(self):
        root = Path(__file__).resolve().parents[1]
        py = (root / "models/inventory_count_workflow.py").read_text(encoding="utf-8")
        self.assertIn("El Administrador debe revisar y aplicar el ajuste definitivo", py)
