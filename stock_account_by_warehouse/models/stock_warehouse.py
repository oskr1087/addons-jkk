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
        help=(
            "Equivale funcionalmente a la Cuenta de valoración de inventario "
            "configurada en la categoría del producto, pero tiene prioridad para "
            "los movimientos asociados a este almacén."
        ),
    )

    warehouse_stock_input_account_id = fields.Many2one(
        "account.account",
        string="Cuenta contrapartida de entrada",
        check_company=True,
        ondelete="restrict",
        domain=[
            ("account_type", "not in", _INVALID_STOCK_ACCOUNT_TYPES),
        ],
        help=(
            "Contrapartida usada cuando un movimiento valorado entra al almacén. "
            "En Odoo 19 las contrapartidas del stock se relacionan con las cuentas "
            "de valoración de las ubicaciones; este campo permite definir la "
            "contrapartida directamente por almacén cuando la opción está activa."
        ),
    )

    warehouse_stock_output_account_id = fields.Many2one(
        "account.account",
        string="Cuenta contrapartida de salida",
        check_company=True,
        ondelete="restrict",
        domain=[
            ("account_type", "not in", _INVALID_STOCK_ACCOUNT_TYPES),
        ],
        help=(
            "Contrapartida usada cuando un movimiento valorado sale del almacén. "
            "En Odoo 19 las contrapartidas del stock se relacionan con las cuentas "
            "de valoración de las ubicaciones; este campo permite definir la "
            "contrapartida directamente por almacén cuando la opción está activa."
        ),
    )

    warehouse_stock_journal_id = fields.Many2one(
        "account.journal",
        string="Diario de inventario",
        check_company=True,
        ondelete="restrict",
        domain=[("type", "=", "general")],
        help=(
            "Equivale al Diario de inventario de la categoría/compañía. "
            "Debe ser un diario de tipo Misceláneo/General de la misma compañía."
        ),
    )

    warehouse_stock_variation_account_id = fields.Many2one(
        "account.account",
        string="Cuenta de variación de inventario",
        related="warehouse_stock_valuation_account_id.account_stock_variation_id",
        readonly=True,
        help=(
            "Cuenta de variación asociada a la cuenta de valoración seleccionada. "
            "Se muestra como referencia, siguiendo la relación estándar de Odoo 19."
        ),
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
                missing.append(_("Cuenta contrapartida de entrada"))
            if not warehouse.warehouse_stock_output_account_id:
                missing.append(_("Cuenta contrapartida de salida"))
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
