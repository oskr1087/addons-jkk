# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import _, fields, models
from odoo.exceptions import AccessError
from odoo.tools.float_utils import float_is_zero


class StockInventoryCountBackendDashboard(models.Model):
    _inherit = "setu.stock.inventory.count"

    def _check_backend_dashboard_access(self):
        if not self.env.user.has_group(
            "setu_inventory_count_management.group_setu_inventory_count_manager"
        ):
            raise AccessError(_("No tiene permisos para consultar el panel administrativo del conteo."))

    def action_open_backend_dashboard(self):
        self.ensure_one()
        self._check_backend_dashboard_access()
        return {
            "type": "ir.actions.client",
            "tag": "setu_inventory_count_management.count_backend_dashboard",
            "name": _("Panel del conteo"),
            "params": {"count_id": self.id},
        }

    def _dashboard_scope_locations(self):
        self.ensure_one()
        if not self.location_id:
            return self.env["stock.location"]
        return self.env["stock.location"].sudo().search([
            ("id", "child_of", self.location_id.id),
            ("usage", "=", "internal"),
            ("company_id", "in", [False, self.company_id.id]),
        ])

    def _dashboard_expected_stock(self):
        """Expected physical stock by Product + Lot + Location.

        This is intentionally evaluated only when the manager opens/refreshes the
        dashboard. It never preloads count/session lines.
        """
        self.ensure_one()
        locations = self._dashboard_scope_locations()
        if not locations:
            return {}

        quants = self.env["stock.quant"].sudo().search([
            ("location_id", "in", locations.ids),
            ("quantity", "!=", 0),
            ("product_id.active", "=", True),
        ])

        result = defaultdict(float)
        for quant in quants:
            key = (
                quant.product_id.id,
                quant.lot_id.id or False,
                quant.location_id.id,
            )
            result[key] += quant.quantity
        return {
            key: quantity
            for key, quantity in result.items()
            if not float_is_zero(
                quantity,
                precision_rounding=self.env["product.product"].browse(key[0]).uom_id.rounding,
            )
        }

    def _dashboard_scanned_stock(self):
        self.ensure_one()
        sessions = self.session_ids.filtered(lambda session: session.state != "Cancel")
        lines = sessions.mapped("session_line_ids").filtered(
            lambda line: line.product_id and line.location_id and line.product_scanned
        )
        result = defaultdict(float)
        lines_by_key = defaultdict(lambda: self.env["setu.inventory.count.session.line"])
        for line in lines:
            key = (
                line.product_id.id,
                line.lot_id.id or False,
                line.location_id.id,
            )
            result[key] += line.scanned_qty
            lines_by_key[key] |= line
        return dict(result), dict(lines_by_key)

    def _dashboard_row(self, key, theoretical, counted, lines=False, duplicate=False):
        product_id, lot_id, location_id = key
        product = self.env["product.product"].browse(product_id)
        lot = self.env["stock.lot"].browse(lot_id) if lot_id else self.env["stock.lot"]
        location = self.env["stock.location"].browse(location_id)
        difference = counted - theoretical
        is_difference = not float_is_zero(
            difference,
            precision_rounding=product.uom_id.rounding,
        )
        return {
            "key": "%s:%s:%s" % (product_id, lot_id or 0, location_id),
            "product_id": product_id,
            "product": product.display_name,
            "default_code": product.default_code or "",
            "barcode": product.barcode or "",
            "lot_id": lot.id or False,
            "lot": lot.name or "",
            "location_id": location_id,
            "location": location.display_name,
            "uom": product.uom_id.display_name,
            "theoretical": theoretical,
            "counted": counted,
            "difference": difference,
            "has_difference": is_difference,
            "duplicate": bool(duplicate),
            "session_line_ids": lines.ids if lines else [],
        }

    def _snapshot_dashboard_row(self, snapshot):
        return {
            "key": str(snapshot.id),
            "snapshot_id": snapshot.id,
            "product_id": snapshot.product_id.id,
            "product": snapshot.product_id.display_name,
            "default_code": snapshot.product_id.default_code or "",
            "barcode": snapshot.product_id.barcode or "",
            "lot_id": snapshot.lot_id.id or False,
            "lot": snapshot.lot_id.name or "",
            "location_id": snapshot.location_id.id,
            "location": snapshot.location_id.display_name,
            "uom": snapshot.uom_id.display_name,
            "theoretical": snapshot.expected_qty,
            "counted": snapshot.counted_qty,
            "difference": snapshot.difference_qty,
            "has_difference": snapshot.status in (
                "difference", "zero", "unexpected", "duplicate"
            ),
            "duplicate": snapshot.duplicate,
            "unexpected": snapshot.unexpected,
            "status": snapshot.status,
        }

    def get_backend_dashboard_data(self, pending_page=1, difference_page=1, page_size=25):
        """Lee exclusivamente la fotografía persistente del conteo.

        El panel ya no recorre stock.quant ni recompone todas las lecturas cada
        vez que el administrador entra, cambia de página o regresa de una acción.
        """
        self.ensure_one()
        self._check_backend_dashboard_access()
        if not self.snapshot_ready:
            has_scans = bool(
                self.session_ids.mapped("session_line_ids").filtered(
                    lambda line: line.product_scanned
                )
            )
            if not has_scans:
                self._prepare_inventory_snapshot()

        pending_page = max(int(pending_page or 1), 1)
        difference_page = max(int(difference_page or 1), 1)
        page_size = min(max(int(page_size or 25), 10), 100)
        Snapshot = self.env["setu.inventory.count.snapshot.line"].sudo()
        base_domain = [("count_id", "=", self.id)]
        pending_domain = base_domain + [("status", "=", "pending")]
        difference_domain = base_domain + [
            ("status", "in", ["difference", "zero", "unexpected", "duplicate"])
        ]

        pending_total = self.pending_item_count
        difference_total = self.difference_item_count
        pending_pages = max((pending_total + page_size - 1) // page_size, 1)
        difference_pages = max((difference_total + page_size - 1) // page_size, 1)
        pending_page = min(pending_page, pending_pages)
        difference_page = min(difference_page, difference_pages)
        pending_start = (pending_page - 1) * page_size
        difference_start = (difference_page - 1) * page_size

        pending_lines = Snapshot.search(
            pending_domain,
            order="location_id, product_id, lot_id, id",
            offset=pending_start,
            limit=page_size,
        )
        difference_lines = Snapshot.search(
            difference_domain,
            order="last_scan_at desc, id desc",
            offset=difference_start,
            limit=page_size,
        )

        sessions = self.session_ids.filtered(lambda session: session.state != "Cancel")
        active_sessions = sessions.filtered(
            lambda session: session.state in ("Draft", "In Progress")
        )
        completed_sessions = sessions.filtered(
            lambda session: session.state in ("Submitted", "Done")
        )
        active_users = active_sessions.mapped("user_ids")

        return {
            "count": {
                "id": self.id,
                "name": self.display_name,
                "state": self.state,
                "warehouse": self.warehouse_id.display_name or "",
                "location": self.location_id.display_name or "",
                "controller": self.approver_id.display_name or "",
                "date": fields.Date.to_string(self.inventory_count_date) if self.inventory_count_date else "",
                "snapshot_date": fields.Datetime.to_string(self.snapshot_date) if self.snapshot_date else "",
            },
            "kpis": {
                "expected": self.expected_item_count,
                "counted": self.counted_item_count,
                "pending": self.pending_item_count,
                "progress": round(self.progress_percent, 2),
                "differences": self.difference_item_count,
                "difference_percent": round(self.difference_percent, 2),
                "matched": self.matched_item_count,
                "zero": self.zero_item_count,
                "unexpected": self.unexpected_item_count,
                "duplicates": self.duplicate_item_count,
                "sessions": len(sessions),
                "active_sessions": len(active_sessions),
                "completed_sessions": len(completed_sessions),
                "active_users": len(active_users),
            },
            "pending": [
                self._snapshot_dashboard_row(line) for line in pending_lines
            ],
            "differences": [
                self._snapshot_dashboard_row(line) for line in difference_lines
            ],
            "pagination": {
                "page_size": page_size,
                "pending": {
                    "page": pending_page,
                    "pages": pending_pages,
                    "total": pending_total,
                    "from": pending_start + 1 if pending_total else 0,
                    "to": min(pending_start + page_size, pending_total),
                },
                "differences": {
                    "page": difference_page,
                    "pages": difference_pages,
                    "total": difference_total,
                    "from": difference_start + 1 if difference_total else 0,
                    "to": min(difference_start + page_size, difference_total),
                },
            },
            "last_update": fields.Datetime.to_string(
                self.dashboard_last_update or self.snapshot_date or fields.Datetime.now()
            ),
        }

    def dashboard_open_sessions(self):
        self.ensure_one()
        self._check_backend_dashboard_access()
        action = self.action_open_sessions()
        if isinstance(action, dict):
            action = dict(action)
            action["target"] = "new"
        return action

    def dashboard_create_session(self):
        self.ensure_one()
        self._check_backend_dashboard_access()
        action = self.create_session()
        if isinstance(action, dict):
            action = dict(action)
            action["target"] = "new"
        return action

    def dashboard_complete_counting(self):
        self.ensure_one()
        self._check_backend_dashboard_access()
        self.complete_counting()
        return self.get_backend_dashboard_data()

    def dashboard_open_scanned_lines(self):
        self.ensure_one()
        self._check_backend_dashboard_access()
        return {
            "type": "ir.actions.act_window",
            "name": _("Lecturas del conteo"),
            "res_model": "setu.inventory.count.session.line",
            "views": [(False, "list"), (False, "form")],
            "view_mode": "list,form",
            "domain": [
                ("inventory_count_id", "=", self.id),
                ("product_scanned", "=", True),
            ],
            "context": {"create": False},
            "target": "new",
        }

    def dashboard_open_difference_lines(self):
        self.ensure_one()
        self._check_backend_dashboard_access()
        return {
            "type": "ir.actions.act_window",
            "name": _("Divergencias del conteo"),
            "res_model": "setu.inventory.count.snapshot.line",
            "views": [
                (
                    self.env.ref(
                        "setu_inventory_count_management.setu_inventory_count_snapshot_line_list"
                    ).id,
                    "list",
                )
            ],
            "view_mode": "list",
            "domain": [
                ("count_id", "=", self.id),
                ("status", "in", ["difference", "zero", "unexpected", "duplicate"]),
            ],
            "context": {"create": False},
            "target": "new",
        }

    def dashboard_open_quant(self, product_id, lot_id=False, location_id=False):
        self.ensure_one()
        self._check_backend_dashboard_access()
        domain = [("product_id", "=", product_id)]
        if lot_id:
            domain.append(("lot_id", "=", lot_id))
        else:
            domain.append(("lot_id", "=", False))
        if location_id:
            domain.append(("location_id", "=", location_id))
        return {
            "type": "ir.actions.act_window",
            "name": _("Existencias"),
            "res_model": "stock.quant",
            "views": [(False, "list"), (False, "form")],
            "view_mode": "list,form",
            "domain": domain,
            "context": {
                "create": False,
                "edit": False,
                "delete": False,
            },
            "target": "new",
        }
