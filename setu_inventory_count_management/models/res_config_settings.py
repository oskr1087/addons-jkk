# -*- coding: utf-8 -*-
from odoo import fields, models, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    auto_inventory_adjustment = fields.Boolean(string="¿Ajuste automático de inventario?",config_parameter='setu_inventory_count_management.auto_inventory_adjustment')