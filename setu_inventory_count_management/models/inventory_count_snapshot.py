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
            session_lines = SessionLine.search([
                ("inventory_count_id", "=", snapshot_line.count_id.id),
                ("product_id", "=", snapshot_line.product_id.id),
                ("location_id", "=", snapshot_line.location_id.id),
                ("lot_id", "=", snapshot_line.lot_id.id if snapshot_line.lot_id else False),
                ("product_scanned", "=", True),
                ("session_id.state", "!=", "Cancel"),
            ], order="date_of_scanning, id")

            counted = sum(session_lines.mapped("scanned_qty"))
            scan_count = len(session_lines)
            first = session_lines[:1]
            last = session_lines[-1:]
            status = snapshot_line._status_from_values(
                snapshot_line.expected_qty,
                counted,
                scan_count,
                unexpected=snapshot_line.unexpected,
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
    dashboard_last_update = fields.Datetime(
        string="Última actualización", compute="_compute_snapshot_metrics"
    )

    def _snapshot_headers(self):
        return self.env["setu.inventory.count.snapshot"].sudo().search([
            ("count_id", "in", self.ids)
        ])

    @api.depends()
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
            count.progress_percent = header.progress_percent if header else 0.0
            count.difference_percent = header.difference_percent if header else 0.0
            expected = header.expected_item_count if header else 0
            counted = header.counted_item_count if header else 0
            denominator = expected or 1
            count.expected_percent = 100.0 if expected else 0.0
            count.pending_percent = (
                (header.pending_item_count * 100.0 / denominator) if header else 0.0
            )
            count.matched_percent = (
                (header.matched_item_count * 100.0 / denominator) if header else 0.0
            )
            count.unexpected_percent = (
                (header.unexpected_item_count * 100.0 / denominator) if header else 0.0
            )
            count.duplicate_percent = (
                (header.duplicate_item_count * 100.0 / denominator) if header else 0.0
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

    def _ensure_snapshot_line_for_session_line(self, session_line):
        self.ensure_one()
        header = self._get_snapshot_header(create=True)
        SnapshotLine = self.env["setu.inventory.count.snapshot.line"].sudo()
        domain = [
            ("snapshot_id", "=", header.id),
            ("product_id", "=", session_line.product_id.id),
            ("location_id", "=", session_line.location_id.id),
            ("lot_id", "=", session_line.lot_id.id if session_line.lot_id else False),
        ]
        snapshot_line = SnapshotLine.search(domain, limit=1)
        if not snapshot_line:
            snapshot_line = SnapshotLine.create({
                "snapshot_id": header.id,
                "product_id": session_line.product_id.id,
                "lot_id": session_line.lot_id.id if session_line.lot_id else False,
                "location_id": session_line.location_id.id,
                "expected_qty": 0.0,
                "unexpected": True,
                "status": "unexpected",
            })
        return snapshot_line

    def _refresh_persistent_kpis(self):
        SnapshotLine = self.env["setu.inventory.count.snapshot.line"].sudo()
        for count in self:
            header = count._get_snapshot_header(create=True)
            domain = [("snapshot_id", "=", header.id)]
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
