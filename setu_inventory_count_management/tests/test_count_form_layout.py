# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestCountFormLayout(TransactionCase):

    def test_snapshot_view_has_expected_operational_tabs(self):
        view = self.env.ref(
            "setu_inventory_count_management."
            "setu_stock_inventory_count_snapshot_form_extension"
        )
        arch = view.arch_db

        self.assertNotIn('name="snapshot_sessions"', arch)
        self.assertIn('string="Todos" name="snapshot_all"', arch)
        self.assertIn(
            'string="Pendientes de conteo" name="snapshot_pending"',
            arch,
        )
        self.assertIn(
            'string="Por resolver" name="snapshot_to_resolve"',
            arch,
        )

    def test_kpis_are_inserted_before_notebook(self):
        view = self.env.ref(
            "setu_inventory_count_management."
            "setu_stock_inventory_count_snapshot_form_extension"
        )
        self.assertIn(
            'expr="//sheet/notebook" position="before"',
            view.arch_db,
        )

    def test_configuration_is_after_to_resolve(self):
        view = self.env.ref(
            "setu_inventory_count_management."
            "setu_stock_inventory_count_form_enhanced"
        )
        self.assertIn(
            "//notebook/page[@name='snapshot_to_resolve']",
            view.arch_db,
        )
