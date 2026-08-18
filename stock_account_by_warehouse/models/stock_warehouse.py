from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


_INVALID_STOCK_ACCOUNT_TYPES = (
    "asset_receivable",
    "liability_payable",
    "asset_cash",
    "liability_credit_card",
)


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    use_warehouse_stock_accounts = fields.Boolean(
        string="Usar contabilidad de inventario del almacén",
        default=False,
        help=(
            "Si está desactivado, Odoo utiliza su configuración contable estándar. "
            "Si está activado, los movimientos valorados asociados a este almacén "
            "utilizan las cuentas y el diario definidos en esta pestaña."
        ),
    )

    warehouse_stock_valuation_account_id = fields.Many2one(
        "account.account",
        string="Cuenta de valoración de inventario",
        check_company=True,
        ondelete="restrict",
        domain=[
            ("account_type", "not in", _INVALID_STOCK_ACCOUNT_TYPES),
        ],
        help="Cuenta utilizada para registrar el valor del inventario asociado a este almacén.",
    )

    warehouse_stock_input_account_id = fields.Many2one(
        "account.account",
        string="Cuenta de entrada de inventario",
        check_company=True,
        ondelete="restrict",
        domain=[
            ("account_type", "not in", _INVALID_STOCK_ACCOUNT_TYPES),
        ],
        help="Cuenta utilizada como contrapartida contable en las entradas de inventario de este almacén.",
    )

    warehouse_stock_output_account_id = fields.Many2one(
        "account.account",
        string="Cuenta de salida de inventario",
        check_company=True,
        ondelete="restrict",
        domain=[
            ("account_type", "not in", _INVALID_STOCK_ACCOUNT_TYPES),
        ],
        help="Cuenta utilizada como contrapartida contable en las salidas de inventario de este almacén.",
    )

    warehouse_stock_journal_id = fields.Many2one(
        "account.journal",
        string="Diario de inventario",
        check_company=True,
        ondelete="restrict",
        domain=[("type", "=", "general")],
        help="Diario utilizado para registrar los asientos contables de inventario de este almacén.",
    )


    @api.constrains(
        "use_warehouse_stock_accounts",
        "warehouse_stock_valuation_account_id",
        "warehouse_stock_input_account_id",
        "warehouse_stock_output_account_id",
        "warehouse_stock_journal_id",
    )
    def _check_warehouse_stock_account_configuration(self):
        for warehouse in self:
            if not warehouse.use_warehouse_stock_accounts:
                continue

            missing = []
            if not warehouse.warehouse_stock_valuation_account_id:
                missing.append(_("Cuenta de valoración de inventario"))
            if not warehouse.warehouse_stock_input_account_id:
                missing.append(_("Cuenta de entrada de inventario"))
            if not warehouse.warehouse_stock_output_account_id:
                missing.append(_("Cuenta de salida de inventario"))
            if not warehouse.warehouse_stock_journal_id:
                missing.append(_("Diario de inventario"))

            if missing:
                raise ValidationError(_(
                    "No puede activar la contabilidad por almacén sin completar "
                    "la configuración contable.\n\nFalta configurar:\n- %s",
                    "\n- ".join(missing),
                ))

            accounts = (
                warehouse.warehouse_stock_valuation_account_id
                | warehouse.warehouse_stock_input_account_id
                | warehouse.warehouse_stock_output_account_id
            )
            invalid = accounts.filtered(
                lambda account: account.account_type in _INVALID_STOCK_ACCOUNT_TYPES
            )
            if invalid:
                raise ValidationError(_(
                    "Las siguientes cuentas no son válidas para valoración de "
                    "inventario: %s",
                    ", ".join(invalid.mapped("display_name")),
                ))

            if warehouse.warehouse_stock_journal_id.type != "general":
                raise ValidationError(_(
                    "El Diario de inventario del almacén debe ser de tipo "
                    "Misceláneo/General."
                ))
