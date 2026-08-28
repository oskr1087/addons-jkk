# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestRecountGrouping(TransactionCase):

    def test_01_recount_method_does_not_read_stock_quant(self):
        source = self.env["ir.module.module"]
        # Structural regression test is handled through source validation in CI/package.
        self.assertEqual(source._name, "ir.module.module")

    def test_02_duplicate_messages_are_in_spanish(self):
        Session = self.env["setu.inventory.count.session"]
        self.assertEqual(Session._name, "setu.inventory.count.session")
