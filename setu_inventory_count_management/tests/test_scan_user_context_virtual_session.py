# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestScanUserContextVirtualSession(TransactionCase):

    def test_virtual_session_never_creates_orphan_context(self):
        Context = self.env["setu.inventory.count.session.user.context"].sudo()
        Session = self.env["setu.inventory.count.session"].sudo()

        before = Context.search_count([])

        virtual = Session.new({
            "mobile_count_qty": 1.0,
        })

        result = virtual._get_user_scan_context(create=True)

        self.assertFalse(result)
        self.assertEqual(Context.search_count([]), before)

    def test_persisted_session_context_has_session_id(self):
        warehouse = self.env["stock.warehouse"].search([], limit=1)
        session = self.env["setu.inventory.count.session"].sudo().create({
            "warehouse_id": warehouse.id,
            "mobile_count_qty": 1.0,
        })

        context = session._get_user_scan_context(create=True)

        self.assertTrue(context)
        self.assertEqual(context.session_id, session)
        self.assertTrue(context.session_id.id)
