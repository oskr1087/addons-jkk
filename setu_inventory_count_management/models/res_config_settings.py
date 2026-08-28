# -*- coding: utf-8 -*-
from odoo import fields, models, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    auto_inventory_adjustment = fields.Boolean(string="¿Ajuste automático de inventario?",config_parameter='setu_inventory_count_management.auto_inventory_adjustment')
    inventory_count_high_impact_threshold = fields.Float(
        string="Umbral de divergencia de alto impacto",
        default=500.0,
        config_parameter="setu_inventory_count_management.high_impact_threshold",
        help="Importe absoluto a partir del cual una divergencia se resalta como de alto impacto económico.",
    )
