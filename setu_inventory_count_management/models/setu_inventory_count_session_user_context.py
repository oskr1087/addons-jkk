# -*- coding: utf-8 -*-
from odoo import fields, models


class SetuInventoryCountSessionUserContext(models.Model):
    _name = "setu.inventory.count.session.user.context"
    _description = "Contexto de escaneo por usuario y sesión"
    _order = "session_id, user_id"

    session_id = fields.Many2one(
        "setu.inventory.count.session",
        required=True,
        ondelete="cascade",
        index=True,
    )
    user_id = fields.Many2one(
        "res.users",
        required=True,
        ondelete="cascade",
        index=True,
    )
    current_location_id = fields.Many2one(
        "stock.location",
        string="Ubicación activa",
    )
    current_product_id = fields.Many2one(
        "product.product",
        string="Producto activo",
    )
    current_lot_id = fields.Many2one(
        "stock.lot",
        string="Lote/Serie activo",
    )
    mobile_count_qty = fields.Float(
        string="Cantidad física",
        default=1.0,
    )
    last_feedback = fields.Char(string="Último resultado")
    last_feedback_type = fields.Selection(
        [
            ("info", "Información"),
            ("success", "Correcto"),
            ("warning", "Advertencia"),
            ("danger", "Error"),
        ],
        default="info",
        string="Tipo de resultado",
    )
    qr_payload = fields.Char(string="QR leído")
    qr_quantity = fields.Float(string="Cantidad QR")
    qr_detected = fields.Boolean(string="QR enriquecido")
    paused = fields.Boolean(string="Pausado", default=False)
    finished = fields.Boolean(string="Participación finalizada", default=False)
    finished_at = fields.Datetime(string="Finalizada el")

    _session_user_unique = models.Constraint(
        "UNIQUE(session_id, user_id)",
        "Ya existe un contexto de escaneo para este usuario en la sesión.",
    )
