# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_is_zero
from psycopg2.extras import execute_values


class InventoryCountSnapshot(models.Model):
    """Cabecera persistente 1:1 del análisis de un conteo."""

    _name = "setu.inventory.count.snapshot"
    _description = "Información persistente del conteo"
    _order = "id desc"

    count_id = fields.Many2one(
        "setu.stock.inventory.count",
        string="Conteo",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        related="count_id.company_id",
        store=True,
        index=True,
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        related="count_id.warehouse_id",
        store=True,
        index=True,
    )
    location_id = fields.Many2one(
        "stock.location",
        related="count_id.location_id",
        store=True,
        index=True,
    )

    ready = fields.Boolean(string="Información preparada", default=False, readonly=True)
    snapshot_date = fields.Datetime(string="Información preparada el", readonly=True)
    last_update = fields.Datetime(string="Última actualización", readonly=True)

    expected_item_count = fields.Integer(string="Esperados", readonly=True)
    counted_item_count = fields.Integer(string="Contados", readonly=True)
    pending_item_count = fields.Integer(string="Pendientes", readonly=True)
    matched_item_count = fields.Integer(string="Coincidencias", readonly=True)
    difference_item_count = fields.Integer(string="Divergencias", readonly=True)
    zero_item_count = fields.Integer(string="Cantidad cero", readonly=True)
    unexpected_item_count = fields.Integer(string="No previstos", readonly=True)
    duplicate_item_count = fields.Integer(string="Posibles duplicados", readonly=True)
    progress_percent = fields.Float(string="Avance (%)", readonly=True, digits=(16, 2))
    difference_percent = fields.Float(
        string="Divergencia (%)", readonly=True, digits=(16, 2)
    )
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", store=True, readonly=True)
    expected_value = fields.Monetary(string="Valor esperado", currency_field="currency_id", readonly=True)
    counted_value = fields.Monetary(string="Valor contado", currency_field="currency_id", readonly=True)
    shortage_value = fields.Monetary(string="Pérdida estimada", currency_field="currency_id", readonly=True)
    surplus_value = fields.Monetary(string="Sobrante estimado", currency_field="currency_id", readonly=True)
    net_adjustment_value = fields.Monetary(string="Impacto neto", currency_field="currency_id", readonly=True)
    high_impact_item_count = fields.Integer(string="Divergencias de alto impacto", readonly=True)

    line_ids = fields.One2many(
        "setu.inventory.count.snapshot.line",
        "snapshot_id",
        string="Detalle del conteo",
    )

    _count_unique = models.Constraint(
        "UNIQUE(count_id)",
        "Ya existe información persistente para este conteo.",
    )


class InventoryCountSnapshotLine(models.Model):
    _name = "setu.inventory.count.snapshot.line"
    _description = "Detalle persistente del conteo"
    _order = "location_id, product_id, lot_id, id"
    _rec_name = "product_id"

    def init(self):
        self.env.cr.execute(f"""
            CREATE INDEX IF NOT EXISTS
                setu_inv_snapshot_line_key_idx
            ON {self._table}
                (snapshot_id, product_id, location_id, lot_id)
        """)
        self.env.cr.execute(f"""
            CREATE INDEX IF NOT EXISTS
                setu_inv_snapshot_line_status_idx
            ON {self._table}
                (snapshot_id, status)
        """)
        self.env.cr.execute(f"""
            CREATE INDEX IF NOT EXISTS
                setu_inv_snapshot_line_count_key_idx
            ON {self._table}
                (count_id, product_id, location_id, lot_id)
        """)

        # Compatibilidad con snapshots creados por versiones anteriores:
        # Boolean NULL debe significar False, nunca excluir una línea esperada.
        self.env.cr.execute(f"""
            UPDATE {self._table}
               SET unexpected = FALSE
             WHERE unexpected IS NULL
        """)
        self.env.cr.execute(f"""
            UPDATE {self._table}
               SET duplicate = FALSE
             WHERE duplicate IS NULL
        """)

    snapshot_id = fields.Many2one(
        "setu.inventory.count.snapshot",
        string="Información persistente",
        required=True,
        ondelete="cascade",
        index=True,
    )
    count_id = fields.Many2one(
        "setu.stock.inventory.count",
        related="snapshot_id.count_id",
        string="Conteo",
        store=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        related="snapshot_id.company_id",
        store=True,
        index=True,
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        related="snapshot_id.warehouse_id",
        store=True,
        index=True,
    )
    location_id = fields.Many2one(
        "stock.location", string="Ubicación", required=True, index=True
    )
    product_id = fields.Many2one(
        "product.product", string="Producto", required=True, index=True
    )
    lot_id = fields.Many2one("stock.lot", string="Lote", index=True)
    uom_id = fields.Many2one(
        "uom.uom", related="product_id.uom_id", string="UdM", store=True
    )

    expected_qty = fields.Float(
        string="Cantidad esperada", digits="Product Unit of Measure", readonly=True
    )
    counted_qty = fields.Float(
        string="Cantidad contada", digits="Product Unit of Measure", readonly=True
    )
    difference_qty = fields.Float(
        string="Diferencia", digits="Product Unit of Measure", readonly=True
    )
    difference_display = fields.Char(
        string="Diferencia",
        compute="_compute_difference_display",
    )
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", store=True, readonly=True)
    unit_cost = fields.Monetary(string="Costo unitario", currency_field="currency_id", readonly=True)
    expected_value = fields.Monetary(string="Valor esperado", currency_field="currency_id", compute="_compute_financial_values", store=True, readonly=True)
    counted_value = fields.Monetary(string="Valor contado", currency_field="currency_id", compute="_compute_financial_values", store=True, readonly=True)
    impact_value = fields.Monetary(string="Impacto", currency_field="currency_id", compute="_compute_financial_values", store=True, readonly=True)
    impact_abs = fields.Monetary(string="Impacto absoluto", currency_field="currency_id", compute="_compute_financial_values", store=True, readonly=True)
    high_impact = fields.Boolean(string="Alto impacto", compute="_compute_financial_values", store=True, readonly=True)
    scan_count = fields.Integer(string="Lecturas", readonly=True)
    first_session_id = fields.Many2one(
        "setu.inventory.count.session", string="Primera sesión", readonly=True
    )
    last_session_id = fields.Many2one(
        "setu.inventory.count.session", string="Última sesión", readonly=True
    )
    last_user_id = fields.Many2one("res.users", string="Último usuario", readonly=True)
    first_scan_at = fields.Datetime(string="Primera lectura", readonly=True)
    last_scan_at = fields.Datetime(string="Última lectura", readonly=True)
    unexpected = fields.Boolean(string="No previsto", default=False, readonly=True)
    duplicate = fields.Boolean(string="Posible duplicado", default=False, readonly=True)
    status = fields.Selection(
        [
            ("pending", "Pendiente"),
            ("matched", "Coincide"),
            ("difference", "Divergencia"),
            ("zero", "Cantidad cero"),
            ("unexpected", "No previsto"),
            ("duplicate", "Posible duplicado"),
        ],
        string="Estado",
        default="pending",
        required=True,
        index=True,
        readonly=True,
    )

    @api.depends("expected_qty", "counted_qty", "difference_qty", "unit_cost")
    def _compute_financial_values(self):
        threshold = float(
            self.env["ir.config_parameter"].sudo().get_param(
                "setu_inventory_count_management.high_impact_threshold", 500.0
            ) or 500.0
        )
        for line in self:
            line.expected_value = line.expected_qty * line.unit_cost
            line.counted_value = line.counted_qty * line.unit_cost
            line.impact_value = line.difference_qty * line.unit_cost
            line.impact_abs = abs(line.impact_value)
            line.high_impact = line.impact_abs >= threshold

    @api.depends("status", "difference_qty")
    def _compute_difference_display(self):
        for line in self:
            if line.status == "pending":
                line.difference_display = "—"
            else:
                line.difference_display = str(
                    round(line.difference_qty, 6)
                ).rstrip("0").rstrip(".") or "0"

    @api.model_create_multi
    def create(self, vals_list):
        keys = {
            (
                vals.get("snapshot_id"),
                vals.get("product_id"),
                vals.get("lot_id") or False,
                vals.get("location_id"),
            )
            for vals in vals_list
        }
        if len(keys) != len(vals_list):
            raise ValidationError(
                _("La fotografía contiene duplicado el mismo producto, lote y ubicación.")
            )

        snapshot_ids = {key[0] for key in keys if key[0]}
        product_ids = {key[1] for key in keys if key[1]}
        location_ids = {key[3] for key in keys if key[3]}
        if snapshot_ids and product_ids and location_ids:
            existing = self.search([
                ("snapshot_id", "in", list(snapshot_ids)),
                ("product_id", "in", list(product_ids)),
                ("location_id", "in", list(location_ids)),
            ])
            existing_keys = {
                (
                    line.snapshot_id.id,
                    line.product_id.id,
                    line.lot_id.id if line.lot_id else False,
                    line.location_id.id,
                )
                for line in existing
            }
            if keys & existing_keys:
                raise ValidationError(
                    _("Ya existe el mismo producto, lote y ubicación en este conteo.")
                )
        return super().create(vals_list)

    def _status_from_values(self, expected, counted, scan_count, unexpected=False):
        self.ensure_one()
        if unexpected:
            return "unexpected"
        if not scan_count:
            return "pending"
        if scan_count > 1:
            return "duplicate"
        rounding = self.product_id.uom_id.rounding
        if float_is_zero(counted, precision_rounding=rounding):
            if not float_is_zero(expected, precision_rounding=rounding):
                return "zero"
        if float_is_zero(counted - expected, precision_rounding=rounding):
            return "matched"
        return "difference"

    def _refresh_from_session_lines(self, count_override=None):
        """Actualiza solo los ítems afectados por una lectura."""
        if not self:
            return True

        SessionLine = self.env["setu.inventory.count.session.line"].sudo()
        affected_counts = self.mapped("count_id") | (
            count_override or self.env["setu.stock.inventory.count"]
        )

        for snapshot_line in self:
            domain = [
                ("inventory_count_id", "=", snapshot_line.count_id.id),
                ("product_id", "=", snapshot_line.product_id.id),
                ("location_id", "=", snapshot_line.location_id.id),
                ("product_scanned", "=", True),
                ("session_id.state", "!=", "Cancel"),
            ]
            if snapshot_line.product_id.tracking == "serial" and snapshot_line.lot_id:
                domain.append(("serial_number_ids", "in", snapshot_line.lot_id.id))
            else:
                domain.append(
                    ("lot_id", "=", snapshot_line.lot_id.id if snapshot_line.lot_id else False)
                )
            session_lines = SessionLine.search(
                domain, order="date_of_scanning, id"
            )

            counted = (
                float(len(session_lines))
                if snapshot_line.product_id.tracking == "serial"
                else sum(session_lines.mapped("scanned_qty"))
            )
            scan_count = len(session_lines)
            first = session_lines[:1]
            last = session_lines[-1:]
            status = (
                "zero"
                if snapshot_line.closed_as_zero and not scan_count
                else snapshot_line._status_from_values(
                    snapshot_line.expected_qty,
                    counted,
                    scan_count,
                    unexpected=snapshot_line.unexpected,
                )
            )
            snapshot_line.write({
                "counted_qty": counted,
                "difference_qty": counted - snapshot_line.expected_qty,
                "scan_count": scan_count,
                "duplicate": scan_count > 1,
                "status": status,
                "first_session_id": first.session_id.id if first else False,
                "last_session_id": last.session_id.id if last else False,
                "last_user_id": (
                    last.user_ids[:1].id
                    if last and last.user_ids
                    else (
                        last.session_id.user_ids[:1].id
                        if last and last.session_id.user_ids
                        else False
                    )
                ),
                "first_scan_at": first.date_of_scanning if first else False,
                "last_scan_at": last.date_of_scanning if last else False,
            })

        affected_counts._refresh_persistent_kpis()
        return True

    def _refresh_from_session_lines_bulk(self):
        if not self:
            return True

        SessionLine = self.env["setu.inventory.count.session.line"].sudo()
        snapshots = self.sudo()
        session_lines = SessionLine.search([
            ("inventory_count_id", "in", snapshots.count_id.ids),
            ("product_id", "in", snapshots.product_id.ids),
            ("location_id", "in", snapshots.location_id.ids),
            ("product_scanned", "=", True),
            ("session_id.state", "!=", "Cancel"),
        ], order="date_of_scanning, id")

        session_lines.mapped("serial_number_ids")
        session_lines.mapped("session_id.user_ids")

        aggregates = {}
        for line in session_lines:
            base = (
                line.inventory_count_id.id,
                line.product_id.id,
                line.location_id.id,
            )
            if line.product_id.tracking == "serial":
                keys = [(*base, serial.id) for serial in line.serial_number_ids]
                qty = 1.0
            else:
                keys = [(*base, line.lot_id.id if line.lot_id else False)]
                qty = line.scanned_qty

            for key in keys:
                data = aggregates.setdefault(key, {
                    "counted": 0.0,
                    "scan_count": 0,
                    "first": False,
                    "last": False,
                })
                data["counted"] += qty
                data["scan_count"] += 1
                if not data["first"]:
                    data["first"] = line
                data["last"] = line

        values=[]
        for snapshot in snapshots:
            key=(
                snapshot.count_id.id,
                snapshot.product_id.id,
                snapshot.location_id.id,
                snapshot.lot_id.id if snapshot.lot_id else False,
            )
            data=aggregates.get(key)
            counted=data["counted"] if data else 0.0
            scan_count=data["scan_count"] if data else 0
            status=(
                "zero"
                if snapshot.closed_as_zero and not scan_count
                else snapshot._status_from_values(
                    snapshot.expected_qty,
                    counted,
                    scan_count,
                    unexpected=snapshot.unexpected,
                )
            )
            difference=counted-snapshot.expected_qty
            first=data["first"] if data else SessionLine
            last=data["last"] if data else SessionLine
            first_user=(
                first.session_id.user_ids[:1].id
                if first and first.session_id.user_ids else None
            )
            last_user=(
                last.session_id.user_ids[:1].id
                if last and last.session_id.user_ids else None
            )
            impact=difference*snapshot.unit_cost
            values.append((
                snapshot.id,
                counted,
                difference,
                counted*snapshot.unit_cost,
                impact,
                abs(impact),
                scan_count,
                first.session_id.id if first else None,
                last.session_id.id if last else None,
                last_user or first_user,
                first.date_of_scanning if first else None,
                last.date_of_scanning if last else None,
                bool(scan_count > 1),
                status,
            ))

        if values:
            execute_values(
                self.env.cr,
                f"""
                    UPDATE {self._table} AS snap
                       SET counted_qty = data.counted_qty::double precision,
                           difference_qty = data.difference_qty::double precision,
                           counted_value = data.counted_value::numeric,
                           impact_value = data.impact_value::numeric,
                           impact_abs = data.impact_abs::numeric,
                           scan_count = data.scan_count::integer,
                           first_session_id = data.first_session_id::integer,
                           last_session_id = data.last_session_id::integer,
                           last_user_id = data.last_user_id::integer,
                           first_scan_at = data.first_scan_at::timestamp,
                           last_scan_at = data.last_scan_at::timestamp,
                           duplicate = data.duplicate::boolean,
                           status = data.status::varchar
                      FROM (VALUES %s) AS data(
                           id, counted_qty, difference_qty, counted_value,
                           impact_value, impact_abs, scan_count,
                           first_session_id, last_session_id, last_user_id,
                           first_scan_at, last_scan_at, duplicate, status
                      )
                     WHERE snap.id = data.id
                """,
                values,
                page_size=5000,
            )
            snapshots.invalidate_recordset([
                "counted_qty","difference_qty","counted_value",
                "impact_value","impact_abs","scan_count",
                "first_session_id","last_session_id","last_user_id",
                "first_scan_at","last_scan_at","duplicate","status",
                "difference_display","high_impact",
            ])
        return True


class StockInventoryCountPersistentSnapshot(models.Model):
    _inherit = "setu.stock.inventory.count"

    # No se almacena ningún campo nuevo en setu_stock_inventory_count.
    # Esto evita romper lecturas globales del modelo cuando el código se
    # despliega antes de ejecutar -u del módulo.
    snapshot_line_ids = fields.One2many(
        "setu.inventory.count.snapshot.line",
        "count_id",
        string="Detalle del conteo",
        readonly=True,
    )

    snapshot_pending_line_ids = fields.One2many(
        "setu.inventory.count.snapshot.line",
        "count_id",
        string="Pendientes",
        readonly=True,
        domain=[
            ("status", "=", "pending"),
            ("scan_count", "=", 0),
            ("closed_as_zero", "=", False),
        ],
        help="Posiciones esperadas que todavía no registran ninguna lectura o escaneo.",
    )
    snapshot_to_resolve_line_ids = fields.One2many(
        "setu.inventory.count.snapshot.line",
        "count_id",
        string="Por resolver",
        readonly=True,
        domain=[
            ("status", "in", ("difference", "zero", "unexpected", "duplicate")),
        ],
    )

    snapshot_ready = fields.Boolean(
        string="Información preparada", compute="_compute_snapshot_metrics"
    )
    snapshot_date = fields.Datetime(
        string="Información preparada el", compute="_compute_snapshot_metrics"
    )
    expected_item_count = fields.Integer(
        string="Esperados", compute="_compute_snapshot_metrics"
    )
    counted_item_count = fields.Integer(
        string="Contados", compute="_compute_snapshot_metrics"
    )
    pending_item_count = fields.Integer(
        string="Pendientes", compute="_compute_snapshot_metrics"
    )
    matched_item_count = fields.Integer(
        string="Coincidencias", compute="_compute_snapshot_metrics"
    )
    difference_item_count = fields.Integer(
        string="Divergencias", compute="_compute_snapshot_metrics"
    )
    zero_item_count = fields.Integer(
        string="Cantidad cero", compute="_compute_snapshot_metrics"
    )
    unexpected_item_count = fields.Integer(
        string="No previstos", compute="_compute_snapshot_metrics"
    )
    duplicate_item_count = fields.Integer(
        string="Posibles duplicados", compute="_compute_snapshot_metrics"
    )
    progress_percent = fields.Float(
        string="Avance (%)", compute="_compute_snapshot_metrics", digits=(16, 2)
    )
    difference_percent = fields.Float(
        string="Divergencia (%)", compute="_compute_snapshot_metrics", digits=(16, 2)
    )
    expected_percent = fields.Float(
        string="Esperados (%)", compute="_compute_snapshot_metrics", digits=(16, 2)
    )
    pending_percent = fields.Float(
        string="Pendientes (%)", compute="_compute_snapshot_metrics", digits=(16, 2)
    )
    matched_percent = fields.Float(
        string="Coincidencias (%)", compute="_compute_snapshot_metrics", digits=(16, 2)
    )
    unexpected_percent = fields.Float(
        string="No previstos (%)", compute="_compute_snapshot_metrics", digits=(16, 2)
    )
    duplicate_percent = fields.Float(
        string="Duplicados (%)", compute="_compute_snapshot_metrics", digits=(16, 2)
    )
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", readonly=True)
    expected_value = fields.Monetary(string="Valor esperado", currency_field="currency_id", compute="_compute_snapshot_metrics")
    counted_value = fields.Monetary(string="Valor contado", currency_field="currency_id", compute="_compute_snapshot_metrics")
    shortage_value = fields.Monetary(string="Pérdida estimada", currency_field="currency_id", compute="_compute_snapshot_metrics")
    surplus_value = fields.Monetary(string="Sobrante estimado", currency_field="currency_id", compute="_compute_snapshot_metrics")
    net_adjustment_value = fields.Monetary(string="Impacto neto", currency_field="currency_id", compute="_compute_snapshot_metrics")
    high_impact_item_count = fields.Integer(string="Alto impacto", compute="_compute_snapshot_metrics")
    adjustment_candidate_count = fields.Integer(string="Líneas a ajustar", compute="_compute_snapshot_metrics")
    blocking_issue_count = fields.Integer(string="Bloqueos pendientes", compute="_compute_snapshot_metrics")
    adjustment_ready = fields.Boolean(string="Listo para ajustar", compute="_compute_snapshot_metrics")
    adjustment_readiness_text = fields.Char(string="Estado previo al ajuste", compute="_compute_snapshot_metrics")
    dashboard_last_update = fields.Datetime(
        string="Última actualización", compute="_compute_snapshot_metrics"
    )

    def _snapshot_headers(self):
        return self.env["setu.inventory.count.snapshot"].sudo().search([
            ("count_id", "in", self.ids)
        ])

    @api.depends(
        "session_ids.state",
        "line_ids.state",
        "line_ids.is_discrepancy_found",
    )
    def _compute_snapshot_metrics(self):
        headers = {
            header.count_id.id: header
            for header in self._snapshot_headers()
        } if self.ids else {}

        for count in self:
            header = headers.get(count.id)
            count.snapshot_ready = bool(header and header.ready)
            count.snapshot_date = header.snapshot_date if header else False
            count.expected_item_count = header.expected_item_count if header else 0
            count.counted_item_count = header.counted_item_count if header else 0
            count.pending_item_count = header.pending_item_count if header else 0
            count.matched_item_count = header.matched_item_count if header else 0
            count.difference_item_count = header.difference_item_count if header else 0
            count.zero_item_count = header.zero_item_count if header else 0
            count.unexpected_item_count = header.unexpected_item_count if header else 0
            count.duplicate_item_count = header.duplicate_item_count if header else 0
            count.expected_value = header.expected_value if header else 0.0
            count.counted_value = header.counted_value if header else 0.0
            count.shortage_value = header.shortage_value if header else 0.0
            count.surplus_value = header.surplus_value if header else 0.0
            count.net_adjustment_value = header.net_adjustment_value if header else 0.0
            count.high_impact_item_count = header.high_impact_item_count if header else 0
            count.adjustment_candidate_count = max(
                (header.difference_item_count - header.duplicate_item_count) if header else 0,
                0,
            )
            open_sessions = count.session_ids.filtered(
                lambda session: session.state not in ("Done", "Cancel")
            )
            pending_decisions = count.line_ids.filtered(
                lambda line: (
                    line.is_discrepancy_found
                    and line.state == "Pending Review"
                )
            )
            count.blocking_issue_count = (
                (header.pending_item_count + header.duplicate_item_count) if header else 0
            ) + len(open_sessions) + len(pending_decisions)
            count.adjustment_ready = bool(
                header and count.state == "To Be Approved" and not count.blocking_issue_count
            )
            if open_sessions:
                count.adjustment_readiness_text = "Hay sesiones abiertas"
            elif header and header.pending_item_count:
                count.adjustment_readiness_text = "Faltan productos/lotes por resolver"
            elif header and header.duplicate_item_count:
                count.adjustment_readiness_text = "Hay lecturas duplicadas por revisar"
            elif pending_decisions:
                count.adjustment_readiness_text = "Hay diferencias sin decisión"
            elif count.state == "To Be Approved":
                count.adjustment_readiness_text = "Listo para generar el ajuste"
            else:
                count.adjustment_readiness_text = "Conteo en proceso"
            count.progress_percent = header.progress_percent if header else 0.0
            count.difference_percent = header.difference_percent if header else 0.0
            expected = header.expected_item_count if header else 0
            denominator = expected or 1
            # El widget percentage de Odoo espera valores entre 0.0 y 1.0.
            # Ejemplo: 1.0 = 100%, 0.25 = 25%.
            count.expected_percent = 1.0 if expected else 0.0
            count.pending_percent = (
                (header.pending_item_count / denominator) if header else 0.0
            )
            count.matched_percent = (
                (header.matched_item_count / denominator) if header else 0.0
            )
            count.unexpected_percent = (
                (header.unexpected_item_count / denominator) if header else 0.0
            )
            count.duplicate_percent = (
                (header.duplicate_item_count / denominator) if header else 0.0
            )
            count.dashboard_last_update = header.last_update if header else False

    def _get_snapshot_header(self, create=False):
        self.ensure_one()
        Snapshot = self.env["setu.inventory.count.snapshot"].sudo()
        header = Snapshot.search([("count_id", "=", self.id)], limit=1)
        if not header and create:
            header = Snapshot.create({"count_id": self.id})
        return header

    def _snapshot_scope_locations(self):
        self.ensure_one()
        if not self.location_id:
            return self.env["stock.location"]
        Location = self.env["stock.location"].sudo()
        locations = Location.search([
            ("id", "child_of", self.location_id.id),
            ("usage", "=", "internal"),
        ])
        # child_of depende de parent_path; una ubicación creada dentro de la
        # misma transacción debe entrar siempre en su propia fotografía.
        if self.location_id.usage == "internal":
            locations |= self.location_id.sudo()
        return locations

    @api.model
    def _backfill_missing_inventory_snapshots(self):
        Header = self.env["setu.inventory.count.snapshot"].sudo()
        existing_count_ids = Header.search([]).mapped("count_id").ids
        counts = self.search([
            ("id", "not in", existing_count_ids),
            ("warehouse_id", "!=", False),
            ("location_id", "!=", False),
            ("state", "not in", ["Cancel", "Rejected"]),
        ])
        for count in counts:
            has_scans = bool(
                count.session_ids.mapped("session_line_ids").filtered(
                    lambda line: (
                        line.product_scanned
                        and line.product_id
                        and line.location_id
                    )
                )
            )
            # Nunca inventamos una fotografía histórica usando el stock actual.
            if not has_scans:
                count._prepare_inventory_snapshot()
        return True

    def _prepare_inventory_snapshot(self, force=False):
        """Fotografía stock.quant una sola vez por conteo."""
        SnapshotLine = self.env["setu.inventory.count.snapshot.line"].sudo()
        Quant = self.env["stock.quant"].sudo()

        for count in self:
            if not count.warehouse_id or not count.location_id:
                continue

            header = count._get_snapshot_header(create=True)
            if header.ready and not force:
                continue

            has_scans = bool(
                count.session_ids.mapped("session_line_ids").filtered(
                    lambda line: line.product_scanned
                )
            )
            if force and has_scans:
                raise ValidationError(
                    _(
                        "No puede reconstruir la información del conteo porque "
                        "ya existen lecturas físicas."
                    )
                )

            header.line_ids.unlink()
            locations = count._snapshot_scope_locations()
            grouped = defaultdict(float)

            if locations:
                # El snapshot debe ser consistente incluso dentro de la misma
                # transacción (tests, importaciones y cargas masivas).  Se
                # fuerza el flush y se agrega directamente en PostgreSQL para
                # evitar caché ORM y un recorrido de miles de stock.quant.
                Quant.flush_model(["product_id", "location_id", "lot_id", "quantity"])
                product_filter = count.product_ids.ids
                if product_filter:
                    self.env.cr.execute(
                        """
                            SELECT product_id, lot_id, location_id, SUM(quantity)
                              FROM stock_quant
                             WHERE location_id = ANY(%s)
                               AND product_id = ANY(%s)
                               AND quantity <> 0
                             GROUP BY product_id, lot_id, location_id
                        """,
                        (locations.ids, product_filter),
                    )
                else:
                    self.env.cr.execute(
                        """
                            SELECT product_id, lot_id, location_id, SUM(quantity)
                              FROM stock_quant
                             WHERE location_id = ANY(%s)
                               AND quantity <> 0
                             GROUP BY product_id, lot_id, location_id
                        """,
                        (locations.ids,),
                    )
                for product_id, lot_id, location_id, quantity in self.env.cr.fetchall():
                    product = self.env["product.product"].browse(product_id)
                    if not product.active:
                        continue
                    grouped[(product_id, lot_id or False, location_id)] += quantity

            vals_list = []
            for (product_id, lot_id, location_id), quantity in grouped.items():
                product = self.env["product.product"].browse(product_id)
                if float_is_zero(
                    quantity,
                    precision_rounding=product.uom_id.rounding,
                ):
                    continue
                vals_list.append({
                    "snapshot_id": header.id,
                    "product_id": product_id,
                    "lot_id": lot_id,
                    "location_id": location_id,
                    "expected_qty": quantity,
                    # Costo congelado al preparar el conteo; solo informativo.
                    "unit_cost": product.with_company(count.company_id).standard_price,
                    "counted_qty": 0.0,
                    "difference_qty": -quantity,
                    "status": "pending",
                })

            if vals_list:
                SnapshotLine.create(vals_list)

            header.write({
                "ready": True,
                "snapshot_date": fields.Datetime.now(),
            })
            count._refresh_persistent_kpis()

        return True

    def _ensure_snapshot_lines_for_session_line(self, session_line):
        self.ensure_one()
        header = self._get_snapshot_header(create=True)
        SnapshotLine = self.env["setu.inventory.count.snapshot.line"].sudo()
        base_domain = [
            ("snapshot_id", "=", header.id),
            ("product_id", "=", session_line.product_id.id),
            ("location_id", "=", session_line.location_id.id),
        ]

        if session_line.product_id.tracking == "serial":
            snapshots = SnapshotLine
            for serial in session_line.serial_number_ids:
                snapshot = SnapshotLine.search(
                    base_domain + [("lot_id", "=", serial.id)], limit=1
                )
                if not snapshot:
                    snapshot = SnapshotLine.create({
                        "snapshot_id": header.id,
                        "product_id": session_line.product_id.id,
                        "lot_id": serial.id,
                        "location_id": session_line.location_id.id,
                        "expected_qty": 0.0,
                        "unit_cost": session_line.product_id.with_company(
                            self.company_id
                        ).standard_price,
                        "unexpected": True,
                        "status": "unexpected",
                    })
                snapshots |= snapshot
            return snapshots

        snapshot = SnapshotLine.search(
            base_domain + [
                ("lot_id", "=", session_line.lot_id.id if session_line.lot_id else False)
            ],
            limit=1,
        )
        if not snapshot:
            snapshot = SnapshotLine.create({
                "snapshot_id": header.id,
                "product_id": session_line.product_id.id,
                "lot_id": session_line.lot_id.id if session_line.lot_id else False,
                "location_id": session_line.location_id.id,
                "expected_qty": 0.0,
                "unit_cost": session_line.product_id.with_company(
                    self.company_id
                ).standard_price,
                "unexpected": True,
                "status": "unexpected",
            })
        return snapshot

    def _ensure_snapshot_line_for_session_line(self, session_line):
        """Compatibilidad con llamadas antiguas que esperan un recordset."""
        return self._ensure_snapshot_lines_for_session_line(session_line)

    def _refresh_persistent_kpis(self):
        SnapshotLine = self.env["setu.inventory.count.snapshot.line"].sudo()
        table = SnapshotLine._table

        for count in self:
            header = count._get_snapshot_header(create=True)
            threshold = float(
                self.env["ir.config_parameter"].sudo().get_param(
                    "setu_inventory_count_management.high_impact_threshold",
                    500.0,
                ) or 500.0
            )

            SnapshotLine.flush_model([
                "snapshot_id","status","unexpected","duplicate",
                "expected_value","counted_value","impact_value","impact_abs",
            ])

            self.env.cr.execute(
                f"""
                    SELECT
                        COUNT(*) FILTER (
                            WHERE COALESCE(unexpected, FALSE) = FALSE
                        ),
                        COUNT(*) FILTER (
                            WHERE status = 'pending'
                              AND COALESCE(unexpected, FALSE) = FALSE
                        ),
                        COUNT(*) FILTER (
                            WHERE status = 'matched'
                              AND COALESCE(unexpected, FALSE) = FALSE
                        ),
                        COUNT(*) FILTER (WHERE status = 'zero'),
                        COUNT(*) FILTER (WHERE status = 'unexpected'),
                        COUNT(*) FILTER (WHERE status = 'duplicate'),
                        COUNT(*) FILTER (
                            WHERE status IN ('difference','zero','unexpected','duplicate')
                        ),
                        COALESCE(SUM(expected_value),0.0),
                        COALESCE(SUM(counted_value),0.0),
                        COALESCE(SUM(CASE
                            WHEN status IN ('difference','zero','unexpected')
                             AND impact_value < 0
                            THEN -impact_value ELSE 0 END),0.0),
                        COALESCE(SUM(CASE
                            WHEN status IN ('difference','zero','unexpected')
                             AND impact_value > 0
                            THEN impact_value ELSE 0 END),0.0),
                        COALESCE(SUM(CASE
                            WHEN status IN ('difference','zero','unexpected')
                            THEN impact_value ELSE 0 END),0.0),
                        COUNT(*) FILTER (
                            WHERE status IN ('difference','zero','unexpected')
                              AND impact_abs >= %s
                        )
                    FROM {table}
                    WHERE snapshot_id = %s
                """,
                (threshold,header.id),
            )
            row=self.env.cr.fetchone()
            (
                expected,pending,matched,zero,unexpected,duplicate,differences,
                expected_value,counted_value,shortage,surplus,net,high_impact,
            )=row
            counted=max(expected-pending,0)
            progress=(counted*100.0/expected) if expected else 0.0
            difference_percent=(differences*100.0/counted) if counted else 0.0
            header.write({
                "expected_item_count":expected,
                "counted_item_count":counted,
                "pending_item_count":pending,
                "matched_item_count":matched,
                "difference_item_count":differences,
                "zero_item_count":zero,
                "unexpected_item_count":unexpected,
                "duplicate_item_count":duplicate,
                "progress_percent":progress,
                "difference_percent":difference_percent,
                "expected_value":expected_value,
                "counted_value":counted_value,
                "shortage_value":shortage,
                "surplus_value":surplus,
                "net_adjustment_value":net,
                "high_impact_item_count":high_impact,
                "last_update":fields.Datetime.now(),
            })
            # Los campos gerenciales del conteo se calculan buscando esta
            # cabecera (no existe una dependencia ORM directa). Invalídalos
            # explícitamente para que no queden KPIs antiguos en caché.
            count.invalidate_recordset([
                "snapshot_ready", "snapshot_date", "expected_item_count",
                "counted_item_count", "pending_item_count", "matched_item_count",
                "difference_item_count", "zero_item_count", "unexpected_item_count",
                "duplicate_item_count", "progress_percent", "difference_percent",
                "expected_percent", "pending_percent", "matched_percent",
                "unexpected_percent", "duplicate_percent", "expected_value",
                "counted_value", "shortage_value", "surplus_value",
                "net_adjustment_value", "high_impact_item_count",
                "adjustment_candidate_count", "blocking_issue_count",
                "adjustment_ready", "adjustment_readiness_text",
                "dashboard_last_update",
            ])
        return True

    def action_refresh_inventory_snapshot(self):
        for count in self:
            count._prepare_inventory_snapshot(force=True)
        return True

    def write(self, vals):
        watched = {"warehouse_id", "location_id"}
        needs_rebuild = bool(watched.intersection(vals))
        if needs_rebuild:
            blocked = self.filtered(
                lambda count: count.session_ids.mapped("session_line_ids").filtered(
                    lambda line: line.product_scanned
                )
            )
            if blocked:
                raise ValidationError(
                    _(
                        "No puede cambiar el almacén o la ubicación después "
                        "de iniciar las lecturas del conteo."
                    )
                )

        result = super().write(vals)

        if needs_rebuild:
            for count in self:
                header = count._get_snapshot_header(create=False)
                if not count.warehouse_id or not count.location_id:
                    if header:
                        header.unlink()
                    continue
                count._prepare_inventory_snapshot(force=True)

        return result
