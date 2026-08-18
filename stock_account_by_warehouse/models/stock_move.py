from collections import defaultdict

from odoo import Command, fields, models
from odoo.tools import float_is_zero


class StockMove(models.Model):
    _inherit = "stock.move"

    def _get_warehouse_for_accounting(self):
        """
        Return the warehouse whose internal location participates in the move.

        Incoming movement  -> destination warehouse.
        Outgoing movement  -> source warehouse.
        Other valued flows -> source/destination warehouse as fallback.
        """
        self.ensure_one()
        Warehouse = self.env["stock.warehouse"]
        warehouses = Warehouse.search([
            ("company_id", "=", self.company_id.id),
        ])
        if not warehouses:
            return Warehouse

        def warehouse_from_location(location):
            if not location:
                return Warehouse
            ancestor_ids = {
                int(location_id)
                for location_id in (location.parent_path or "").split("/")
                if location_id
            }
            return warehouses.filtered(
                lambda warehouse:
                    warehouse.view_location_id.id in ancestor_ids
            )[:1]

        source_warehouse = warehouse_from_location(self.location_id)
        destination_warehouse = warehouse_from_location(self.location_dest_id)

        if self._is_in() and destination_warehouse:
            return destination_warehouse

        if self._is_out() and source_warehouse:
            return source_warehouse

        return source_warehouse or destination_warehouse

    def _get_warehouse_accounting_configuration(self):
        self.ensure_one()
        warehouse = self._get_warehouse_for_accounting()
        if not warehouse or not warehouse.use_warehouse_stock_accounts:
            return self.env["stock.warehouse"]
        return warehouse

    def _should_create_account_move(self):
        """
        Preserve Odoo's standard decision when the feature is disabled.

        When enabled, only create an entry for an actual valued boundary movement:
        an incoming or outgoing stock move. This deliberately excludes ordinary
        internal transfers inside the valued stock area.
        """
        self.ensure_one()
        warehouse = self._get_warehouse_accounting_configuration()
        if not warehouse:
            return super()._should_create_account_move()

        return (
            self.product_id.is_storable
            and self.is_valued
            and (self._is_in() or self._is_out())
            and not float_is_zero(
                self.quantity,
                precision_rounding=self.product_uom.rounding,
            )
            and self.product_id.valuation == "real_time"
        )

    def _get_account_move_line_vals(self):
        """
        Keep Odoo's valuation amount/cost calculation untouched.
        Only substitute accounts when warehouse accounting is enabled.
        """
        self.ensure_one()
        warehouse = self._get_warehouse_accounting_configuration()
        if not warehouse:
            return super()._get_account_move_line_vals()

        valuation_account = warehouse.warehouse_stock_valuation_account_id

        if self._is_in():
            debit_account = valuation_account
            credit_account = warehouse.warehouse_stock_input_account_id
        elif self._is_out():
            debit_account = warehouse.warehouse_stock_output_account_id
            credit_account = valuation_account
        else:
            return super()._get_account_move_line_vals()

        value = self._get_aml_value()
        reference = self.reference or self.name or ""
        line_name = "%s - %s" % (reference, self.product_id.name)

        return [
            {
                "account_id": credit_account.id,
                "name": line_name,
                "debit": 0,
                "credit": value,
                "product_id": self.product_id.id,
            },
            {
                "account_id": debit_account.id,
                "name": line_name,
                "debit": value,
                "credit": 0,
                "product_id": self.product_id.id,
            },
        ]

    def _create_account_move(self):
        """
        Odoo 19 uses the company's stock journal in core.
        Split entries by effective warehouse journal while keeping standard
        behavior for warehouses where the feature is disabled.
        """
        grouped_moves = defaultdict(lambda: self.env["stock.move"])

        for move in self:
            warehouse = move._get_warehouse_accounting_configuration()
            journal = (
                warehouse.warehouse_stock_journal_id
                if warehouse
                else move.company_id.account_stock_journal_id
            )

            # Odoo 19 core valuation moves do not expose
            # _get_partner_id_for_valuation_lines(). Group only by company and
            # effective stock journal, matching the core accounting flow.
            grouped_moves[
                (move.company_id.id, journal.id)
            ] |= move

        account_moves = self.env["account.move"]

        for (_company_id, journal_id), moves in grouped_moves.items():
            aml_vals_list = []
            move_ids_to_link = set()

            for move in moves:
                if move._should_create_account_move():
                    aml_vals_list += move._get_account_move_line_vals()
                    move_ids_to_link.add(move.id)

            if not aml_vals_list:
                continue

            references = sorted(set(filter(None, moves.mapped("reference"))))
            joined_refs = ", ".join(references)
            if len(joined_refs) > 43:
                joined_refs = joined_refs[:40] + "..."

            account_move = self.env["account.move"].sudo().create({
                "ref": joined_refs,
                "journal_id": journal_id,
                "line_ids": [
                    Command.create(vals)
                    for vals in aml_vals_list
                ],
                "date": (
                    self.env.context.get("force_period_date")
                    or fields.Date.context_today(self)
                ),
            })
            self.env["stock.move"].browse(
                move_ids_to_link
            ).account_move_id = account_move.id

            account_move._post()
            account_moves |= account_move

        return account_moves
