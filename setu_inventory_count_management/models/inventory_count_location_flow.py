# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero


class InventoryCountLocationProgress(models.Model):
    _name = "setu.inventory.count.location.progress"
    _description = "Avance del conteo por ubicación"
    _order = "location_id"

    count_id = fields.Many2one(
        "setu.stock.inventory.count",
        required=True,
        ondelete="cascade",
        index=True,
        string="Conteo",
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        related="count_id.warehouse_id",
        store=True,
        readonly=True,
    )
    location_id = fields.Many2one(
        "stock.location",
        required=True,
        ondelete="cascade",
        index=True,
        string="Ubicación",
    )
    state = fields.Selection(
        [
            ("not_started", "Sin contar"),
            ("in_progress", "En proceso"),
            ("done", "Finalizada"),
        ],
        compute="_compute_live_metrics",
        string="Estado",
    )
    expected_position_count = fields.Integer(
        compute="_compute_live_metrics",
        string="Posiciones esperadas",
    )
    scanned_position_count = fields.Integer(
        compute="_compute_live_metrics",
        string="Posiciones leídas",
    )
    pending_position_count = fields.Integer(
        compute="_compute_live_metrics",
        string="Pendientes",
    )
    difference_position_count = fields.Integer(
        compute="_compute_live_metrics",
        string="Diferencias",
    )
    progress_percent = fields.Float(
        compute="_compute_live_metrics",
        string="Avance (%)",
        digits=(16, 2),
    )
    active_user_ids = fields.Many2many(
        "res.users",
        compute="_compute_live_metrics",
        string="Usuarios activos",
    )
    participant_user_ids = fields.Many2many(
        "res.users",
        compute="_compute_live_metrics",
        string="Participantes",
    )
    started_at = fields.Datetime(string="Iniciada el", readonly=True)
    last_scan_at = fields.Datetime(string="Última lectura", readonly=True)
    finished_at = fields.Datetime(string="Finalizada el", readonly=True)
    finished_user_ids = fields.Many2many(
        "res.users",
        "setu_location_progress_finished_user_rel",
        "progress_id",
        "user_id",
        string="Finalizada por",
        readonly=True,
    )

    _count_location_unique = models.Constraint(
        "UNIQUE(count_id, location_id)",
        "La ubicación ya existe en el control de avance de este conteo.",
    )

    def _compute_live_metrics(self):
        Snapshot = self.env["setu.inventory.count.snapshot.line"].sudo()
        SessionLine = self.env["setu.inventory.count.session.line"].sudo()
        Context = self.env["setu.inventory.count.session.user.context"].sudo()

        for progress in self:
            snapshots = Snapshot.search([
                ("count_id", "=", progress.count_id.id),
                ("location_id", "=", progress.location_id.id),
            ])
            expected = snapshots.filtered(lambda line: not line.unexpected)
            pending = expected.filtered(
                lambda line: line.status == "pending" and not line.closed_as_zero
            )
            scanned = snapshots.filtered(lambda line: line.scan_count > 0)
            differences = snapshots.filtered(
                lambda line: line.status in (
                    "difference", "zero", "unexpected", "duplicate"
                )
            )

            session_lines = SessionLine.search([
                ("inventory_count_id", "=", progress.count_id.id),
                ("location_id", "=", progress.location_id.id),
                ("product_scanned", "=", True),
                ("session_id.state", "!=", "Cancel"),
            ])
            participants = session_lines.mapped("user_ids")

            contexts = Context.search([
                ("session_id", "in", progress.count_id.session_ids.ids),
                ("current_location_id", "=", progress.location_id.id),
                ("finished", "=", False),
            ])
            active_users = contexts.mapped("user_id")

            denominator = len(expected)
            progress.expected_position_count = denominator
            progress.scanned_position_count = len(scanned)
            progress.pending_position_count = len(pending)
            progress.difference_position_count = len(differences)
            progress.progress_percent = (
                min(len(scanned), denominator) * 100.0 / denominator
                if denominator else (100.0 if session_lines else 0.0)
            )
            progress.active_user_ids = active_users
            progress.participant_user_ids = participants | active_users

            if active_users:
                progress.state = "in_progress"
            elif progress.finished_at:
                progress.state = "done"
            elif progress.started_at or session_lines:
                progress.state = "in_progress"
            else:
                progress.state = "not_started"

    def _mark_started(self, user=None):
        now = fields.Datetime.now()
        for progress in self:
            vals = {
                "last_scan_at": now,
                "finished_at": False,
            }
            if not progress.started_at:
                vals["started_at"] = now
            progress.write(vals)
        return True

    def _mark_finished_by(self, user):
        Context = self.env["setu.inventory.count.session.user.context"].sudo()
        now = fields.Datetime.now()
        for progress in self:
            progress.finished_user_ids = [(4, user.id)]
            active_other = Context.search_count([
                ("session_id", "in", progress.count_id.session_ids.ids),
                ("current_location_id", "=", progress.location_id.id),
                ("finished", "=", False),
            ])
            if not active_other:
                progress.finished_at = now
        return True


class InventoryCountRelocationIssue(models.Model):
    _name = "setu.inventory.count.relocation.issue"
    _description = "Producto encontrado en otra ubicación"
    _order = "state, product_id, lot_id, found_location_id"

    count_id = fields.Many2one(
        "setu.stock.inventory.count",
        required=True,
        ondelete="cascade",
        index=True,
        string="Conteo",
    )
    snapshot_line_id = fields.Many2one(
        "setu.inventory.count.snapshot.line",
        required=True,
        ondelete="cascade",
        index=True,
        string="Lectura encontrada",
    )
    product_id = fields.Many2one(
        "product.product",
        related="snapshot_line_id.product_id",
        store=True,
        readonly=True,
    )
    lot_id = fields.Many2one(
        "stock.lot",
        related="snapshot_line_id.lot_id",
        store=True,
        readonly=True,
    )
    found_location_id = fields.Many2one(
        "stock.location",
        related="snapshot_line_id.location_id",
        store=True,
        readonly=True,
        string="Ubicación física encontrada",
    )
    found_qty = fields.Float(
        related="snapshot_line_id.counted_qty",
        string="Cantidad encontrada",
        readonly=True,
    )
    resolved_qty = fields.Float(string="Cantidad trasladada", readonly=True)
    remaining_qty = fields.Float(
        compute="_compute_remaining_qty",
        string="Pendiente de trasladar",
    )
    candidate_source_location_ids = fields.Many2many(
        "stock.location",
        compute="_compute_candidate_sources",
        string="Ubicaciones origen posibles",
    )
    source_location_id = fields.Many2one(
        "stock.location",
        string="Viene de",
    )
    quantity_to_move = fields.Float(
        string="Cantidad a mover",
        digits="Product Unit of Measure",
    )
    state = fields.Selection(
        [
            ("pending", "Por resolver"),
            ("partial", "Parcial"),
            ("resolved", "Resuelto"),
        ],
        default="pending",
        required=True,
        index=True,
    )
    resolution_line_ids = fields.One2many(
        "setu.inventory.count.relocation.line",
        "issue_id",
        string="Traslados realizados",
        readonly=True,
    )
    last_picking_id = fields.Many2one(
        "stock.picking",
        string="Último traslado",
        readonly=True,
    )

    _snapshot_unique = models.Constraint(
        "UNIQUE(snapshot_line_id)",
        "Ya existe una incidencia de ubicación para esta lectura.",
    )

    @api.depends("found_qty", "resolved_qty")
    def _compute_remaining_qty(self):
        for issue in self:
            issue.remaining_qty = max(
                (issue.found_qty or 0.0) - (issue.resolved_qty or 0.0),
                0.0,
            )

    @api.depends(
        "product_id", "lot_id", "found_location_id",
        "count_id.location_id", "resolved_qty", "found_qty",
    )
    def _compute_candidate_sources(self):
        Quant = self.env["stock.quant"].sudo()
        for issue in self:
            locations = self.env["stock.location"]
            if (
                issue.product_id
                and issue.found_location_id
                and issue.count_id.location_id
            ):
                domain = [
                    ("product_id", "=", issue.product_id.id),
                    ("location_id", "child_of", issue.count_id.location_id.id),
                    ("location_id.usage", "=", "internal"),
                    ("location_id", "!=", issue.found_location_id.id),
                    ("quantity", ">", 0),
                ]
                if issue.product_id.tracking != "none":
                    domain.append(
                        ("lot_id", "=", issue.lot_id.id if issue.lot_id else False)
                    )
                quants = Quant.search(domain)
                locations = quants.mapped("location_id")
            issue.candidate_source_location_ids = locations

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for issue in records:
            if not issue.quantity_to_move:
                issue.quantity_to_move = issue.remaining_qty
        return records

    def _available_source_qty(self):
        self.ensure_one()
        Quant = self.env["stock.quant"].sudo()
        domain = [
            ("product_id", "=", self.product_id.id),
            ("location_id", "=", self.source_location_id.id),
        ]
        if self.product_id.tracking != "none":
            domain.append(("lot_id", "=", self.lot_id.id if self.lot_id else False))
        return sum(Quant.search(domain).mapped("quantity"))

    def _create_internal_transfer(self, quantity):
        self.ensure_one()
        warehouse = self.count_id.warehouse_id
        picking_type = warehouse.int_type_id
        if not picking_type:
            raise ValidationError(_(
                "El almacén %s no tiene un tipo de operación de transferencias internas."
            ) % warehouse.display_name)

        picking = self.env["stock.picking"].sudo().create({
            "picking_type_id": picking_type.id,
            "location_id": self.source_location_id.id,
            "location_dest_id": self.found_location_id.id,
            "origin": "%s · corrección de ubicación" % self.count_id.display_name,
        })

        move_vals = {
            "name": self.product_id.display_name,
            "product_id": self.product_id.id,
            "product_uom_qty": quantity,
            "product_uom": self.product_id.uom_id.id,
            "location_id": self.source_location_id.id,
            "location_dest_id": self.found_location_id.id,
            "picking_id": picking.id,
        }
        move = self.env["stock.move"].sudo().create(move_vals)
        picking.action_confirm()
        picking.action_assign()

        MoveLine = self.env["stock.move.line"].sudo()
        move_lines = move.move_line_ids
        qty_field = (
            "quantity"
            if "quantity" in MoveLine._fields
            else "qty_done"
            if "qty_done" in MoveLine._fields
            else False
        )
        if not qty_field:
            raise ValidationError(_(
                "No se encontró el campo de cantidad realizada en stock.move.line."
            ))

        if not move_lines:
            ml_vals = {
                "move_id": move.id,
                "picking_id": picking.id,
                "product_id": self.product_id.id,
                "product_uom_id": self.product_id.uom_id.id,
                "location_id": self.source_location_id.id,
                "location_dest_id": self.found_location_id.id,
                qty_field: quantity,
            }
            if self.lot_id:
                ml_vals["lot_id"] = self.lot_id.id
            MoveLine.create(ml_vals)
        else:
            remaining = quantity
            for line in move_lines:
                if remaining <= 0:
                    line.write({qty_field: 0.0})
                    continue
                available = line.quantity_product_uom if (
                    "quantity_product_uom" in line._fields
                ) else remaining
                done = min(remaining, available or remaining)
                vals = {qty_field: done}
                if self.lot_id:
                    vals["lot_id"] = self.lot_id.id
                line.write(vals)
                remaining -= done
            if remaining > 0:
                ml_vals = {
                    "move_id": move.id,
                    "picking_id": picking.id,
                    "product_id": self.product_id.id,
                    "product_uom_id": self.product_id.uom_id.id,
                    "location_id": self.source_location_id.id,
                    "location_dest_id": self.found_location_id.id,
                    qty_field: remaining,
                }
                if self.lot_id:
                    ml_vals["lot_id"] = self.lot_id.id
                MoveLine.create(ml_vals)

        result = picking.button_validate()
        if isinstance(result, dict) and result.get("res_model"):
            raise ValidationError(_(
                "Odoo solicitó una operación adicional al validar el traslado %s. "
                "Abra el traslado y complételo manualmente antes de continuar."
            ) % picking.display_name)
        return picking

    def _update_snapshot_after_transfer(self, quantity):
        self.ensure_one()
        Snapshot = self.env["setu.inventory.count.snapshot.line"].sudo()
        destination = self.snapshot_line_id
        source = Snapshot.search([
            ("count_id", "=", self.count_id.id),
            ("product_id", "=", self.product_id.id),
            ("location_id", "=", self.source_location_id.id),
            ("lot_id", "=", self.lot_id.id if self.lot_id else False),
        ], limit=1)

        destination.relocation_resolved_qty += quantity
        if source:
            source.relocation_resolved_qty += quantity

        for snapshot, direction in ((destination, 1.0), (source, -1.0)):
            if not snapshot:
                continue
            effective_expected = (
                snapshot.expected_qty
                + direction * snapshot.relocation_resolved_qty
            )
            remaining_difference = snapshot.counted_qty - effective_expected
            rounding = snapshot.product_id.uom_id.rounding
            if float_is_zero(
                remaining_difference,
                precision_rounding=rounding,
            ):
                snapshot.write({
                    "status": "relocated",
                    "relocation_resolved": True,
                })

            count_line = self.count_id._find_count_line_for_snapshot(snapshot)
            if not count_line:
                count_line = self.count_id._ensure_count_line_for_snapshot_adjustment(
                    snapshot
                )
            count_line.write({
                "theoretical_qty": effective_expected,
                "qty_in_stock": effective_expected,
                "counted_qty": snapshot.counted_qty,
                "state": "Approve",
            })

    def action_create_internal_transfer(self):
        if not self.env.user.has_group(
            "setu_inventory_count_management.group_setu_inventory_count_manager"
        ):
            raise UserError(_(
                "Solo un Controlador o Administrador del conteo puede generar "
                "traslados internos para corregir ubicaciones."
            ))
        for issue in self:
            if issue.state == "resolved":
                continue
            if not issue.source_location_id:
                raise ValidationError(_("Seleccione la ubicación de donde viene el producto."))
            if issue.source_location_id not in issue.candidate_source_location_ids:
                raise ValidationError(_(
                    "La ubicación seleccionada no tiene existencia disponible para este producto/lote."
                ))
            if issue.source_location_id == issue.found_location_id:
                raise ValidationError(_("La ubicación origen y destino no pueden ser iguales."))

            quantity = issue.quantity_to_move or issue.remaining_qty
            if quantity <= 0:
                raise ValidationError(_("Ingrese una cantidad mayor a cero."))
            if float_compare(
                quantity,
                issue.remaining_qty,
                precision_rounding=issue.product_id.uom_id.rounding,
            ) > 0:
                raise ValidationError(_(
                    "La cantidad a mover no puede superar la cantidad pendiente (%s)."
                ) % issue.remaining_qty)

            available = issue._available_source_qty()
            if float_compare(
                quantity,
                available,
                precision_rounding=issue.product_id.uom_id.rounding,
            ) > 0:
                raise ValidationError(_(
                    "La ubicación %s solo tiene %s disponibles para este producto/lote."
                ) % (issue.source_location_id.display_name, available))

            source = issue.source_location_id
            picking = issue._create_internal_transfer(quantity)

            self.env["setu.inventory.count.relocation.line"].sudo().create({
                "issue_id": issue.id,
                "source_location_id": source.id,
                "quantity": quantity,
                "picking_id": picking.id,
                "user_id": self.env.user.id,
            })
            issue._update_snapshot_after_transfer(quantity)

            new_resolved = issue.resolved_qty + quantity
            remaining = max(issue.found_qty - new_resolved, 0.0)
            resolved = float_is_zero(
                remaining,
                precision_rounding=issue.product_id.uom_id.rounding,
            )
            issue.write({
                "resolved_qty": new_resolved,
                "state": "resolved" if resolved else "partial",
                "last_picking_id": picking.id,
                "source_location_id": False,
                "quantity_to_move": remaining,
            })

            issue.count_id._refresh_persistent_kpis()
            issue.count_id.message_post(
                body=_(
                    "Corrección de ubicación: %(qty)s %(product)s%(lot)s movidos "
                    "de %(source)s a %(destination)s mediante %(picking)s."
                ) % {
                    "qty": quantity,
                    "product": issue.product_id.display_name,
                    "lot": (
                        " · lote %s" % issue.lot_id.name
                        if issue.lot_id else ""
                    ),
                    "source": source.display_name,
                    "destination": issue.found_location_id.display_name,
                    "picking": picking.display_name,
                }
            )
        return True


class InventoryCountRelocationLine(models.Model):
    _name = "setu.inventory.count.relocation.line"
    _description = "Traslado interno originado por conteo"
    _order = "id desc"

    issue_id = fields.Many2one(
        "setu.inventory.count.relocation.issue",
        required=True,
        ondelete="cascade",
        index=True,
    )
    source_location_id = fields.Many2one(
        "stock.location",
        required=True,
        readonly=True,
        string="Origen",
    )
    destination_location_id = fields.Many2one(
        "stock.location",
        related="issue_id.found_location_id",
        store=True,
        readonly=True,
        string="Destino",
    )
    quantity = fields.Float(
        readonly=True,
        digits="Product Unit of Measure",
        string="Cantidad",
    )
    picking_id = fields.Many2one(
        "stock.picking",
        readonly=True,
        string="Traslado",
    )
    user_id = fields.Many2one(
        "res.users",
        readonly=True,
        string="Resuelto por",
    )
    date = fields.Datetime(
        default=fields.Datetime.now,
        readonly=True,
        string="Fecha",
    )


class InventoryCountSnapshotLocationExtension(models.Model):
    _inherit = "setu.inventory.count.snapshot.line"

    relocation_resolved_qty = fields.Float(
        string="Cantidad resuelta por traslado interno",
        default=0.0,
        readonly=True,
        digits="Product Unit of Measure",
    )
    relocation_resolved = fields.Boolean(
        string="Resuelto por traslado interno",
        default=False,
        readonly=True,
    )


class InventoryCountLocationFlow(models.Model):
    _inherit = "setu.stock.inventory.count"

    location_progress_ids = fields.One2many(
        "setu.inventory.count.location.progress",
        "count_id",
        string="Estado de ubicaciones",
        readonly=True,
    )
    relocation_issue_ids = fields.One2many(
        "setu.inventory.count.relocation.issue",
        "count_id",
        string="Productos encontrados en otra ubicación",
    )
    pending_relocation_count = fields.Integer(
        compute="_compute_location_flow_metrics",
        string="Ubicaciones por corregir",
    )
    location_not_started_count = fields.Integer(
        compute="_compute_location_flow_metrics",
        string="Ubicaciones sin contar",
    )
    location_in_progress_count = fields.Integer(
        compute="_compute_location_flow_metrics",
        string="Ubicaciones en proceso",
    )
    location_done_count = fields.Integer(
        compute="_compute_location_flow_metrics",
        string="Ubicaciones finalizadas",
    )

    def _compute_location_flow_metrics(self):
        for count in self:
            count._ensure_location_progress_records()
            progress = count.location_progress_ids
            count.pending_relocation_count = len(
                count.relocation_issue_ids.filtered(
                    lambda issue: issue.state != "resolved"
                )
            )
            count.location_not_started_count = len(
                progress.filtered(lambda line: line.state == "not_started")
            )
            count.location_in_progress_count = len(
                progress.filtered(lambda line: line.state == "in_progress")
            )
            count.location_done_count = len(
                progress.filtered(lambda line: line.state == "done")
            )

    def _ensure_location_progress_records(self):
        Progress = self.env["setu.inventory.count.location.progress"].sudo()
        for count in self:
            if not count.location_id:
                continue
            locations = count._snapshot_scope_locations()
            existing = Progress.search([
                ("count_id", "=", count.id),
            ])
            missing = locations - existing.mapped("location_id")
            if missing:
                Progress.create([
                    {
                        "count_id": count.id,
                        "location_id": location.id,
                    }
                    for location in missing
                ])
        return True

    def _location_progress(self, location, create=True):
        self.ensure_one()
        Progress = self.env["setu.inventory.count.location.progress"].sudo()
        progress = Progress.search([
            ("count_id", "=", self.id),
            ("location_id", "=", location.id),
        ], limit=1)
        if not progress and create:
            progress = Progress.create({
                "count_id": self.id,
                "location_id": location.id,
            })
        return progress

    def _sync_relocation_issues(self):
        Issue = self.env["setu.inventory.count.relocation.issue"].sudo()
        Quant = self.env["stock.quant"].sudo()
        for count in self:
            unexpected = count.snapshot_line_ids.filtered(
                lambda line: (
                    line.status == "unexpected"
                    and line.counted_qty > 0
                    and not line.relocation_resolved
                )
            )
            for snapshot in unexpected:
                domain = [
                    ("product_id", "=", snapshot.product_id.id),
                    ("location_id", "child_of", count.location_id.id),
                    ("location_id.usage", "=", "internal"),
                    ("location_id", "!=", snapshot.location_id.id),
                    ("quantity", ">", 0),
                ]
                if snapshot.product_id.tracking != "none":
                    domain.append(
                        ("lot_id", "=", snapshot.lot_id.id if snapshot.lot_id else False)
                    )
                if not Quant.search_count(domain):
                    continue
                issue = Issue.search([
                    ("snapshot_line_id", "=", snapshot.id),
                ], limit=1)
                if not issue:
                    Issue.create({
                        "count_id": count.id,
                        "snapshot_line_id": snapshot.id,
                        "quantity_to_move": snapshot.counted_qty,
                    })
        return True

    def approve_inventory_count(self):
        for count in self:
            count._sync_relocation_issues()
            pending = count.relocation_issue_ids.filtered(
                lambda issue: issue.state != "resolved"
            )
            if pending:
                raise ValidationError(_(
                    "Hay %s producto(s)/lote(s) encontrados físicamente en una "
                    "ubicación distinta a la registrada en Odoo. Resuelva primero "
                    "la pestaña «Ubicaciones» antes de aprobar el conteo."
                ) % len(pending))
        return super().approve_inventory_count()


class InventoryCountSessionLocationFlow(models.Model):
    _inherit = "setu.inventory.count.session"

    def _activate_scanned_location(self, location):
        result = super()._activate_scanned_location(location)
        for session in self:
            progress = session.inventory_count_id._location_progress(
                location, create=True
            )
            progress._mark_started(self.env.user)
        return result

    def _touch_current_location_progress(self):
        for session in self:
            if session.current_scanning_location_id:
                progress = session.inventory_count_id._location_progress(
                    session.current_scanning_location_id,
                    create=True,
                )
                progress._mark_started(self.env.user)
        return True
