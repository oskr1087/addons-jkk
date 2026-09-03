# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import ValidationError


class InventoryCountSnapshotLineWorkflow(models.Model):
    _inherit = "setu.inventory.count.snapshot.line"

    closed_as_zero = fields.Boolean(
        string="No encontrado / cero", readonly=True, copy=False
    )
    recount_required = fields.Boolean(
        string="Requiere reconteo", readonly=True, copy=False
    )


class StockInventoryCountWorkflow(models.Model):
    _inherit = "setu.stock.inventory.count"

    def _snapshot_problem_lines(self):
        self.ensure_one()
        return self.snapshot_line_ids.filtered(
            lambda line: line.status in ("difference", "zero", "unexpected", "duplicate")
            and not line.relocation_resolved
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
        """Cierra pendientes como no encontrados usando el snapshot, sin consultar stock.quant."""
        CountLine = self.env["setu.stock.inventory.count.line"]
        for count in self:
            if count.state not in ("In Progress", "To Be Approved"):
                raise ValidationError(
                    _("Los pendientes solo pueden cerrarse como cero mientras el conteo está activo.")
                )
            if count.session_ids.filtered(lambda session: session.state not in ("Done", "Cancel")):
                raise ValidationError(
                    _("Valide o cancele todas las sesiones antes de marcar pendientes como no encontrados.")
                )

            pending = count.snapshot_line_ids.filtered(lambda line: line.status == "pending")
            if not pending:
                raise ValidationError(_("No existen productos/lotes pendientes de contar."))

            created = 0
            for snapshot_line in pending:
                count_line = count._find_count_line_for_snapshot(snapshot_line)
                if not count_line:
                    vals = {
                        "inventory_count_id": count.id,
                        "product_id": snapshot_line.product_id.id,
                        "location_id": snapshot_line.location_id.id,
                        "lot_id": (
                            snapshot_line.lot_id.id
                            if snapshot_line.product_id.tracking != "serial"
                            and snapshot_line.lot_id
                            else False
                        ),
                        "theoretical_qty": snapshot_line.expected_qty,
                        "qty_in_stock": snapshot_line.expected_qty,
                        "counted_qty": 0.0,
                        "state": "Approve",
                        "is_system_generated": True,
                    }
                    if snapshot_line.product_id.tracking == "serial" and snapshot_line.lot_id:
                        vals["not_found_serial_number_ids"] = [(6, 0, snapshot_line.lot_id.ids)]
                    CountLine.create(vals)
                    created += 1
                else:
                    count_line.write({
                        "counted_qty": 0.0,
                        "state": "Approve",
                        "is_system_generated": True,
                    })

                snapshot_line.write({
                    "counted_qty": 0.0,
                    "difference_qty": -snapshot_line.expected_qty,
                    "status": "zero",
                    "closed_as_zero": True,
                    "recount_required": False,
                })

            count._refresh_persistent_kpis()
            sessions = count.session_ids.filtered(lambda s: s.state != "Cancel")
            if (
                sessions
                and not sessions.filtered(lambda s: s.state != "Done")
                and not count.pending_item_count
                and not count.duplicate_item_count
            ):
                count.state = "To Be Approved"
            count.message_post(
                body=_(
                    "Se marcaron %s productos/lotes pendientes como no encontrados (cantidad física 0). "
                    "Se generaron %s líneas de control."
                ) % (len(pending), created)
            )
        return True

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
        """Acepta divergencias y garantiza líneas para el ajuste."""
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

            count_lines = self.env["setu.stock.inventory.count.line"]
            session_lines = self.env["setu.inventory.count.session.line"]
            for snapshot_line in candidates:
                count_lines |= count._ensure_count_line_for_snapshot_adjustment(snapshot_line)
                session_lines |= count._find_session_lines_for_snapshot(snapshot_line)

            if count_lines:
                count_lines.write({"state": "Approve"})
            if session_lines:
                session_lines.write({"state": "Approve"})

            count.message_post(
                body=_("Se aceptaron %s diferencias para el ajuste de inventario.") % len(candidates)
            )
        return True

    def action_accept_and_approve(self):
        """Acepta todas las diferencias pendientes y aprueba en una sola acción.

        El snapshot es la fuente de verdad, pero versiones anteriores del flujo
        pueden dejar líneas legacy en ``Pending Review`` aunque la divergencia
        del snapshot ya haya sido aceptada. Al elegir esta acción el usuario
        está aceptando explícitamente TODAS las diferencias del conteo, por lo
        que también cerramos esas líneas residuales antes de aprobar.
        """
        self.ensure_one()

        if self.count_id:
            return self.approve_inventory_count()

        if self.state != "To Be Approved":
            raise ValidationError(_("El conteo debe estar Por aprobar."))

        if self.line_ids.filtered(lambda line: line.state == "Reject"):
            raise ValidationError(
                _("Existen líneas enviadas a reconteo. Apruebe primero el reconteo correspondiente.")
            )

        # 1. Materializar y aceptar las divergencias reales del snapshot.
        self.action_accept_adjustment_candidates()

        # 2. Cerrar cualquier línea legacy residual del flujo anterior.
        pending_count_lines = self.line_ids.filtered(
            lambda line: line.state == "Pending Review"
        )
        if pending_count_lines:
            pending_count_lines.write({"state": "Approve"})

        pending_session_lines = self.session_ids.mapped("session_line_ids").filtered(
            lambda line: line.state == "Pending Review"
        )
        if pending_session_lines:
            pending_session_lines.write({"state": "Approve"})

        # 3. Releer desde BD antes de la validación final.
        self.flush_recordset()
        self.invalidate_recordset()
        self.line_ids.invalidate_recordset(["state"])

        remaining = self.line_ids.filtered(
            lambda line: line.state == "Pending Review"
        )
        if remaining:
            raise ValidationError(
                _(
                    "No fue posible resolver automáticamente %(count)s línea(s) pendientes. "
                    "Revise esas líneas antes de aprobar."
                ) % {"count": len(remaining)}
            )

        self.message_post(
            body=_(
                "Se aceptaron todas las diferencias pendientes. "
                "El conteo se aprobará y el ajuste se generará automáticamente."
            )
        )

        # 4. Aprobar + crear ajuste + desbloqueo normal del flujo.
        # El contexto indica que el usuario ya tomó explícitamente la decisión
        # de aceptar TODAS las diferencias. approve_inventory_count vuelve a
        # normalizar cualquier línea residual creada durante el mismo flujo.
        return self.with_context(
            setu_accept_all_differences=True
        ).approve_inventory_count()

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
        """Cierra un reconteo y consolida su resultado en el conteo principal."""
        self.ensure_one()
        if not self.count_id:
            raise ValidationError(_("Esta acción solo está disponible para reconteos."))
        return self.approve_inventory_count()

    def action_prepare_directed_recount(self):
        """Marca divergencias del conteo principal y crea un reconteo dirigido."""
        self.ensure_one()
        if self.count_id:
            raise ValidationError(
                _("Los reconteos no generan nuevos reconteos. Regrese al conteo principal.")
            )
        if self.state != "To Be Approved":
            raise ValidationError(_("El reconteo dirigido se prepara cuando el conteo está Por aprobar."))

        problems = self._snapshot_problem_lines()
        if not problems:
            raise ValidationError(_("No existen divergencias que requieran reconteo."))

        rejected = self.env["setu.stock.inventory.count.line"]
        for snapshot_line in problems:
            snapshot_line.write({"recount_required": True})
            rejected |= self._find_count_line_for_snapshot(snapshot_line)

        if not rejected:
            raise ValidationError(
                _("No se encontraron líneas de conteo asociadas a las divergencias. Revise primero las sesiones.")
            )

        rejected.write({"state": "Reject"})
        self.line_ids.filtered(
            lambda line: line not in rejected and line.state == "Pending Review"
        ).write({"state": "Approve"})

        self.message_post(
            body=_("Se enviaron %s líneas con divergencia a reconteo.") % len(rejected)
        )
        return self.create_re_count()


    def action_open_financial_adjustment_preview(self):
        """Muestra exactamente las líneas con impacto antes de crear el ajuste."""
        self.ensure_one()
        self._refresh_persistent_kpis()
        return {
            "type": "ir.actions.act_window",
            "name": _("Vista previa del ajuste"),
            "res_model": "setu.inventory.count.snapshot.line",
            "view_mode": "list",
            "views": [(
                self.env.ref(
                    "setu_inventory_count_management.setu_inventory_count_snapshot_line_list"
                ).id,
                "list",
            )],
            "domain": [
                ("count_id", "=", self.id),
                ("status", "in", ["difference", "zero", "unexpected"]),
            ],
            "context": {
                "create": False,
                "delete": False,
            },
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
        self._validate_controlled_closure()
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
