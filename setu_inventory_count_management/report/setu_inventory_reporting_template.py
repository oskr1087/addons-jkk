# -*- coding: utf-8 -*-
from odoo import fields, models


class SetuReportTemplate(models.TransientModel):
    _name = 'setu.inventory.reporting.template'
    _description = 'Setu Inventory Reporting Template'

    start_date = fields.Date(string="Fecha inicial")
    inventory_count_date = fields.Date(string="Fecha de conteo")
    end_date = fields.Date(string="Fecha final")

    theoretical_qty = fields.Float(string="Cantidad teórica")
    counted_qty = fields.Float(string="Cantidad contada")
    discrepancy_qty = fields.Float(string="Cantidad de discrepancia")

    product_id = fields.Many2one(comodel_name="product.product", string="Producto")
    warehouse_id = fields.Many2one(comodel_name="stock.warehouse", string="Almacén")
    location_id = fields.Many2one(comodel_name="stock.location", string="Ubicación")
    user_id = fields.Many2one(comodel_name="res.users", string="User")

    user_ids = fields.Many2many(comodel_name="res.users", string="Users")
    warehouse_ids = fields.Many2many(comodel_name="stock.warehouse", string="Warehouses")
    location_ids = fields.Many2many(comodel_name="stock.location", string="Ubicaciones")
    lot_id = fields.Many2one(comodel_name="stock.lot", string="Lote")