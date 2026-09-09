from collections import defaultdict

from odoo import Command, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import float_is_zero


class StockMove(models.Model):
    _inherit = "stock.move"

    # -------------------------------------------------------------------------
    # Warehouse resolution
    # -------------------------------------------------------------------------

    def _warehouse_from_location(self, location):
        self.ensure_one()
        Warehouse = self.env["stock.warehouse"]
        if not location:
            return Warehouse

        warehouses = Warehouse.search([
            ("company_id", "=", self.company_id.id),
        ])
        if not warehouses:
            return Warehouse

        ancestor_ids = {
            int(location_id)
            for location_id in (location.parent_path or "").split("/")
            if location_id
        }
        return warehouses.filtered(
            lambda warehouse: warehouse.view_location_id.id in ancestor_ids
        )[:1]

    def _get_source_destination_warehouses(self):
        self.ensure_one()
        return (
            self._warehouse_from_location(self.location_id),
            self._warehouse_from_location(self.location_dest_id),
        )

    def _get_warehouse_for_accounting(self):
        """Compatibility helper used by tests and existing integrations."""
        self.ensure_one()
        source_warehouse, destination_warehouse = (
            self._get_source_destination_warehouses()
        )

        if self._is_in() and destination_warehouse:
            return destination_warehouse
        if self._is_out() and source_warehouse:
            return source_warehouse
        return source_warehouse or destination_warehouse

    def _warehouse_uses_custom_accounting(self, warehouse):
        self.ensure_one()
        return bool(
            warehouse
            and warehouse.use_warehouse_stock_accounts
        )

    # -------------------------------------------------------------------------
    # Effective accounts / journal
    # -------------------------------------------------------------------------

    def _get_product_valuation_account(self):
        self.ensure_one()
        return self.product_id._get_product_accounts().get("stock_valuation")

    def _get_effective_valuation_account(self, warehouse):
        self.ensure_one()
        if self._warehouse_uses_custom_accounting(warehouse):
            return warehouse.warehouse_stock_valuation_account_id
        return self._get_product_valuation_account()

    def _get_effective_valuation_mode(self, warehouse):
        """
        Effective valuation policy for this movement/warehouse.

        Warehouse policy has priority only when warehouse accounting is enabled
        and a specific policy was selected. Otherwise the product/category
        valuation policy remains in force.
        """
        self.ensure_one()

        if self._warehouse_uses_custom_accounting(warehouse):
            return warehouse.warehouse_valuation_mode
        return self.product_id.valuation

    def _check_interwarehouse_valuation_compatibility(
        self,
        source_warehouse,
        destination_warehouse,
    ):
        """
        A transfer between warehouses can only be automatically reclassified
        when both warehouses use the same effective valuation policy.

        Mixed periodic/perpetual policies would create an incomplete accounting
        treatment, so validation is blocked with a clear message.
        """
        self.ensure_one()

        source_mode = self._get_effective_valuation_mode(source_warehouse)
        destination_mode = self._get_effective_valuation_mode(
            destination_warehouse
        )

        if source_mode != destination_mode:
            raise ValidationError(_(
                "No se puede completar la transferencia entre los almacenes "
                "'%(source)s' y '%(destination)s' porque utilizan políticas de "
                "valoración diferentes. Configure ambos almacenes con la misma "
                "política de valoración antes de continuar.",
                source=source_warehouse.display_name,
                destination=destination_warehouse.display_name,
            ))

        return source_mode

    def _get_effective_journal(self, source_warehouse=False, destination_warehouse=False):
        self.ensure_one()

        if self._warehouse_uses_custom_accounting(source_warehouse):
            return source_warehouse.warehouse_stock_journal_id

        if self._warehouse_uses_custom_accounting(destination_warehouse):
            return destination_warehouse.warehouse_stock_journal_id

        return self.company_id.account_stock_journal_id

    def _is_return_of_outgoing_move(self):
        self.ensure_one()
        origin = self.origin_returned_move_id
        return bool(
            origin
            and (
                getattr(origin, "is_out", False)
                or origin._is_out()
            )
        )

    def _is_return_of_incoming_move(self):
        self.ensure_one()
        origin = self.origin_returned_move_id
        return bool(
            origin
            and (
                getattr(origin, "is_in", False)
                or origin._is_in()
            )
        )

    def _get_external_counterpart_account(self, warehouse, external_location, direction):
        """
        Determine the counterpart for a warehouse boundary movement.

        Priority:
        1. Explicit valuation account on the external/special location.
           This preserves manufacturing, adjustments, scrap, subcontracting, etc.
        2. Warehouse input/output account according to the business direction.
        """
        self.ensure_one()

        if external_location and external_location.valuation_account_id:
            return external_location.valuation_account_id

        if not self._warehouse_uses_custom_accounting(warehouse):
            return False

        if direction == "in":
            # Customer return reverses a delivery.
            if (
                self._is_return_of_outgoing_move()
                or (external_location and external_location.usage == "customer")
            ):
                return warehouse.warehouse_stock_output_account_id
            return warehouse.warehouse_stock_input_account_id

        # Supplier return reverses a receipt.
        if (
            self._is_return_of_incoming_move()
            or (external_location and external_location.usage == "supplier")
        ):
            return warehouse.warehouse_stock_input_account_id
        return warehouse.warehouse_stock_output_account_id

    # -------------------------------------------------------------------------
    # Flow classification
    # -------------------------------------------------------------------------

    def _get_warehouse_accounting_flow(self):
        """
        Returns one of:
        - ('in', False, destination_warehouse)
        - ('out', source_warehouse, False)
        - ('inter_warehouse', source_warehouse, destination_warehouse)
        - ('standard', source_warehouse, destination_warehouse)
        """
        self.ensure_one()

        source_warehouse, destination_warehouse = (
            self._get_source_destination_warehouses()
        )

        # Internal transfer between two different warehouses:
        # Odoo sees it as valued -> valued and normally creates no accounting.
        if (
            source_warehouse
            and destination_warehouse
            and source_warehouse != destination_warehouse
        ):
            return "inter_warehouse", source_warehouse, destination_warehouse

        if self._is_in() and destination_warehouse:
            return "in", source_warehouse, destination_warehouse

        if self._is_out() and source_warehouse:
            return "out", source_warehouse, destination_warehouse

        return "standard", source_warehouse, destination_warehouse

    # -------------------------------------------------------------------------
    # Valuation amounts
    # -------------------------------------------------------------------------

    def _get_interwarehouse_transfer_value(self):
        """
        Internal transfers have no stock.move.value in the standard valuation
        flow because total company inventory does not change.

        For a reclassification between warehouse valuation accounts, use the
        current company inventory unit value. This matches the stock.quant
        valuation approach used by the inventory valuation report.
        """
        self.ensure_one()

        quantity = abs(self.quantity)
        if float_is_zero(
            quantity,
            precision_rounding=self.product_uom.rounding,
        ):
            return 0.0

        product = self.product_id.with_company(self.company_id)

        if product.lot_valuated and len(self.lot_ids) == 1:
            lot = self.lot_ids.with_company(self.company_id)
            lot_qty = lot.product_qty
            if lot_qty:
                return abs(quantity * lot.total_value / lot_qty)

        product_ctx = product._with_valuation_context()
        total_qty = product_ctx.qty_available
        total_value = product.total_value

        if not self.product_uom.is_zero(total_qty):
            return abs(quantity * total_value / total_qty)

        return abs(quantity * product.standard_price)

    # -------------------------------------------------------------------------
    # Costeo independiente por almacén
    # -------------------------------------------------------------------------

    def _warehouse_cost_record(self, warehouse):
        self.ensure_one()
        Cost = self.env["stock.warehouse.product.cost"].sudo()
        rec = Cost.search([("warehouse_id","=",warehouse.id),("product_id","=",self.product_id.id)], limit=1)
        if not rec:
            rec = Cost.create({"warehouse_id": warehouse.id, "product_id": self.product_id.id,
                               "standard_cost": self.product_id.standard_price})
        return rec

    def _warehouse_fifo_value(self, warehouse, qty):
        self.ensure_one()
        Layer=self.env["stock.warehouse.cost.layer"].sudo()
        layers=Layer.search([("warehouse_id","=",warehouse.id),("product_id","=",self.product_id.id),
                             ("remaining_qty",">",0)], order="date,id")
        remaining=qty; value=0.0
        for layer in layers:
            if remaining <= 0: break
            take=min(remaining,layer.remaining_qty)
            value += take*layer.unit_cost
            layer.remaining_qty -= take
            remaining -= take
        if remaining:
            rec=self._warehouse_cost_record(warehouse)
            value += remaining*(rec.average_cost or rec.standard_cost or self.product_id.standard_price)
        return value

    def _warehouse_out_value(self, warehouse):
        self.ensure_one()
        qty=abs(self._get_valued_qty()); rec=self._warehouse_cost_record(warehouse)
        if warehouse.warehouse_cost_method=="standard":
            return qty*(rec.standard_cost or self.product_id.standard_price)
        if warehouse.warehouse_cost_method=="average":
            return qty*(rec.average_cost or rec.standard_cost or self.product_id.standard_price)
        return self._warehouse_fifo_value(warehouse,qty)

    def _warehouse_accounting_value(self, flow, source_warehouse, destination_warehouse):
        self.ensure_one()
        if flow in ("out","inter_warehouse") and self._warehouse_uses_custom_accounting(source_warehouse):
            return self._warehouse_out_value(source_warehouse)
        return self._get_aml_value()

    # -------------------------------------------------------------------------
    # Accounting hooks
    # -------------------------------------------------------------------------

    def _should_create_account_move(self):
        self.ensure_one()

        flow, source_warehouse, destination_warehouse = (
            self._get_warehouse_accounting_flow()
        )

        custom_enabled = (
            self._warehouse_uses_custom_accounting(source_warehouse)
            or self._warehouse_uses_custom_accounting(destination_warehouse)
        )

        if not custom_enabled:
            return super()._should_create_account_move()

        # Respect the effective valuation policy of the warehouse.
        if flow == "inter_warehouse":
            valuation_mode = self._check_interwarehouse_valuation_compatibility(
                source_warehouse,
                destination_warehouse,
            )
        elif flow == "in":
            valuation_mode = self._get_effective_valuation_mode(
                destination_warehouse
            )
        elif flow == "out":
            valuation_mode = self._get_effective_valuation_mode(
                source_warehouse
            )
        else:
            valuation_mode = self.product_id.valuation

        # Periodic valuation does not create immediate accounting entries.
        if valuation_mode != "real_time":
            return False

        if (
            not self.product_id.is_storable
            or not self.is_valued
            or float_is_zero(
                self.quantity,
                precision_rounding=self.product_uom.rounding,
            )
        ):
            return False

        if flow in ("in", "out"):
            return True

        if flow == "inter_warehouse":
            source_account = self._get_effective_valuation_account(source_warehouse)
            destination_account = self._get_effective_valuation_account(
                destination_warehouse
            )
            return bool(
                source_account
                and destination_account
                and source_account != destination_account
            )

        return super()._should_create_account_move()

    def _get_account_move_line_vals(self):
        self.ensure_one()

        flow, source_warehouse, destination_warehouse = (
            self._get_warehouse_accounting_flow()
        )

        custom_enabled = (
            self._warehouse_uses_custom_accounting(source_warehouse)
            or self._warehouse_uses_custom_accounting(destination_warehouse)
        )

        if not custom_enabled:
            return super()._get_account_move_line_vals()

        reference = self.reference or ""
        line_name = "%s - %s" % (reference, self.product_id.name)

        if flow == "inter_warehouse":
            source_account = self._get_effective_valuation_account(source_warehouse)
            destination_account = self._get_effective_valuation_account(
                destination_warehouse
            )
            value = self._warehouse_accounting_value(flow, source_warehouse, destination_warehouse)

            if not source_account or not destination_account or not value:
                return []

            return [
                {
                    "account_id": source_account.id,
                    "name": line_name,
                    "debit": 0,
                    "credit": value,
                    "product_id": self.product_id.id,
                },
                {
                    "account_id": destination_account.id,
                    "name": line_name,
                    "debit": value,
                    "credit": 0,
                    "product_id": self.product_id.id,
                },
            ]

        value = self._warehouse_accounting_value(flow, source_warehouse, destination_warehouse)

        if flow == "in":
            valuation_account = self._get_effective_valuation_account(
                destination_warehouse
            )
            counterpart_account = self._get_external_counterpart_account(
                destination_warehouse,
                self.location_id,
                "in",
            )
            if not valuation_account or not counterpart_account:
                return super()._get_account_move_line_vals()

            debit_account = valuation_account
            credit_account = counterpart_account

        elif flow == "out":
            valuation_account = self._get_effective_valuation_account(
                source_warehouse
            )
            counterpart_account = self._get_external_counterpart_account(
                source_warehouse,
                self.location_dest_id,
                "out",
            )
            if not valuation_account or not counterpart_account:
                return super()._get_account_move_line_vals()

            debit_account = counterpart_account
            credit_account = valuation_account

        else:
            return super()._get_account_move_line_vals()

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

    def _get_warehouse_accounting_partner_id(self):
        """Compatible with Odoo 19 revisions with/without the core helper."""
        self.ensure_one()

        partner = self.picking_id.partner_id
        if not partner:
            return False

        return self.env["res.partner"]._find_accounting_partner(partner).id

    def _create_account_move(self):
        """
        Create valuation entries grouped by:
        company + effective journal + accounting partner.

        This preserves the standard batch behavior while allowing a different
        journal per warehouse.
        """
        grouped_moves = defaultdict(lambda: self.env["stock.move"])

        for move in self:
            flow, source_warehouse, destination_warehouse = (
                move._get_warehouse_accounting_flow()
            )
            journal = move._get_effective_journal(
                source_warehouse,
                destination_warehouse,
            )
            partner_id = move._get_warehouse_accounting_partner_id()

            grouped_moves[
                (move.company_id.id, journal.id, partner_id or False)
            ] |= move

        account_moves = self.env["account.move"]

        for (_company_id, journal_id, partner_id), moves in grouped_moves.items():
            aml_vals_list = []
            move_ids_to_link = set()

            for move in moves:
                if move._should_create_account_move():
                    move_lines = move._get_account_move_line_vals()
                    if move_lines:
                        aml_vals_list += move_lines
                        move_ids_to_link.add(move.id)

            if not aml_vals_list:
                continue

            references = sorted(set(filter(None, moves.mapped("reference"))))
            joined_refs = ", ".join(references)
            if len(joined_refs) > 43:
                joined_refs = joined_refs[:40] + "..."

            account_move = self.env["account.move"].sudo().create({
                "ref": joined_refs,
                "partner_id": partner_id,
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
