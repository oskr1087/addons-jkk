# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


ACTIVE_COUNT_STATES = ("In Progress", "To Be Approved")
RELEASE_COUNT_STATES = ("Approved", "Inventory Adjusted", "Rejected", "Cancel")


class InventoryCountWarehouseLock(models.Model):
    _name = "setu.inventory.count.warehouse.lock"
    _description = "Bloqueo de almacén por conteo"
    _order = "started_at desc, id desc"

    count_id = fields.Many2one(
        "setu.stock.inventory.count",
        string="Conteo",
        required=True,
        ondelete="cascade",
        index=True,
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Almacén",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        related="warehouse_id.company_id",
        store=True,
        index=True,
    )
    started_at = fields.Datetime(
        string="Bloqueado desde",
        required=True,
        default=fields.Datetime.now,
        readonly=True,
    )

    _warehouse_unique = models.Constraint(
        "UNIQUE(warehouse_id)",
        "Ya existe un conteo activo bloqueando este almacén.",
    )
    _count_unique = models.Constraint(
        "UNIQUE(count_id)",
        "Este conteo ya posee un bloqueo de almacén.",
    )


class StockInventoryCountWarehouseLock(models.Model):
    _inherit = "setu.stock.inventory.count"

    warehouse_lock_active = fields.Boolean(
        string="Almacén bloqueado",
        compute="_compute_warehouse_lock_info",
    )
    warehouse_lock_started_at = fields.Datetime(
        string="Almacén bloqueado desde",
        compute="_compute_warehouse_lock_info",
    )
    warehouse_lock_manual_disabled = fields.Boolean(
        string="Bloqueo desactivado por administrador",
        default=False,
        copy=False,
        readonly=True,
        help="Permite al administrador desactivar temporalmente el bloqueo del almacén durante un conteo activo.",
    )

    @api.depends("warehouse_id", "state")
    def _compute_warehouse_lock_info(self):
        locks = self.env["setu.inventory.count.warehouse.lock"].sudo().search([
            ("count_id", "in", self.ids)
        ]) if self.ids else self.env["setu.inventory.count.warehouse.lock"]
        by_count = {lock.count_id.id: lock for lock in locks}
        for count in self:
            lock = by_count.get(count.id)
            count.warehouse_lock_active = bool(lock)
            count.warehouse_lock_started_at = lock.started_at if lock else False

    def _warehouse_lock_record(self):
        self.ensure_one()
        return self.env["setu.inventory.count.warehouse.lock"].sudo().search([
            ("count_id", "=", self.id)
        ], limit=1)

    def _activate_warehouse_lock(self):
        Lock = self.env["setu.inventory.count.warehouse.lock"].sudo()
        for count in self:
            if count.warehouse_lock_manual_disabled and not self.env.context.get("force_warehouse_lock"):
                continue
            if not count.warehouse_id:
                raise ValidationError(
                    _("Debe seleccionar un almacén antes de iniciar el conteo.")
                )

            own_lock = count._warehouse_lock_record()
            if own_lock:
                if own_lock.warehouse_id != count.warehouse_id:
                    raise ValidationError(
                        _("El conteo ya bloquea otro almacén. No puede cambiar el alcance.")
                    )
                continue

            # Serializa activaciones concurrentes para el mismo almacén.
            self.env.cr.execute(
                "SELECT id FROM stock_warehouse WHERE id = %s FOR UPDATE",
                [count.warehouse_id.id],
            )

            other = Lock.search([
                ("warehouse_id", "=", count.warehouse_id.id),
                ("count_id", "!=", count.id),
            ], limit=1)
            if other:
                raise ValidationError(_(
                    "No puede iniciar este conteo porque el almacén %(warehouse)s "
                    "ya está bloqueado por el conteo %(count)s."
                ) % {
                    "warehouse": count.warehouse_id.display_name,
                    "count": other.count_id.display_name,
                })

            Lock.create({
                "count_id": count.id,
                "warehouse_id": count.warehouse_id.id,
                "started_at": fields.Datetime.now(),
            })
        return True

    def _release_warehouse_lock(self):
        locks = self.env["setu.inventory.count.warehouse.lock"].sudo().search([
            ("count_id", "in", self.ids)
        ])
        if locks:
            locks.unlink()
        return True

    def _check_warehouse_lock_admin(self):
        if not self.env.user.has_group(
            "setu_inventory_count_management.group_setu_inventory_count_admin"
        ):
            raise ValidationError(
                _("Solo un administrador de Conteo de Inventarios puede cambiar manualmente el bloqueo del almacén.")
            )

    def action_admin_unlock_warehouse(self):
        self._check_warehouse_lock_admin()
        for count in self:
            if count.state not in ACTIVE_COUNT_STATES:
                raise ValidationError(
                    _("El desbloqueo manual solo aplica a conteos activos o pendientes de aprobación.")
                )
            was_locked = bool(count._warehouse_lock_record())
            count._release_warehouse_lock()
            count.with_context(setu_admin_lock_change=True).write({
                "warehouse_lock_manual_disabled": True,
            })
            if was_locked:
                count.message_post(
                    body=_(
                        "El administrador %(user)s desbloqueó manualmente el almacén %(warehouse)s durante el conteo. "
                        "Los movimientos quedan habilitados hasta reactivar el bloqueo o finalizar el conteo."
                    ) % {
                        "user": self.env.user.display_name,
                        "warehouse": count.warehouse_id.display_name,
                    }
                )
        return True

    def action_admin_lock_warehouse(self):
        self._check_warehouse_lock_admin()
        for count in self:
            if count.state not in ACTIVE_COUNT_STATES:
                raise ValidationError(
                    _("El bloqueo manual solo aplica a conteos activos o pendientes de aprobación.")
                )
            count.with_context(setu_admin_lock_change=True).write({
                "warehouse_lock_manual_disabled": False,
            })
            count.with_context(force_warehouse_lock=True)._activate_warehouse_lock()
            count.message_post(
                body=_(
                    "El administrador %(user)s reactivó manualmente el bloqueo del almacén %(warehouse)s."
                ) % {
                    "user": self.env.user.display_name,
                    "warehouse": count.warehouse_id.display_name,
                }
            )
        return True

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        active = records.filtered(lambda count: count.state in ACTIVE_COUNT_STATES)
        if active:
            active._activate_warehouse_lock()
        return records

    def write(self, vals):
        if "warehouse_lock_manual_disabled" in vals and not self.env.context.get("setu_admin_lock_change"):
            self._check_warehouse_lock_admin()
        if "warehouse_id" in vals:
            locked = self.filtered(lambda count: bool(count._warehouse_lock_record()))
            if locked:
                raise ValidationError(_(
                    "No puede cambiar el almacén mientras el conteo mantenga el "
                    "bloqueo de inventario activo."
                ))

        new_state = vals.get("state")
        if new_state in ACTIVE_COUNT_STATES:
            self._activate_warehouse_lock()

        result = super().write(vals)

        if new_state in RELEASE_COUNT_STATES:
            self._release_warehouse_lock()
            manual_disabled = self.filtered("warehouse_lock_manual_disabled")
            if manual_disabled:
                super(StockInventoryCountWarehouseLock, manual_disabled).write({
                    "warehouse_lock_manual_disabled": False,
                })

        return result

    def unlink(self):
        self._release_warehouse_lock()
        return super().unlink()

    @api.model
    def _backfill_warehouse_count_locks(self):
        """Reconstruye locks de conteos activos al actualizar el módulo."""
        Lock = self.env["setu.inventory.count.warehouse.lock"].sudo()
        active_counts = self.search([
            ("state", "in", list(ACTIVE_COUNT_STATES)),
            ("warehouse_id", "!=", False),
        ], order="inventory_count_date, id")

        for count in active_counts:
            own = Lock.search([("count_id", "=", count.id)], limit=1)
            if own:
                continue

            self.env.cr.execute(
                "SELECT id FROM stock_warehouse WHERE id = %s FOR UPDATE",
                [count.warehouse_id.id],
            )
            other = Lock.search([
                ("warehouse_id", "=", count.warehouse_id.id),
                ("count_id", "!=", count.id),
            ], limit=1)
            if other:
                raise ValidationError(_(
                    "Existen dos conteos activos para el mismo almacén %(warehouse)s: "
                    "%(count1)s y %(count2)s. Finalice uno antes de actualizar el módulo."
                ) % {
                    "warehouse": count.warehouse_id.display_name,
                    "count1": other.count_id.display_name,
                    "count2": count.display_name,
                })

            Lock.create({
                "count_id": count.id,
                "warehouse_id": count.warehouse_id.id,
                "started_at": fields.Datetime.now(),
            })
        return True

    @api.model
    def _get_locked_count_for_locations(self, locations, company=None):
        """Devuelve el conteo que bloquea alguna de las ubicaciones indicadas."""
        locations = locations.exists()
        if not locations:
            return self.env["setu.stock.inventory.count"]

        domain = []
        if company:
            domain.append(("company_id", "=", company.id))
        locks = self.env["setu.inventory.count.warehouse.lock"].sudo().search(domain)
        for lock in locks:
            warehouse = lock.warehouse_id
            root = warehouse.view_location_id
            root_path = root.parent_path or ("%s/" % root.id)
            for location in locations:
                if location == root:
                    return lock.count_id
                if location.warehouse_id == warehouse:
                    return lock.count_id
                path = location.parent_path or ""
                if path.startswith(root_path):
                    return lock.count_id
        return self.env["setu.stock.inventory.count"]

class InventoryCountSessionWarehouseLock(models.Model):
    _inherit = "setu.inventory.count.session"

    def _ensure_running_session_warehouse_lock(self):
        running = self.filtered(
            lambda session: (
                session.state == "In Progress"
                or session.current_state in ("Start", "Resume")
            )
            and session.inventory_count_id
        )
        for session in running:
            count = session.inventory_count_id
            if count.state not in ACTIVE_COUNT_STATES:
                count.write({"state": "In Progress"})
            else:
                count._activate_warehouse_lock()
        return True

    @api.model_create_multi
    def create(self, vals_list):
        sessions = super().create(vals_list)
        sessions._ensure_running_session_warehouse_lock()
        return sessions

    def write(self, vals):
        result = super().write(vals)
        if "state" in vals or "current_state" in vals:
            self._ensure_running_session_warehouse_lock()
        return result

