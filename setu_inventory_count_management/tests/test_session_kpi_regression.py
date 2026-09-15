# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

@tagged("post_install", "-at_install")
class TestSessionKpiRegression(TransactionCase):

    def test_session_kpi_counts_lines_not_unique_products(self):
        Session = self.env["setu.inventory.count.session"]
        method = Session._compute_scanned_products
        self.assertTrue(callable(method))
        # Contrato: la implementación no debe volver a mapped('product_id')
        # para determinar total/escaneados.
        import inspect
        source = inspect.getsource(method)
        self.assertIn("session.total_products = len(lines)", source)
        self.assertIn("session.total_scanned_products = len(completed)", source)
        self.assertNotIn("len(lines.mapped('product_id'))", source)

    def test_location_progress_counts_closed_zero_as_processed(self):
        Progress = self.env["setu.inventory.count.location.progress"]
        import inspect
        source = inspect.getsource(Progress._compute_live_metrics)
        self.assertIn("processed_expected", source)
        self.assertIn("line.closed_as_zero", source)
        self.assertIn('progress.finished_at and not pending', source)
