# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_is_zero


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
    high_impact = fields.Boolean(string="Alto impacto", compute="_compute_financial_values", readonly=True)
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
    unexpected = fields.Boolean(string="No previsto", readonly=True)
    duplicate = fields.Boolean(string="Posible duplicado", readonly=True)
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
        seen = set()
        for vals in vals_list:
            key = (
                vals.get("snapshot_id"),
                vals.get("product_id"),
                vals.get("lot_id") or False,
                vals.get("location_id"),
            )
            if key in seen:
                raise ValidationError(
                    _("La fotografía contiene duplicado el mismo producto, lote y ubicación.")
                )
            seen.add(key)
            if self.search_count([
                ("snapshot_id", "=", key[0]),
                ("product_id", "=", key[1]),
                ("lot_id", "=", key[2]),
                ("location_id", "=", key[3]),
            ]):
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
        return self.env["stock.location"].sudo().search([
            ("id", "child_of", self.location_id.id),
            ("usage", "=", "internal"),
            ("company_id", "in", [False, self.company_id.id]),
        ])

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
                quants = Quant.search([
                    ("location_id", "in", locations.ids),
                    ("quantity", "!=", 0),
                    ("product_id.active", "=", True),
                ])
                for quant in quants:
                    grouped[(
                        quant.product_id.id,
                        quant.lot_id.id or False,
                        quant.location_id.id,
                    )] += quant.quantity

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
        for count in self:
            header = count._get_snapshot_header(create=True)
            domain = [("snapshot_id", "=", header.id)]

            # Compatibilidad con snapshots creados antes de incorporar la
            # visualización económica: completamos el costo sin reconstruir
            # ni volver a consultar existencias.
            legacy_cost_lines = SnapshotLine.search(domain + [("unit_cost", "=", 0.0)])
            for legacy_line in legacy_cost_lines:
                legacy_line.unit_cost = legacy_line.product_id.with_company(
                    count.company_id
                ).standard_price
            grouped = SnapshotLine._read_group(
                domain,
                groupby=["status"],
                aggregates=["__count"],
            )
            by_status = {
                status: qty
                for status, qty in grouped
                if status
            }

            expected = SnapshotLine.search_count(
                domain + [("unexpected", "=", False)]
            )
            pending = by_status.get("pending", 0)
            matched = by_status.get("matched", 0)
            zero = by_status.get("zero", 0)
            unexpected = SnapshotLine.search_count(
                domain + [("unexpected", "=", True)]
            )
            duplicate = SnapshotLine.search_count(
                domain + [("duplicate", "=", True)]
            )
            differences = sum(
                by_status.get(status, 0)
                for status in ("difference", "zero", "unexpected", "duplicate")
            )
            financial = SnapshotLine._read_group(
                domain,
                aggregates=["expected_value:sum", "counted_value:sum"],
            )
            expected_value = counted_value = 0.0
            if financial:
                expected_value, counted_value = financial[0]

            # Pendientes y duplicados no forman parte de la vista previa
            # económica porque todavía no representan un ajuste aprobado.
            actionable_lines = SnapshotLine.search(
                domain + [("status", "in", ["difference", "zero", "unexpected"])]
            )
            net_value = sum(actionable_lines.mapped("impact_value"))
            shortage_value = sum(
                -line.impact_value for line in actionable_lines if line.impact_value < 0
            )
            surplus_value = sum(
                line.impact_value for line in actionable_lines if line.impact_value > 0
            )
            threshold = float(
                self.env["ir.config_parameter"].sudo().get_param(
                    "setu_inventory_count_management.high_impact_threshold", 500.0
                ) or 500.0
            )
            high_impact = len(
                actionable_lines.filtered(lambda line: line.impact_abs >= threshold)
            )
            counted = max(expected - pending, 0)
            progress = (counted * 100.0 / expected) if expected else 100.0
            difference_percent = (
                differences * 100.0 / counted if counted else 0.0
            )

            header.write({
                "expected_item_count": expected,
                "counted_item_count": counted,
                "pending_item_count": pending,
                "matched_item_count": matched,
                "difference_item_count": differences,
                "zero_item_count": zero,
                "unexpected_item_count": unexpected,
                "duplicate_item_count": duplicate,
                "progress_percent": progress,
                "difference_percent": difference_percent,
                "expected_value": expected_value,
                "counted_value": counted_value,
                "shortage_value": shortage_value,
                "surplus_value": surplus_value,
                "net_adjustment_value": net_value,
                "high_impact_item_count": high_impact,
                "last_update": fields.Datetime.now(),
            })
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
