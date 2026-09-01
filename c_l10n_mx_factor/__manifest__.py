# -*- coding: utf-8 -*-
{
    "name": "Factoraje financiero CFDI",
    "version": "19.0.1.0.2",
    "summary": 'Cede tus facturas a un factor y emite el complemento de pago (REP) con el factor como receptor, sobre el CFDI nativo de Odoo (l10n_mx_edi).',
    "description": """
Factoraje financiero en el complemento de pagos (CFDI)
======================================================

Cuando vendes (cedes) tus facturas a una entidad de factoraje y esa entidad te
paga, el SAT exige que el complemento para recepción de pagos (REP) se emita con
el **factor como receptor**, no con tu cliente original. El CFDI de pagos nativo
de Odoo siempre pone al cliente de la factura; este módulo permite indicar la
operación como factoraje y emitir el REP con el receptor correcto (el factor),
relacionado con la factura cedida.

- Marca un pago como factoraje y elige la entidad de factoraje (factor).
- El REP se timbra con el factor como receptor y se relaciona a la(s) factura(s).
- Soporta cobranza directa y delegada.
- Validación previa de los datos fiscales del factor (RFC, régimen, C.P.).
""",
    "author": "Codfy",
    "website": "https://www.codfy.mx",
    "category": "Accounting/Localizations/EDI",
    "license": "OPL-1",
    "price": 30.0,
    "currency": "USD",
    "images": ["static/description/assets/images/main_screenshot.gif"],
    "depends": ["l10n_mx_edi"],
    "data": [
        "views/account_payment_views.xml",
        "views/account_payment_register_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
