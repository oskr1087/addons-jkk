# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSimplifiedRecountFlow(TransactionCase):

    def _counts(self):
        Count = self.env["setu.stock.inventory.count"]
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        parent = Count.with_context(setu_creating_recount=True).create({
            "warehouse_id": warehouse.id,
            "location_id": warehouse.lot_stock_id.id,
            "approver_id": self.env.user.id,
            "type": "Multi Session",
        })
        child = Count.with_context(setu_creating_recount=True).create({
            "warehouse_id": warehouse.id,
            "location_id": warehouse.lot_stock_id.id,
            "approver_id": self.env.user.id,
            "type": "Multi Session",
            "count_id": parent.id,
        })
        return parent, child

    def test_01_recount_traceability(self):
        parent, child = self._counts()
        self.assertFalse(parent.is_recount)
        self.assertTrue(child.is_recount)
        self.assertEqual(child.root_count_id, parent)
        self.assertEqual(child.recount_level, 1)

    def test_02_recount_never_creates_adjustment(self):
        _parent, child = self._counts()
        child.state = "To Be Approved"
        child.approve_inventory_count()
        self.assertEqual(child.state, "Approved")
        self.assertFalse(child.inventory_adj_ids)

    def test_03_nested_recount_is_blocked(self):
        _parent, child = self._counts()
        child.state = "To Be Approved"
        with self.assertRaises(ValidationError):
            child.action_prepare_directed_recount()
