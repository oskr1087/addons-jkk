# -*- coding: utf-8 -*-
# Part of the Codfy module suite for Odoo. See LICENSE file for full terms.
# Copyright (C) 2026 Codfy (https://www.codfy.mx)
# License: OPL-1 (Odoo Proprietary License v1.0). All rights reserved.
from odoo import _, api, fields, models

from .account_move import _l10n_mx_factor_missing


class AccountPayment(models.Model):
    _inherit = "account.payment"

    l10n_mx_factor = fields.Boolean(
        string="Pago por factoraje",
        help="Marca este pago como una operación de factoraje financiero: el "
             "complemento de pago (REP) se timbrará con el factor como receptor, "
             "no con el cliente de la factura.")
    l10n_mx_factor_factor_id = fields.Many2one(
        "res.partner", string="Factor",
        help="Entidad de factoraje que te paga por la(s) factura(s) cedida(s). "
             "Debe tener RFC, régimen fiscal y código postal para poder timbrar.")
    l10n_mx_factor_scheme = fields.Selection(
        [("directa", "Cobranza directa"),
         ("delegada", "Cobranza delegada"),
         ("plataforma", "Plataforma electrónica")],
        string="Esquema de factoraje", default="directa",
        help="Para tu registro. La emisión del CFDI es la misma en los tres "
             "esquemas; cambia solo quién le cobra al deudor.")
    l10n_mx_factor_commission_move_id = fields.Many2one(
        "account.move", string="CFDI de comisión del factor",
        domain="[('move_type', 'in', ('in_invoice', 'in_refund')),"
               " ('partner_id', '=', l10n_mx_factor_factor_id)]",
        help="Factura de proveedor con el CFDI de Ingreso que el factor te emite "
             "por su comisión e intereses. El SAT la documenta por separado (no "
             "va dentro del REP); enlázala aquí para dejar completo el ciclo.")
    l10n_mx_factor_warning = fields.Char(
        compute="_compute_l10n_mx_factor_warning")

    @api.depends("l10n_mx_factor", "l10n_mx_factor_factor_id",
                 "l10n_mx_factor_factor_id.vat",
                 "l10n_mx_factor_factor_id.zip",
                 "l10n_mx_factor_factor_id.l10n_mx_edi_fiscal_regime")
    def _compute_l10n_mx_factor_warning(self):
        for payment in self:
            warning = False
            if payment.l10n_mx_factor and payment.l10n_mx_factor_factor_id:
                missing = _l10n_mx_factor_missing(payment.l10n_mx_factor_factor_id)
                if missing:
                    warning = _("El factor «%s» no tiene %s; complétalo antes de timbrar.",
                                payment.l10n_mx_factor_factor_id.display_name, ", ".join(missing))
            payment.l10n_mx_factor_warning = warning

    def action_l10n_mx_factor_open_commission(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("CFDI de comisión del factor"),
            "res_model": "account.move",
            "res_id": self.l10n_mx_factor_commission_move_id.id,
            "view_mode": "form",
            "views": [(False, "form")],
        }
