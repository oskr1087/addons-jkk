from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.stock_account.tests.common import TestStockValuationCommon


@tagged("post_install", "-at_install")
class TestStockAccountByWarehouse(TestStockValuationCommon):
    """Functional/unit tests for warehouse-specific stock accounting."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.account_wh_variation = cls.env["account.account"].create({
            "name": "WH Stock Variation",
            "code": "WHSTV",
            "account_type": "expense",
        })
        cls.account_wh_valuation = cls.env["account.account"].create({
            "name": "WH Stock Valuation",
            "code": "WHSTK",
            "account_type": "asset_current",
            "account_stock_variation_id": cls.account_wh_variation.id,
        })
        cls.account_wh_input = cls.env["account.account"].create({
            "name": "WH Stock Input",
            "code": "WHIN",
            "account_type": "asset_current",
        })
        cls.account_wh_output = cls.env["account.account"].create({
            "name": "WH Stock Output",
            "code": "WHOUT",
            "account_type": "expense",
        })
        cls.journal_wh = cls.env["account.journal"].create({
            "name": "Warehouse Stock Journal",
            "code": "WHST",
            "type": "general",
            "company_id": cls.company.id,
        })

    def _warehouse_configuration_vals(self):
        return {
            "warehouse_stock_valuation_account_id": self.account_wh_valuation.id,
            "warehouse_stock_input_account_id": self.account_wh_input.id,
            "warehouse_stock_output_account_id": self.account_wh_output.id,
            "warehouse_stock_journal_id": self.journal_wh.id,
        }

    def _enable_warehouse_accounting(self, warehouse=None):
        warehouse = warehouse or self.warehouse
        warehouse.write({
            **self._warehouse_configuration_vals(),
            "use_warehouse_stock_accounts": True,
        })
        return warehouse

    def test_01_feature_disabled_by_default(self):
        """Installing the module must not silently change existing warehouses."""
        self.assertFalse(
            self.warehouse.use_warehouse_stock_accounts,
            "Warehouse accounting override must be opt-in.",
        )

    def test_02_cannot_enable_without_complete_configuration(self):
        """All accounting properties are mandatory when the switch is enabled."""
        with self.assertRaises(ValidationError):
            self.warehouse.write({
                "use_warehouse_stock_accounts": True,
            })

        self.assertFalse(self.warehouse.use_warehouse_stock_accounts)

    def test_03_reject_invalid_account_types(self):
        """Receivable/payable/cash accounts must never be accepted for stock valuation."""
        receivable = self.env["account.account"].create({
            "name": "Invalid Warehouse Receivable",
            "code": "WHREC",
            "account_type": "asset_receivable",
            "reconcile": True,
        })

        vals = self._warehouse_configuration_vals()
        vals.update({
            "warehouse_stock_valuation_account_id": receivable.id,
            "use_warehouse_stock_accounts": True,
        })

        with self.assertRaises(ValidationError):
            self.warehouse.write(vals)

    def test_04_disabled_uses_odoo_standard_logic(self):
        """
        A normal supplier -> stock receipt does not get a warehouse-specific
        accounting move while the feature is disabled.
        """
        move = self._make_in_move(
            self.product_standard_auto,
            2,
            unit_cost=10,
        )

        self.assertFalse(
            move.account_move_id,
            "Disabled mode must preserve standard Odoo 19 accounting behavior.",
        )

    def test_05_incoming_move_uses_warehouse_accounts_and_journal(self):
        """Receipt: Dr warehouse valuation / Cr warehouse input."""
        self._enable_warehouse_accounting()

        move = self._make_in_move(
            self.product_standard_auto,
            2,
            unit_cost=10,
        )

        account_move = move.account_move_id
        self.assertTrue(account_move)
        self.assertEqual(account_move.state, "posted")
        self.assertEqual(account_move.journal_id, self.journal_wh)

        debit_line = account_move.line_ids.filtered(lambda line: line.debit)
        credit_line = account_move.line_ids.filtered(lambda line: line.credit)

        self.assertEqual(len(debit_line), 1)
        self.assertEqual(len(credit_line), 1)

        self.assertEqual(
            debit_line.account_id,
            self.account_wh_valuation,
            "Incoming debit must use the warehouse valuation account.",
        )
        self.assertEqual(
            credit_line.account_id,
            self.account_wh_input,
            "Incoming credit must use the warehouse input account.",
        )
        self.assertEqual(debit_line.debit, 20.0)
        self.assertEqual(credit_line.credit, 20.0)
        self.assertEqual(
            sum(account_move.line_ids.mapped("debit")),
            sum(account_move.line_ids.mapped("credit")),
            "The valuation journal entry must be balanced.",
        )

    def test_06_outgoing_move_uses_warehouse_accounts_and_journal(self):
        """Delivery: Dr warehouse output / Cr warehouse valuation."""
        self._enable_warehouse_accounting()

        # Build stock first.
        self._make_in_move(
            self.product_standard_auto,
            5,
            unit_cost=10,
        )

        move = self._make_out_move(
            self.product_standard_auto,
            2,
        )

        account_move = move.account_move_id
        self.assertTrue(account_move)
        self.assertEqual(account_move.state, "posted")
        self.assertEqual(account_move.journal_id, self.journal_wh)

        debit_line = account_move.line_ids.filtered(lambda line: line.debit)
        credit_line = account_move.line_ids.filtered(lambda line: line.credit)

        self.assertEqual(len(debit_line), 1)
        self.assertEqual(len(credit_line), 1)

        self.assertEqual(
            debit_line.account_id,
            self.account_wh_output,
            "Outgoing debit must use the warehouse output account.",
        )
        self.assertEqual(
            credit_line.account_id,
            self.account_wh_valuation,
            "Outgoing credit must use the warehouse valuation account.",
        )
        self.assertEqual(debit_line.debit, credit_line.credit)

    def test_07_correct_warehouse_is_detected_from_destination(self):
        """An incoming move must use the warehouse owning its destination location."""
        self._use_multi_warehouses()

        other_variation = self.env["account.account"].create({
            "name": "OWH Stock Variation",
            "code": "OWHSV",
            "account_type": "expense",
        })
        other_valuation = self.env["account.account"].create({
            "name": "OWH Stock Valuation",
            "code": "OWHST",
            "account_type": "asset_current",
            "account_stock_variation_id": other_variation.id,
        })
        other_input = self.env["account.account"].create({
            "name": "OWH Stock Input",
            "code": "OWHIN",
            "account_type": "asset_current",
        })
        other_output = self.env["account.account"].create({
            "name": "OWH Stock Output",
            "code": "OWHOU",
            "account_type": "expense",
        })
        other_journal = self.env["account.journal"].create({
            "name": "Other Warehouse Stock Journal",
            "code": "OWHS",
            "type": "general",
            "company_id": self.company.id,
        })

        self.other_warehouse.write({
            "warehouse_stock_valuation_account_id": other_valuation.id,
            "warehouse_stock_input_account_id": other_input.id,
            "warehouse_stock_output_account_id": other_output.id,
            "warehouse_stock_journal_id": other_journal.id,
            "use_warehouse_stock_accounts": True,
        })

        move = self._make_in_move(
            self.product_standard_auto,
            3,
            unit_cost=7,
            location_dest_id=self.other_warehouse.lot_stock_id.id,
            picking_type_id=self.other_warehouse.in_type_id.id,
        )

        self.assertEqual(
            move._get_warehouse_for_accounting(),
            self.other_warehouse,
        )
        self.assertEqual(move.account_move_id.journal_id, other_journal)

        accounts = move.account_move_id.line_ids.account_id
        self.assertIn(other_valuation, accounts)
        self.assertIn(other_input, accounts)
        self.assertNotIn(self.account_wh_valuation, accounts)

    def test_08_internal_transfer_does_not_create_extra_account_move(self):
        """Internal movements inside the same warehouse must not create valuation entries."""
        self._enable_warehouse_accounting()

        internal_location = self.env["stock.location"].create({
            "name": "Internal Test Shelf",
            "location_id": self.warehouse.view_location_id.id,
            "usage": "internal",
            "company_id": self.company.id,
        })

        self._make_in_move(
            self.product_standard_auto,
            3,
            unit_cost=10,
        )

        move = self.env["stock.move"].create({
            "description_picking": "Internal transfer test",
            "product_id": self.product_standard_auto.id,
            "location_id": self.stock_location.id,
            "location_dest_id": internal_location.id,
            "product_uom": self.uom.id,
            "product_uom_qty": 1,
        })
        move._action_confirm()
        move._action_assign()
        move.quantity = 1
        move.picked = True
        move._action_done()

        self.assertFalse(
            move.account_move_id,
            "Internal movement inside the warehouse must not create an accounting move.",
        )

    def test_09_account_move_creation_does_not_require_removed_partner_helper(self):
        """
        Regression for Odoo 19: stock.move does not provide
        _get_partner_id_for_valuation_lines. Valuation must work without it.
        """
        self._enable_warehouse_accounting()

        self.assertFalse(
            hasattr(self.env["stock.move"], "_get_partner_id_for_valuation_lines"),
            "This regression test targets the Odoo 19 API used by this database.",
        )

        move = self._make_in_move(
            self.product_standard_auto,
            1,
            unit_cost=11,
        )

        self.assertTrue(move.account_move_id)
        self.assertEqual(move.account_move_id.journal_id, self.journal_wh)
        self.assertEqual(
            move.account_move_id.line_ids.mapped("debit"),
            [0.0, 11.0],
        )
        self.assertEqual(
            move.account_move_id.line_ids.mapped("credit"),
            [11.0, 0.0],
        )

