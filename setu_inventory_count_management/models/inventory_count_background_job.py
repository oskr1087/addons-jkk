# -*- coding: utf-8 -*-
import traceback

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class InventoryCountBackgroundJob(models.Model):
    _name = "setu.inventory.count.background.job"
    _description = "Proceso en segundo plano de conteo"
    _order = "create_date desc, id desc"

    count_id = fields.Many2one(
        "setu.stock.inventory.count",
        required=True,
        ondelete="cascade",
        index=True,
        string="Conteo",
    )
    session_id = fields.Many2one(
        "setu.inventory.count.session",
        ondelete="cascade",
        index=True,
        string="Sesión",
    )
    operation = fields.Selection([
        ("pending_zero", "Marcar pendientes como cero"),
        ("sync_sessions", "Sincronizar sesiones"),
        ("finalize_session", "Finalizar sesión"),
    ], required=True, index=True, string="Operación")
    state = fields.Selection([
        ("pending", "Pendiente"),
        ("running", "En proceso"),
        ("done", "Finalizado"),
        ("failed", "Error"),
    ], default="pending", required=True, index=True, string="Estado")
    total = fields.Integer(string="Total", readonly=True)
    processed = fields.Integer(string="Procesados", readonly=True)
    progress = fields.Float(string="Avance (%)", compute="_compute_progress")
    message = fields.Char(string="Detalle", readonly=True)
    error = fields.Text(string="Error", readonly=True)
    requested_by = fields.Many2one(
        "res.users", default=lambda self: self.env.user, readonly=True
    )

    @api.depends("total", "processed", "state")
    def _compute_progress(self):
        for job in self:
            if job.state == "done":
                job.progress = 100.0
            elif job.total:
                job.progress = min(job.processed * 100.0 / job.total, 100.0)
            else:
                job.progress = 0.0

    @api.model
    def _cron_process_inventory_jobs(self):
        """Obsoleto: desde 19.0.7.9.17 el flujo es síncrono optimizado."""
        self.sudo().search([
            ("state", "in", ["pending", "running"]),
        ]).write({
            "state": "done",
            "message": _("Proceso obsoleto cerrado; el conteo usa ejecución inmediata."),
        })
        return True

    def _process_one_batch(self):
        self.ensure_one()
        self.state = "running"
        if self.operation == "pending_zero":
            return self._process_pending_zero_batch()
        if self.operation == "sync_sessions":
            return self._process_sync_sessions_batch()
        if self.operation == "finalize_session":
            return self._process_finalize_session()
        raise ValidationError(_("Operación de proceso no soportada."))

    def _process_pending_zero_batch(self, batch_size=400):
        self.ensure_one()
        count = self.count_id.sudo()
        Snapshot = self.env["setu.inventory.count.snapshot.line"].sudo()
        CountLine = self.env["setu.stock.inventory.count.line"].sudo()

        domain = [
            ("count_id", "=", count.id),
            ("status", "=", "pending"),
        ]
        if not self.total:
            self.total = Snapshot.search_count(domain)

        pending = Snapshot.search(domain, order="id", limit=batch_size)
        if not pending:
            count._refresh_persistent_kpis()
            sessions = count.session_ids.filtered(lambda s: s.state != "Cancel")
            if (
                sessions
                and not sessions.filtered(lambda s: s.state != "Done")
                and not count.pending_item_count
                and not count.duplicate_item_count
            ):
                count.state = "To Be Approved"
            self.write({
                "state": "done",
                "processed": self.total,
                "message": _("Pendientes procesados correctamente."),
            })
            count.message_post(
                body=_("Finalizó el proceso masivo de pendientes = 0.")
            )
            return True

        product_ids = pending.product_id.ids
        location_ids = pending.location_id.ids
        existing = CountLine.search([
            ("inventory_count_id", "=", count.id),
            ("product_id", "in", product_ids),
            ("location_id", "in", location_ids),
        ])
        by_key = {}
        for line in existing:
            if line.product_id.tracking == "serial":
                lot_ids = (
                    line.serial_number_ids | line.not_found_serial_number_ids
                ).ids
                if line.lot_id:
                    lot_ids.append(line.lot_id.id)
                for lot_id in lot_ids:
                    by_key[(line.product_id.id, line.location_id.id, lot_id)] = line
            else:
                by_key[(
                    line.product_id.id,
                    line.location_id.id,
                    line.lot_id.id if line.lot_id else False,
                )] = line

        vals_list = []
        existing_to_zero = CountLine
        for snapshot in pending:
            key = (
                snapshot.product_id.id,
                snapshot.location_id.id,
                snapshot.lot_id.id if snapshot.lot_id else False,
            )
            line = by_key.get(key)
            if line:
                existing_to_zero |= line
                continue

            vals = {
                "inventory_count_id": count.id,
                "product_id": snapshot.product_id.id,
                "location_id": snapshot.location_id.id,
                "lot_id": (
                    snapshot.lot_id.id
                    if snapshot.product_id.tracking != "serial" and snapshot.lot_id
                    else False
                ),
                "theoretical_qty": snapshot.expected_qty,
                "qty_in_stock": snapshot.expected_qty,
                "counted_qty": 0.0,
                "state": "Approve",
                "is_system_generated": True,
            }
            if snapshot.product_id.tracking == "serial" and snapshot.lot_id:
                vals["not_found_serial_number_ids"] = [(6, 0, snapshot.lot_id.ids)]
            vals_list.append(vals)

        if vals_list:
            CountLine.with_context(
                setu_bulk_count=True,
                setu_skip_manual_audit=True,
            ).create(vals_list)

        if existing_to_zero:
            existing_to_zero.with_context(
                setu_bulk_count=True,
                setu_skip_manual_audit=True,
            ).write({
                "counted_qty": 0.0,
                "state": "Approve",
                "is_system_generated": True,
            })

        pending.write({
            "counted_qty": 0.0,
            "status": "zero",
            "closed_as_zero": True,
            "recount_required": False,
        })
        pending.flush_recordset(["expected_qty"])
        self.env.cr.execute(
            """
            UPDATE setu_inventory_count_snapshot_line
               SET difference_qty = -expected_qty
             WHERE id = ANY(%s)
            """,
            [pending.ids],
        )
        pending.invalidate_recordset(["difference_qty"])

        self.processed += len(pending)
        self.message = _(
            "Procesados %(processed)s de %(total)s pendientes."
        ) % {"processed": self.processed, "total": self.total}
        count._refresh_persistent_kpis()

        # Reprograma el cron inmediatamente sin esperar el siguiente intervalo.
        self._trigger_runner()
        return True

    def _process_sync_sessions_batch(self, batch_size=500):
        self.ensure_one()
        count = self.count_id.sudo()
        SessionLine = self.env["setu.inventory.count.session.line"].sudo()
        Snapshot = self.env["setu.inventory.count.snapshot.line"].sudo()

        domain = [
            ("inventory_count_id", "=", count.id),
            ("product_scanned", "=", True),
            ("session_id.state", "!=", "Cancel"),
        ]
        if not self.total:
            self.total = SessionLine.search_count(domain)

        lines = SessionLine.search(
            domain,
            order="id",
            offset=self.processed,
            limit=batch_size,
        )
        if not lines:
            # Refresco final en lote: considera sesiones Draft/Submitted/Done,
            # excepto Cancel; una sesión finalizada nunca queda fuera.
            count.snapshot_line_ids.sudo()._refresh_from_session_lines_bulk()
            count._sync_observation_recount_flags()
            count._ensure_location_progress_records()
            count._refresh_persistent_kpis()
            self.write({
                "state": "done",
                "processed": self.total,
                "message": _("Sesiones sincronizadas correctamente."),
            })
            count.message_post(
                body=_(
                    "Sincronización de sesiones finalizada: %s lecturas procesadas."
                ) % self.total
            )
            return True

        affected = Snapshot
        for line in lines:
            affected |= count._ensure_snapshot_lines_for_session_line(line)

        if affected:
            affected._refresh_from_session_lines_bulk()

        self.processed += len(lines)
        self.message = _(
            "Sincronizadas %(processed)s de %(total)s lecturas."
        ) % {"processed": self.processed, "total": self.total}
        self._trigger_runner()
        return True

    def _process_finalize_session(self):
        self.ensure_one()
        session = self.session_id.sudo()
        if not session:
            self.state = "failed"
            self.message = _("La sesión ya no existe.")
            return True

        # El RPC solo encola; la lógica original se ejecuta fuera de la petición
        # del navegador. Esto evita pérdidas de conexión en sesiones grandes.
        if session.state not in ("Submitted", "Done", "Cancel"):
            session.with_context(
                setu_background_finalize=True
            ).submit()

        count = session.inventory_count_id
        count._queue_background_inventory_job(
            "sync_sessions",
            message=_("Sincronización solicitada al finalizar la sesión."),
        )
        self.write({
            "state": "done",
            "total": 1,
            "processed": 1,
            "message": _("Sesión enviada y sincronización encolada."),
        })
        return True

    def _trigger_runner(self):
        cron = self.env.ref(
            "setu_inventory_count_management.ir_cron_inventory_count_background_jobs",
            raise_if_not_found=False,
        )
        if cron:
            cron.sudo()._trigger()
        return True

    def init(self):
        """Cierra trabajos heredados de las versiones con cola."""
        self.env.cr.execute("""
            UPDATE setu_inventory_count_background_job
               SET state = 'done',
                   message = 'Proceso obsoleto: ejecución inmediata habilitada'
             WHERE state IN ('pending', 'running')
        """)



class StockInventoryCountBackgroundProcess(models.Model):
    _inherit = "setu.stock.inventory.count"

    background_job_ids = fields.One2many(
        "setu.inventory.count.background.job",
        "count_id",
        string="Procesos en segundo plano",
        readonly=True,
    )
    background_job_running = fields.Boolean(
        compute="_compute_background_job_status",
        string="Procesando",
    )
    background_job_progress = fields.Float(
        compute="_compute_background_job_status",
        string="Avance del proceso",
    )
    background_job_message = fields.Char(
        compute="_compute_background_job_status",
        string="Proceso actual",
    )

    def _compute_background_job_status(self):
        for count in self:
            job = count.background_job_ids.filtered(
                lambda j: j.state in ("pending", "running")
            )[:1]
            count.background_job_running = bool(job)
            count.background_job_progress = job.progress if job else 0.0
            count.background_job_message = job.message if job else False

    def _queue_background_inventory_job(self, operation, session=False, message=False):
        """Compatibilidad: no crea nuevas colas."""
        self.ensure_one()
        if operation == "sync_sessions":
            self.action_sync_sessions_fast()
        elif operation == "finalize_session" and session:
            session._finalize_pda_session_fast()
        elif operation == "pending_zero":
            self.action_mark_pending_as_zero()
        return self.env["setu.inventory.count.background.job"]

    def action_sync_sessions_background(self):
        """Alias compatible hacia la sincronización inmediata."""
        return self.action_sync_sessions_fast()

