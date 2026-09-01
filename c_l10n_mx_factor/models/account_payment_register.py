# -*- coding: utf-8 -*-
# Part of the Codfy module suite for Odoo. See LICENSE file for full terms.
# Copyright (C) 2026 Codfy (https://www.codfy.mx)
# License: OPL-1 (Odoo Proprietary License v1.0). All rights reserved.
from odoo import _, api, fields, models

from .account_move import _l10n_mx_factor_missing


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    l10n_mx_factor = fields.Boolean(string="Pago por factoraje")
    l10n_mx_factor_factor_id = fields.Many2one("res.partner", string="Factor")
    l10n_mx_factor_scheme = fields.Selection(
        [("directa", "Cobranza directa"),
         ("delegada", "Cobranza delegada"),
         ("plataforma", "Plataforma electrónica")],
        string="Esquema de factoraje", default="directa")
    l10n_mx_factor_warning = fields.Char(
        compute="_compute_l10n_mx_factor_warning")

    @api.depends("l10n_mx_factor", "l10n_mx_factor_factor_id",
                 "l10n_mx_factor_factor_id.vat",
                 "l10n_mx_factor_factor_id.zip",
                 "l10n_mx_factor_factor_id.l10n_mx_edi_fiscal_regime")
    def _compute_l10n_mx_factor_warning(self):
        for wizard in self:
            warning = False
            if wizard.l10n_mx_factor and wizard.l10n_mx_factor_factor_id:
                missing = _l10n_mx_factor_missing(wizard.l10n_mx_factor_factor_id)
                if missing:
                    warning = _("El factor «%s» no tiene %s; complétalo antes de timbrar.",
                                wizard.l10n_mx_factor_factor_id.display_name, ", ".join(missing))
            wizard.l10n_mx_factor_warning = warning

    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super()._create_payment_vals_from_wizard(batch_result)
        payment_vals.update(self._l10n_mx_factor_payment_vals())
        return payment_vals

    def _create_payment_vals_from_batch(self, batch_result):
        payment_vals = super()._create_payment_vals_from_batch(batch_result)
        payment_vals.update(self._l10n_mx_factor_payment_vals())
        return payment_vals

    def _l10n_mx_factor_payment_vals(self):
        if not self.l10n_mx_factor:
            return {}
        return {
            "l10n_mx_factor": True,
            "l10n_mx_factor_factor_id": self.l10n_mx_factor_factor_id.id,
            "l10n_mx_factor_scheme": self.l10n_mx_factor_scheme,
        }
