# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class InventoryCountSnapshotLineWorkflow(models.Model):
    _inherit = "setu.inventory.count.snapshot.line"

    closed_as_zero = fields.Boolean(
        string="No encontrado / cero", readonly=True, copy=False
    )
    recount_required = fields.Boolean(
        string="Requiere reconteo", readonly=True, copy=False
    )
    has_observation = fields.Boolean(
        string="Tiene observaciones", readonly=True, copy=False, index=True
    )
    observation_note = fields.Text(
        string="Observaciones PDA", readonly=True, copy=False
    )

    review_required = fields.Boolean(
        string="Para revisión",
        compute="_compute_review_fields",
        store=True,
        index=True,
    )
    review_reason = fields.Char(
        string="Motivo de revisión",
        compute="_compute_review_fields",
        store=True,
    )
    review_selected = fields.Boolean(
        string="Seleccionar",
        default=False,
        copy=False,
        index=True,
    )
    review_decision = fields.Selection(
        [
            ("pending", "Pendiente"),
            ("adjust", "Aprobar para ajuste"),
            ("recount", "Enviar a reconteo"),
            ("transfer", "Resolver por traslado"),
            ("discard", "Descartar"),
            ("resolved", "Resuelto"),
        ],
        string="Decisión",
        default="pending",
        copy=False,
        index=True,
    )
    reviewed_by_id = fields.Many2one(
        "res.users", string="Revisado por", readonly=True, copy=False
    )
    reviewed_at = fields.Datetime(
        string="Revisado el", readonly=True, copy=False
    )

    @api.depends(
        "status",
        "has_observation",
        "unexpected",
        "duplicate",
        "recount_required",
        "relocation_resolved",
    )
    def _compute_review_fields(self):
        for line in self:
            reasons = []
            if line.unexpected or line.status == "unexpected":
                reasons.append(_("Fuera de ubicación / no previsto"))
            if line.status == "difference":
                reasons.append(_("Diferencia de cantidad"))
            if line.status == "zero":
                reasons.append(_("No encontrado"))
            if line.duplicate:
                reasons.append(_("Lectura duplicada"))
            if line.has_observation:
                reasons.append(_("Observación de campo"))
            if line.recount_required:
                reasons.append(_("Reconteo requerido"))

            line.review_required = bool(reasons) and not line.relocation_resolved
            line.review_reason = " · ".join(reasons) if reasons else False


class StockInventoryCountWorkflow(models.Model):
    _inherit = "setu.stock.inventory.count"

    def _snapshot_problem_lines(self):
        self.ensure_one()
        return self.snapshot_line_ids.filtered(
            lambda line: line.review_required and not line.relocation_resolved
        )

    def _find_count_line_for_snapshot(self, snapshot_line):
        self.ensure_one()
        lines = self.line_ids.filtered(
            lambda line: line.product_id == snapshot_line.product_id
            and line.location_id == snapshot_line.location_id
        )
        if snapshot_line.product_id.tracking == "serial":
            return lines.filtered(
                lambda line: snapshot_line.lot_id in line.serial_number_ids
                or snapshot_line.lot_id in line.not_found_serial_number_ids
                or line.lot_id == snapshot_line.lot_id
            )[:1]
        return lines.filtered(lambda line: line.lot_id == snapshot_line.lot_id)[:1]

    def _find_session_lines_for_snapshot(self, snapshot_line):
        self.ensure_one()
        return self.session_ids.mapped("session_line_ids").filtered(
            lambda line: line.product_id == snapshot_line.product_id
            and line.location_id == snapshot_line.location_id
            and (
                (
                    snapshot_line.product_id.tracking == "serial"
                    and snapshot_line.lot_id in line.serial_number_ids
                )
                or (
                    snapshot_line.product_id.tracking != "serial"
                    and line.lot_id == snapshot_line.lot_id
                )
            )
        )

    def action_approve_matching_lines(self):
        """Aprueba en lote únicamente líneas que coinciden con la fotografía."""
        for count in self:
            if count.state not in ("In Progress", "To Be Approved"):
                raise ValidationError(
                    _("Solo puede aprobar coincidencias mientras el conteo está en proceso o por aprobar.")
                )
            matched = count.snapshot_line_ids.filtered(lambda line: line.status == "matched")
            if not matched:
                raise ValidationError(_("No existen coincidencias pendientes de aprobación."))

            count_lines = self.env["setu.stock.inventory.count.line"]
            session_lines = self.env["setu.inventory.count.session.line"]
            for snapshot_line in matched:
                count_lines |= count._find_count_line_for_snapshot(snapshot_line)
                session_lines |= count._find_session_lines_for_snapshot(snapshot_line)

            if count_lines:
                count_lines.write({"state": "Approve"})
            if session_lines:
                session_lines.write({"state": "Approve"})

            count.message_post(
                body=_("Se aprobaron automáticamente %s coincidencias sin divergencia.") % len(matched)
            )
        return True

    def action_mark_pending_as_zero(self):
        """Marca todos los pendientes como cero mediante una única actualización SQL."""
        self.ensure_one()
        if self.state not in ("In Progress", "To Be Approved"):
            raise ValidationError(
                _("Los pendientes solo pueden cerrarse como cero mientras el conteo está activo.")
            )
        if self.session_ids.filtered(lambda session: session.state not in ("Done", "Cancel")):
            raise ValidationError(
                _("Valide o cancele todas las sesiones antes de marcar pendientes como no encontrados.")
            )

        Snapshot = self.env["setu.inventory.count.snapshot.line"].sudo()
        pending = Snapshot.search([
            ("count_id", "=", self.id),
            ("status", "=", "pending"),
        ])
        if not pending:
            raise ValidationError(_("No existen productos/lotes pendientes de contar."))

        pending.flush_recordset(["expected_qty"])
        self.env.cr.execute(
            """
            UPDATE setu_inventory_count_snapshot_line
               SET counted_qty = 0,
                   difference_qty = -expected_qty,
                   status = 'zero',
                   closed_as_zero = TRUE,
                   recount_required = FALSE
             WHERE count_id = %s
               AND status = 'pending'
            """,
            [self.id],
        )
        pending.invalidate_recordset([
            "counted_qty", "difference_qty", "status",
            "closed_as_zero", "recount_required",
        ])

        self._refresh_persistent_kpis()
        sessions = self.session_ids.filtered(lambda s: s.state != "Cancel")
        if (
            sessions
            and not sessions.filtered(lambda s: s.state != "Done")
            and not self.pending_item_count
            and not self.duplicate_item_count
        ):
            self.state = "To Be Approved"

        self.message_post(body=_(
            "Se marcaron %s productos/lotes pendientes como no encontrados (cantidad física 0) "
            "mediante procesamiento masivo."
        ) % len(pending))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Pendientes procesados"),
                "message": _("%s posiciones fueron marcadas como cero.") % len(pending),
                "type": "success",
                "sticky": False,
            },
        }

    def _ensure_count_line_for_snapshot_adjustment(self, snapshot_line):
        """Garantiza una línea de control para una divergencia del snapshot."""
        self.ensure_one()
        CountLine = self.env["setu.stock.inventory.count.line"]
        count_line = self._find_count_line_for_snapshot(snapshot_line)
        vals = {
            "inventory_count_id": self.id,
            "product_id": snapshot_line.product_id.id,
            "location_id": snapshot_line.location_id.id,
            "theoretical_qty": snapshot_line.expected_qty,
            "qty_in_stock": snapshot_line.expected_qty,
            "counted_qty": snapshot_line.counted_qty,
            "state": "Approve",
            "is_system_generated": True,
        }
        tracking = snapshot_line.product_id.tracking
        if tracking == "lot":
            vals["lot_id"] = snapshot_line.lot_id.id if snapshot_line.lot_id else False
        elif tracking == "serial" and snapshot_line.lot_id:
            if snapshot_line.expected_qty > 0 and snapshot_line.counted_qty <= 0:
                vals["not_found_serial_number_ids"] = [(6, 0, snapshot_line.lot_id.ids)]
            elif snapshot_line.counted_qty > 0:
                vals["serial_number_ids"] = [(6, 0, snapshot_line.lot_id.ids)]

        if count_line:
            count_line.write(vals)
            return count_line
        return CountLine.create(vals)

    def action_accept_adjustment_candidates(self):
        """Acepta divergencias sin materializar líneas legacy.

        El snapshot es la fuente de verdad. Las líneas de ajuste se generan
        directamente desde él al aprobar.
        """
        for count in self:
            if count.state != "To Be Approved":
                raise ValidationError(
                    _("Las diferencias se aceptan cuando el conteo está Por aprobar.")
                )

            candidates = count.snapshot_line_ids.filtered(
                lambda line: (
                    line.status in ("difference", "zero", "unexpected")
                    and not line.relocation_resolved
                )
            )
            if not candidates:
                raise ValidationError(_("No existen diferencias listas para ajustar."))

            # Compatibilidad: aprobar estados legacy en SQL, sin recorrer miles
            # de registros ni disparar recomputes por cada línea.
            CountLine = self.env["setu.stock.inventory.count.line"]
            SessionLine = self.env["setu.inventory.count.session.line"]
            self.env.cr.execute(
                f"""
                UPDATE {CountLine._table}
                   SET state = 'Approve'
                 WHERE inventory_count_id = %s
                   AND state = 'Pending Review'
                """,
                [count.id],
            )
            self.env.cr.execute(
                f"""
                UPDATE {SessionLine._table}
                   SET state = 'Approve'
                 WHERE inventory_count_id = %s
                   AND state = 'Pending Review'
                """,
                [count.id],
            )
            CountLine.invalidate_model(["state"])
            SessionLine.invalidate_model(["state"])

            count.message_post(
                body=_(
                    "Se aceptaron %s diferencias directamente desde la fotografía del conteo."
                ) % len(candidates)
            )
        return True

    def action_accept_and_approve(self):
        """Acepta y aprueba usando snapshot + SQL masivo."""
        self.ensure_one()

        if self.count_id:
            return self.approve_inventory_count()
        if self.state != "To Be Approved":
            raise ValidationError(_("El conteo debe estar Por aprobar."))

        CountLine = self.env["setu.stock.inventory.count.line"]
        rejected = CountLine.search_count([
            ("inventory_count_id", "=", self.id),
            ("state", "=", "Reject"),
        ])
        if rejected:
            raise ValidationError(
                _("Existen líneas enviadas a reconteo. Apruebe primero el reconteo correspondiente.")
            )

        self._validate_controlled_closure()

        candidates = self.snapshot_line_ids.filtered(
            lambda line: (
                line.status in ("difference", "zero", "unexpected")
                and not line.relocation_resolved
            )
        )
        if not candidates:
            return self.action_approve_without_differences()

        self.action_accept_adjustment_candidates()

        # El ajuste se crea directamente desde snapshot; no se materializan
        # setu.stock.inventory.count.line para cada una de las divergencias.
        adjustment = self._create_inventory_adj_from_snapshot_fast(candidates)

        self.state = "Approved"
        self.message_post(
            body=_(
                "Conteo aprobado. Se aceptaron %(count)s diferencias y se generó "
                "el ajuste %(adjustment)s mediante procesamiento masivo."
            ) % {
                "count": len(candidates),
                "adjustment": adjustment.display_name if adjustment else _("sin líneas"),
            }
        )
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

    def _create_inventory_adj_from_snapshot_fast(self, snapshots):
        """Genera el ajuste directamente desde snapshot mediante create(vals_list)."""
        self.ensure_one()
        snapshots = snapshots.filtered(
            lambda line: (
                line.status in ("difference", "zero", "unexpected")
                and not line.relocation_resolved
                and line.review_decision == "adjust"
            )
        )
        if not snapshots:
            return self.env["setu.stock.inventory"]

        existing = self.inventory_adj_ids.filtered(lambda adj: adj.state != "cancel")
        if existing:
            return existing[:1]

        Inventory = self.env["setu.stock.inventory"]
        InventoryLine = self.env["setu.stock.inventory.line"]

        adjustment = Inventory.create({
            "location_id": self.location_id.id,
            "name": "ADJ - " + self.name,
            "inventory_count_id": self.id,
            "partner_id": self.approver_id.id,
            "date": self.inventory_count_date,
        })

        vals_list = []
        product_ids = set()
        for snap in snapshots:
            product = snap.product_id
            product_ids.add(product.id)
            vals = {
                "inventory_id": adjustment.id,
                "product_id": product.id,
                "product_uom_id": snap.uom_id.id or product.uom_id.id,
                "location_id": snap.location_id.id,
                "product_qty": snap.counted_qty,
                "theoretical_qty": snap.expected_qty,
                "prod_lot_id": snap.lot_id.id if snap.lot_id else False,
            }

            if product.tracking == "serial" and snap.lot_id:
                if snap.expected_qty > 0 and snap.counted_qty <= 0:
                    vals["not_found_serial_number_ids"] = [(6, 0, [snap.lot_id.id])]
                    vals["product_qty"] = 0.0
                elif snap.counted_qty > 0:
                    vals["serial_number_ids"] = [(6, 0, [snap.lot_id.id])]
                    vals["product_qty"] = 1.0

            vals_list.append(vals)

        if vals_list:
            InventoryLine.with_context(
                setu_bulk_count=True,
                prefetch_fields=False,
            ).create(vals_list)

        adjustment.action_start()
        adjustment.product_ids = [(6, 0, list(product_ids))]

        # No aplicar automáticamente miles de quants dentro del mismo RPC de
        # aprobación. El ajuste queda listo para validar desde su documento.
        return adjustment


    def action_approve_without_differences(self):
        """Aprueba directamente cuando el snapshot no tiene diferencias."""
        self.ensure_one()
        if self.count_id:
            raise ValidationError(_("Use «Aprobar reconteo» para cerrar un reconteo."))
        if self.state != "To Be Approved":
            raise ValidationError(_("El conteo debe estar Por aprobar."))

        self._refresh_persistent_kpis()
        snapshot_differences = self.snapshot_line_ids.filtered(
            lambda line: line.status in ("difference", "zero", "unexpected")
        )
        if snapshot_differences:
            raise ValidationError(
                _("Existen diferencias. Use «Aceptar diferencias y aprobar» o «Recontar diferencias».")
            )

        # El snapshot está limpio: cualquier Pending Review en modelos legacy
        # pertenece a una etapa previa y no debe bloquear el cierre.
        stale_count_lines = self.line_ids.filtered(
            lambda line: line.state == "Pending Review"
        )
        if stale_count_lines:
            stale_count_lines.write({"state": "Approve"})

        stale_session_lines = self.session_ids.mapped(
            "session_line_ids"
        ).filtered(
            lambda line: line.state == "Pending Review"
        )
        if stale_session_lines:
            stale_session_lines.write({"state": "Approve"})

        return self.approve_inventory_count()

    def action_approve_recount(self):
        """Compatibilidad: redirige al cierre controlado del reconteo."""
        return self.action_finalize_recount()

    def action_finalize_recount(self):
        """Finaliza sesiones completas, consolida el reconteo y regresa al conteo principal.

        Un reconteo nunca genera ajuste de inventario. Las decisiones tomadas
        en sus líneas se transfieren al conteo principal, que es el único que
        puede crear el ajuste definitivo.
        """
        self.ensure_one()

        if not self.count_id:
            raise ValidationError(
                _("Esta acción solo está disponible para reconteos.")
            )

        if self.state == "Approved":
            return {
                "type": "ir.actions.act_window",
                "name": _("Conteo principal"),
                "res_model": self._name,
                "res_id": self.count_id.id,
                "view_mode": "form",
                "target": "current",
            }

        sessions = self.session_ids.filtered(lambda session: session.state != "Cancel")
        if not sessions:
            raise ValidationError(
                _("El reconteo no tiene sesiones activas para finalizar.")
            )

        # Solo cerramos automáticamente una sesión cuando TODAS sus líneas
        # fueron realmente escaneadas. Así evitamos convertir silenciosamente
        # líneas no trabajadas en faltantes/cero.
        open_sessions = sessions.filtered(lambda session: session.state != "Done")
        for session in open_sessions:
            not_scanned = session.session_line_ids.filtered(
                lambda line: not line.product_scanned
            )
            if not_scanned:
                raise ValidationError(
                    _(
                        "La sesión %(session)s todavía tiene %(items)s línea(s) "
                        "sin escanear. Complete el reconteo antes de finalizarlo."
                    ) % {
                        "session": session.display_name,
                        "items": len(not_scanned),
                    }
                )
            session._finalize_pda_session_fast()

        self._refresh_persistent_kpis()

        if self.snapshot_line_ids.filtered(lambda line: line.status == "pending"):
            raise ValidationError(
                _("Todavía existen posiciones pendientes de reconteo.")
            )

        if self.snapshot_line_ids.filtered(lambda line: line.status == "duplicate"):
            raise ValidationError(
                _("Existen lecturas duplicadas en el reconteo. Revise esas líneas antes de finalizar.")
            )

        pending_decisions = self.snapshot_line_ids.filtered(
            lambda line: (
                line.review_required
                and line.review_decision == "pending"
            )
        )
        if pending_decisions:
            raise ValidationError(
                _(
                    "Quedan %(items)s línea(s) en «Para revisión» sin decisión. "
                    "Apruébelas para ajuste o descártelas antes de finalizar el reconteo."
                ) % {"items": len(pending_decisions)}
            )

        nested_recount = self.snapshot_line_ids.filtered(
            lambda line: (
                line.review_required
                and line.review_decision == "recount"
            )
        )
        if nested_recount:
            raise ValidationError(
                _("Un reconteo no puede dejar líneas enviadas a otro reconteo.")
            )

        parent = self.count_id
        self._consolidate_recount_into_parent()
        self.state = "Approved"

        self.message_post(
            body=_(
                "Reconteo finalizado. Los resultados y decisiones fueron "
                "consolidados en %(parent)s. Este reconteo no genera ajuste."
            ) % {"parent": parent.display_name}
        )

        # Si el conteo principal ya terminó sus sesiones, lo dejamos listo
        # para la aprobación global. El ajuste seguirá ocurriendo únicamente allí.
        parent_sessions = parent.session_ids.filtered(
            lambda session: session.state != "Cancel"
        )
        if (
            parent_sessions
            and not parent_sessions.filtered(lambda session: session.state != "Done")
        ):
            parent._refresh_persistent_kpis()
            if not parent.snapshot_line_ids.filtered(
                lambda line: line.status in ("pending", "duplicate")
            ):
                parent.state = "To Be Approved"

        parent._notify_count_event(
            "COUNT_REVIEW_UPDATED",
            {
                "count_id": parent.id,
                "recount_id": self.id,
                "recount_finalized": True,
            },
        )

        return {
            "type": "ir.actions.act_window",
            "name": _("Conteo principal"),
            "res_model": self._name,
            "res_id": parent.id,
            "view_mode": "form",
            "target": "current",
        }

    def _sync_observation_recount_flags(self):
        """Marca en snapshot los producto/lote/ubicación observados en campo."""
        self.ensure_one()
        if self.count_id:
            return self.env["setu.inventory.count.snapshot.line"]

        observed_events = self.scan_event_ids.filtered("has_observation")
        observed_snapshots = self.env["setu.inventory.count.snapshot.line"]

        # Reinicia únicamente las banderas de observación; una decisión previa de
        # reconteo puede conservarse hasta que el controlador la procese.
        self.snapshot_line_ids.write({
            "has_observation": False,
            "observation_note": False,
        })

        grouped_notes = {}
        for event in observed_events:
            snapshots = self.snapshot_line_ids.filtered(
                lambda snapshot:
                    snapshot.product_id == event.product_id
                    and snapshot.location_id == event.location_id
                    and snapshot.lot_id == event.lot_id
            )
            for snapshot in snapshots:
                observed_snapshots |= snapshot
                grouped_notes.setdefault(snapshot.id, [])
                note = (event.observation or "").strip()
                if note:
                    grouped_notes[snapshot.id].append(
                        "%s: %s" % (event.user_id.display_name, note)
                    )

        for snapshot in observed_snapshots:
            snapshot.write({
                "has_observation": True,
                "observation_note": "\n".join(grouped_notes.get(snapshot.id, [])) or False,
            })
        return observed_snapshots

    def _prepare_observed_count_lines_for_recount(self):
        """Deja rechazadas solo las líneas observadas para el futuro reconteo."""
        self.ensure_one()
        snapshots = self._sync_observation_recount_flags()
        if not snapshots:
            return self.env["setu.stock.inventory.count.line"]

        rejected = self.env["setu.stock.inventory.count.line"]
        for snapshot in snapshots:
            count_line = self._find_count_line_for_snapshot(snapshot)
            if not count_line:
                count_line = self._ensure_count_line_for_snapshot_adjustment(snapshot)
            rejected |= count_line

        if rejected:
            rejected.write({"state": "Reject"})
        return rejected

    def action_prepare_directed_recount(self):
        """Marca divergencias del conteo principal y crea un reconteo dirigido."""
        self.ensure_one()
        if self.count_id:
            raise ValidationError(
                _("Los reconteos no generan nuevos reconteos. Regrese al conteo principal.")
            )
        if self.state != "To Be Approved":
            raise ValidationError(_("El reconteo dirigido se prepara cuando el conteo está Por aprobar."))

        observed = self._sync_observation_recount_flags()
        problems = observed or self._snapshot_problem_lines()
        if not problems:
            raise ValidationError(_(
                "No existen productos con observaciones ni divergencias que requieran reconteo."
            ))

        rejected = self.env["setu.stock.inventory.count.line"]
        for snapshot_line in problems:
            snapshot_line.write({"recount_required": True})
            count_line = self._find_count_line_for_snapshot(snapshot_line)
            if not count_line:
                count_line = self._ensure_count_line_for_snapshot_adjustment(snapshot_line)
            rejected |= count_line

        if not rejected:
            raise ValidationError(
                _("No se encontraron líneas asociadas para preparar el reconteo.")
            )

        rejected.write({"state": "Reject"})
        self.line_ids.filtered(
            lambda line: line not in rejected and line.state == "Pending Review"
        ).write({"state": "Approve"})

        self.message_post(
            body=_("Se enviaron %s líneas a reconteo. Las observaciones PDA tienen prioridad.") % len(rejected)
        )
        return self.create_re_count()


    def _selected_review_lines(self):
        self.ensure_one()
        return self.snapshot_line_ids.filtered(
            lambda line: (
                line.review_required
                and line.review_selected
                and line.review_decision == "pending"
            )
        )

    def action_review_select_all(self):
        """Selecciona todas las líneas pendientes de decisión en «Para revisión»."""
        self.ensure_one()
        lines = self.snapshot_line_ids.filtered(
            lambda line: (
                line.review_required
                and line.review_decision == "pending"
            )
        )
        if not lines:
            raise ValidationError(
                _("No existen líneas pendientes de decisión en «Para revisión».")
            )
        lines.write({"review_selected": True})
        self._notify_count_event(
            "COUNT_REVIEW_UPDATED",
            {"count_id": self.id, "selected": len(lines)},
        )
        return True

    def action_review_unselect_all(self):
        """Quita la selección masiva sin modificar la decisión del Controlador."""
        self.ensure_one()
        lines = self.snapshot_line_ids.filtered("review_selected")
        if lines:
            lines.write({"review_selected": False})
            self._notify_count_event(
                "COUNT_REVIEW_UPDATED",
                {"count_id": self.id, "selected": 0},
            )
        return True

    def action_review_selected_approve(self):
        """Aprueba la revisión sin generar reconteo ni ajuste de inventario."""
        self.ensure_one()
        lines = self._selected_review_lines()
        if not lines:
            raise ValidationError(
                _("Seleccione al menos una línea pendiente de «Para revisión».")
            )

        lines.write({
            "review_selected": False,
            "review_decision": "resolved",
            "recount_required": False,
            "reviewed_by_id": self.env.user.id,
            "reviewed_at": fields.Datetime.now(),
        })

        # La aprobación de revisión significa que el Controlador acepta el
        # resultado informativo/observación y no requiere acción de stock.
        self._notify_count_event(
            "COUNT_REVIEW_UPDATED",
            {
                "count_id": self.id,
                "approved_review": len(lines),
            },
        )
        self._refresh_persistent_kpis()
        return True

    def action_review_selected_adjust(self):
        self.ensure_one()
        lines = self._selected_review_lines()
        if not lines:
            raise ValidationError(_("Seleccione al menos una línea de «Para revisión»."))
        lines.write({
            "review_decision": "adjust",
            "review_selected": False,
            "reviewed_by_id": self.env.user.id,
            "reviewed_at": fields.Datetime.now(),
        })
        self._notify_count_event("COUNT_REVIEW_UPDATED", {"count_id": self.id})
        return True

    def action_review_selected_discard(self):
        self.ensure_one()
        lines = self._selected_review_lines()
        if not lines:
            raise ValidationError(_("Seleccione al menos una línea de «Para revisión»."))
        lines.write({
            "review_decision": "discard",
            "review_selected": False,
            "reviewed_by_id": self.env.user.id,
            "reviewed_at": fields.Datetime.now(),
        })
        self._notify_count_event("COUNT_REVIEW_UPDATED", {"count_id": self.id})
        return True

    def action_review_selected_recount(self):
        self.ensure_one()
        lines = self._selected_review_lines()
        if not lines:
            raise ValidationError(_("Seleccione al menos una línea de «Para revisión»."))

        count_lines = self.env["setu.stock.inventory.count.line"]
        for snapshot in lines:
            count_lines |= self._ensure_count_line_for_snapshot_adjustment(snapshot)
        if count_lines:
            count_lines.write({"state": "Reject"})

        lines.write({
            "review_decision": "recount",
            "recount_required": True,
            "review_selected": False,
            "reviewed_by_id": self.env.user.id,
            "reviewed_at": fields.Datetime.now(),
        })
        self._notify_count_event("COUNT_REVIEW_UPDATED", {"count_id": self.id})
        return self.create_re_count()

    def _validate_review_decisions(self):
        for count in self.filtered(lambda c: not c.count_id):
            pending = count.snapshot_line_ids.filtered(
                lambda line: line.review_required and line.review_decision == "pending"
            )
            if pending:
                raise ValidationError(
                    _("Quedan %s ítems en «Para revisión» sin decisión.") % len(pending)
                )
            recount = count.snapshot_line_ids.filtered(
                lambda line: line.review_required and line.review_decision == "recount"
            )
            if recount:
                raise ValidationError(
                    _("Existen %s ítems enviados a reconteo que todavía no han sido resueltos.") % len(recount)
                )
        return True

    def action_approve_reviewed_count(self):
        """Cierre global: solo ajusta lo aprobado explícitamente por el Controlador."""
        self.ensure_one()
        if self.count_id:
            raise ValidationError(_("El reconteo se aprueba desde «Aprobar reconteo»."))
        if self.state != "To Be Approved":
            raise ValidationError(_("El conteo debe estar Por aprobar."))

        self._validate_controlled_closure()
        self._validate_review_decisions()

        adjustment_lines = self.snapshot_line_ids.filtered(
            lambda line: (
                line.review_required
                and line.review_decision == "adjust"
                and line.status in ("difference", "zero", "unexpected")
                and not line.relocation_resolved
            )
        )
        adjustment = self._create_inventory_adj_from_snapshot_fast(adjustment_lines)

        self.state = "Approved"
        self._notify_count_event("COUNT_APPROVED", {"count_id": self.id})
        self.message_post(
            body=_(
                "Conteo global aprobado. %(adjust)s posiciones fueron aprobadas para ajuste."
            ) % {"adjust": len(adjustment_lines)}
        )
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_open_financial_adjustment_preview(self):
        """Abre el impacto económico únicamente sobre la vista previa real."""
        self.ensure_one()
        self._refresh_persistent_kpis()
        preview = self.snapshot_line_ids.filtered(
            lambda line: line.status in ("difference", "zero", "unexpected")
        )
        Wizard = self.env["setu.inventory.count.financial.preview.wizard"]
        wizard = Wizard.create({
            "count_id": self.id,
            "currency_id": self.currency_id.id,
            "expected_value": self.expected_value,
            "shortage_value": self.shortage_value,
            "surplus_value": self.surplus_value,
            "net_adjustment_value": self.net_adjustment_value,
            "adjustment_candidate_count": len(preview),
            "high_impact_item_count": self.high_impact_item_count,
            "preview_line_ids": [(6, 0, preview.ids)],
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Impacto económico del ajuste"),
            "res_model": "setu.inventory.count.financial.preview.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "views": [(
                self.env.ref(
                    "setu_inventory_count_management.inventory_count_financial_preview_wizard_form"
                ).id,
                "form",
            )],
            "target": "new",
        }

    def _validate_controlled_closure(self):
        for count in self:
            if count.session_ids.filtered(lambda session: session.state not in ("Done", "Cancel")):
                raise ValidationError(
                    _("Existen sesiones abiertas. Valide o cancele todas las sesiones antes de continuar.")
                )
            pending = count.snapshot_line_ids.filtered(lambda line: line.status == "pending")
            if pending:
                raise ValidationError(
                    _(
                        "Quedan %s productos/lotes sin contar. Revise Pendientes y, "
                        "si físicamente no existen, use «Marcar pendientes como cero»."
                    ) % len(pending)
                )
            duplicates = count.snapshot_line_ids.filtered(lambda line: line.status == "duplicate")
            if duplicates:
                raise ValidationError(
                    _("Existen %s productos/lotes con lecturas duplicadas. Revise Duplicados antes de cerrar.") % len(duplicates)
                )
        return True

    def complete_counting(self):
        self._validate_controlled_closure()
        result = super().complete_counting()
        for count in self:
            if count.matched_item_count:
                count.action_approve_matching_lines()

            observed_lines = count._prepare_observed_count_lines_for_recount()
            if observed_lines:
                count.message_post(
                    body=_(
                        "Se detectaron %s línea(s) con observaciones de campo. "
                        "Quedaron preparadas exclusivamente para reconteo."
                    ) % len(observed_lines)
                )
        return result

    def _validate_adjustment_decisions(self):
        for count in self:
            pending_review = count.line_ids.filtered(
                lambda line: line.is_discrepancy_found and line.state == "Pending Review"
            )
            if pending_review:
                raise ValidationError(
                    _(
                        "Quedan %s diferencias sin decisión. Use «Aceptar diferencias y aprobar» "
                        "o «Recontar diferencias»."
                    ) % len(pending_review)
                )
        return True

    def approve_inventory_count(self):
        self.ensure_one()
        self._validate_controlled_closure()

        if (
            not self.count_id
            and self.env.context.get("setu_accept_all_differences")
        ):
            return self.action_accept_and_approve()

        self._validate_adjustment_decisions()
        return super().approve_inventory_count()

    def create_inventory_adj(self):
        """En sesión única, nunca ajusta líneas rechazadas enviadas a reconteo."""
        self.ensure_one()
        if self.type == "Single Session":
            rejected = self.line_ids.filtered(
                lambda line: line.is_discrepancy_found and line.state == "Reject"
            )
            if rejected:
                approved = self.line_ids.filtered(
                    lambda line: line.is_discrepancy_found and line.state == "Approve"
                )
                if approved:
                    self._create_inventory_adj(approved)
                return True
        return super().create_inventory_adj()
