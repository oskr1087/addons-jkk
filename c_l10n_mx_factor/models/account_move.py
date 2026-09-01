# -*- coding: utf-8 -*-
# Part of the Codfy module suite for Odoo. See LICENSE file for full terms.
# Copyright (C) 2026 Codfy (https://www.codfy.mx)
# License: OPL-1 (Odoo Proprietary License v1.0). All rights reserved.
from odoo import _, models


def _l10n_mx_factor_missing(factor):
    """Datos fiscales del factor que faltan para poder timbrar (o None)."""
    if not factor:
        return None
    missing = []
    if not (factor.vat or "").strip():
        missing.append("RFC")
    if not factor.zip:
        missing.append("código postal")
    if not factor.l10n_mx_edi_fiscal_regime:
        missing.append("régimen fiscal")
    return missing or None


class AccountMove(models.Model):
    _inherit = "account.move"

    def _l10n_mx_edi_add_payment_cfdi_values(self, cfdi_values, pay_results):
        # Emite el REP con el factor como receptor cuando el pago es factoraje.
        super()._l10n_mx_edi_add_payment_cfdi_values(cfdi_values, pay_results)
        payment = self.origin_payment_id
        if not (payment and payment.l10n_mx_factor):
            return
        if cfdi_values.get("errors"):
            return
        cfdi_values["receptor"] = self._l10n_mx_factor_receptor(
            payment, cfdi_values.get("receptor") or {}, cfdi_values)

    def _l10n_mx_factor_receptor(self, payment, receptor, cfdi_values):
        """Devuelve el dict `receptor` del REP con los datos del factor.

        Parte del receptor que ya armó l10n_mx_edi (el deudor) y sustituye solo
        los datos de la parte, para conservar todo lo demás que calculó el core.
        Si el factor no tiene datos fiscales completos, agrega el error al flujo
        estándar de l10n_mx_edi en vez de timbrar."""
        self.ensure_one()
        factor = payment.l10n_mx_factor_factor_id
        if not factor:
            cfdi_values.setdefault("errors", []).append(
                _("Marcaste el pago como factoraje pero no elegiste el factor."))
            return receptor
        missing = _l10n_mx_factor_missing(factor)
        if missing:
            cfdi_values.setdefault("errors", []).append(
                _("El factor «%s» no tiene %s.", factor.display_name, ", ".join(missing)))
            return receptor

        document = self.env["l10n_mx_edi.document"]
        residencia = None
        code = factor.country_id.l10n_mx_edi_code
        if code and code != "MEX":
            residencia = code

        new_receptor = dict(receptor)
        new_receptor.update({
            "to_public": False,
            "rfc": factor.vat.strip(),
            "nombre": document._cfdi_sanitize_to_legal_name(
                factor.commercial_company_name or factor.name),
            "domicilio_fiscal_receptor": factor.zip,
            "regimen_fiscal_receptor": factor.l10n_mx_edi_fiscal_regime,
            "residencia_fiscal": residencia,
            "customer": factor,
        })
        return new_receptor
