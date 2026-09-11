# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class InventoryCountScanEvent(models.Model):
    _name = "setu.inventory.count.scan.event"
    _description = "Evento de escaneo de conteo"
    _order = "scanned_at desc, id desc"

    count_id = fields.Many2one(
        "setu.stock.inventory.count",
        string="Conteo",
        required=True,
        index=True,
        ondelete="cascade",
    )
    session_id = fields.Many2one(
        "setu.inventory.count.session",
        string="Sesión",
        required=True,
        index=True,
        ondelete="cascade",
    )
    session_line_id = fields.Many2one(
        "setu.inventory.count.session.line",
        string="Línea de sesión",
        required=True,
        index=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Producto",
        required=True,
        index=True,
        ondelete="restrict",
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lote / Serie",
        index=True,
        ondelete="restrict",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Ubicación",
        required=True,
        index=True,
        ondelete="restrict",
    )
    quantity = fields.Float(
        string="Cantidad QR",
        required=True,
        digits="Product Unit of Measure",
    )
    payload = fields.Char(
        string="Contenido QR",
        readonly=True,
        copy=False,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Usuario",
        required=True,
        default=lambda self: self.env.user,
        index=True,
        ondelete="restrict",
    )
    scanned_at = fields.Datetime(
        string="Fecha de lectura",
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    has_observation = fields.Boolean(
        string="Tiene observaciones",
        default=False,
        index=True,
        copy=False,
    )
    observation = fields.Text(
        string="Observación",
        copy=False,
    )
    company_id = fields.Many2one(
        "res.company",
        related="count_id.warehouse_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )

    @api.constrains("quantity")
    def _check_quantity(self):
        for event in self:
            if event.quantity < 0:
                raise ValidationError(_("La cantidad del QR no puede ser negativa."))

    def _sync_snapshot_observation(self):
        """Sincroniza inmediatamente las observaciones con el snapshot del conteo."""
        Snapshot = self.env["setu.inventory.count.snapshot.line"].sudo()

        for event in self:
            snapshots = Snapshot.search([
                ("count_id", "=", event.count_id.id),
                ("product_id", "=", event.product_id.id),
                ("location_id", "=", event.location_id.id),
                ("lot_id", "=", event.lot_id.id if event.lot_id else False),
            ])

            # Si la lectura corresponde a un producto/lote no previsto,
            # asegurar primero que exista la línea snapshot.
            if not snapshots and event.session_line_id:
                snapshots = event.count_id._ensure_snapshot_lines_for_session_line(
                    event.session_line_id
                )

            for snapshot in snapshots:
                observed_events = self.sudo().search([
                    ("count_id", "=", snapshot.count_id.id),
                    ("product_id", "=", snapshot.product_id.id),
                    ("location_id", "=", snapshot.location_id.id),
                    ("lot_id", "=", snapshot.lot_id.id if snapshot.lot_id else False),
                    ("has_observation", "=", True),
                ], order="scanned_at asc, id asc")

                notes = []
                for observed in observed_events:
                    note = (observed.observation or "").strip()
                    if note:
                        notes.append(
                            "%s: %s" % (observed.user_id.display_name, note)
                        )

                snapshot.sudo().write({
                    "has_observation": bool(observed_events),
                    "observation_note": "\n".join(notes) if notes else False,
                })

        # Forzar recomputo de métricas del conteo para que la vista del
        # controlador refleje el cambio inmediatamente.
        counts = self.mapped("count_id")
        if counts:
            counts._refresh_snapshot_metrics()
        return True

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.mapped("session_line_id")._refresh_scan_observation_summary()
        records._sync_snapshot_observation()
        for count in records.mapped("count_id"):
            count._notify_count_event("COUNT_SCANNED", {"count_id": count.id})
        return records

    def write(self, vals):
        if not self.env.user.has_group(
            "setu_inventory_count_management.group_setu_inventory_count_manager"
        ):
            allowed = {"has_observation", "observation"}
            forbidden = set(vals) - allowed
            if forbidden:
                raise AccessError(_(
                    "El operador solo puede registrar o modificar la observación de una lectura."
                ))
            if any(event.user_id != self.env.user for event in self):
                raise AccessError(_(
                    "Solo puede modificar observaciones de sus propias lecturas."
                ))

        if vals.get("has_observation") is False:
            vals["observation"] = False

        result = super().write(vals)
        self.mapped("session_line_id")._refresh_scan_observation_summary()

        if {"has_observation", "observation"} & set(vals):
            self._sync_snapshot_observation()
            for count in self.mapped("count_id"):
                count._notify_count_event("COUNT_REVIEW_UPDATED", {"count_id": count.id})

        return result


class InventoryCountSessionLineScanObservation(models.Model):
    _inherit = "setu.inventory.count.session.line"

    scan_event_ids = fields.One2many(
        "setu.inventory.count.scan.event",
        "session_line_id",
        string="Lecturas QR",
        readonly=True,
    )
    has_observation = fields.Boolean(
        string="Tiene observaciones",
        default=False,
        readonly=True,
        index=True,
        copy=False,
    )
    observation = fields.Text(
        string="Observaciones",
        readonly=True,
        copy=False,
    )

    def _refresh_scan_observation_summary(self):
        for line in self:
            observed = line.scan_event_ids.filtered("has_observation")
            notes = [
                event.observation.strip()
                for event in observed
                if event.observation and event.observation.strip()
            ]
            super(
                InventoryCountSessionLineScanObservation,
                line.with_context(skip_scan_observation_summary=True),
            ).write({
                "has_observation": bool(observed),
                "observation": "\n".join(notes) if notes else False,
            })
        return True


class InventoryCountSessionScanObservation(models.Model):
    _inherit = "setu.inventory.count.session"

    scan_event_ids = fields.One2many(
        "setu.inventory.count.scan.event",
        "session_id",
        string="Lecturas QR",
        readonly=True,
    )
    observation_count = fields.Integer(
        string="Con observaciones",
        compute="_compute_scan_observation_count",
    )

    @api.depends("scan_event_ids.has_observation")
    def _compute_scan_observation_count(self):
        for session in self:
            session.observation_count = len(
                session.scan_event_ids.filtered("has_observation")
            )


class StockInventoryCountScanObservation(models.Model):
    _inherit = "setu.stock.inventory.count"

    def _notify_count_event(self, event_type, payload=None):
        """Notificación en tiempo real usando bus.bus nativo de Odoo."""
        Bus = self.env["bus.bus"].sudo()
        for count in self:
            Bus._sendone(
                "setu_inventory_count_%s" % count.id,
                event_type,
                {
                    "count_id": count.id,
                    "event": event_type,
                    "payload": payload or {},
                },
            )
        return True


    scan_event_ids = fields.One2many(
        "setu.inventory.count.scan.event",
        "count_id",
        string="Lecturas QR",
        readonly=True,
    )
    observation_count = fields.Integer(
        string="Observaciones",
        compute="_compute_scan_observation_count",
    )

    @api.depends("scan_event_ids.has_observation")
    def _compute_scan_observation_count(self):
        for count in self:
            count.observation_count = len(
                count.scan_event_ids.filtered("has_observation")
            )
