# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import _, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_is_zero


class StockInventoryCountExecutiveReport(models.Model):
    _inherit = "setu.stock.inventory.count"

    def action_print_executive_report(self):
        self.ensure_one()
        if self.state not in ("Approved", "Inventory Adjusted"):
            raise ValidationError(
                _("El informe ejecutivo solo está disponible cuando el conteo ya está cerrado.")
            )
        return self.env.ref(
            "setu_inventory_count_management.action_report_inventory_count_executive"
        ).report_action(self)

    def _executive_money(self, amount):
        self.ensure_one()
        currency = self.company_id.currency_id
        symbol = currency.symbol or ""
        amount = amount or 0.0
        if currency.position == "after":
            return "%s %s" % (f"{amount:,.2f}", symbol)
        return "%s %s" % (symbol, f"{amount:,.2f}")

    def _get_executive_report_data(self):
        self.ensure_one()

        if self.state not in ("Approved", "Inventory Adjusted"):
            raise ValidationError(
                _("El informe ejecutivo solo está disponible cuando el conteo ya está cerrado.")
            )

        self._refresh_persistent_kpis()
        header = self._get_snapshot_header(create=False)
        lines = header.line_ids if header else self.snapshot_line_ids

        grouped = defaultdict(lambda: {
            "product": False,
            "expected_qty": 0.0,
            "counted_qty": 0.0,
            "difference_qty": 0.0,
            "expected_value": 0.0,
            "counted_value": 0.0,
            "impact_value": 0.0,
            "lots": set(),
            "locations": set(),
            "unexpected": False,
            "duplicate": False,
            "positions": 0,
        })

        for line in lines:
            item = grouped[line.product_id.id]
            item["product"] = line.product_id
            item["expected_qty"] += line.expected_qty
            item["counted_qty"] += line.counted_qty
            item["difference_qty"] += line.difference_qty
            item["expected_value"] += line.expected_value
            item["counted_value"] += line.counted_value
            item["impact_value"] += line.impact_value
            item["positions"] += 1
            if line.lot_id:
                item["lots"].add(line.lot_id.id)
            if line.location_id:
                item["locations"].add(line.location_id.id)
            item["unexpected"] = item["unexpected"] or bool(line.unexpected)
            item["duplicate"] = item["duplicate"] or bool(line.duplicate)

        product_rows = []
        rounding = self.company_id.currency_id.rounding or 0.01

        for item in grouped.values():
            product = item["product"]
            difference = item["difference_qty"]
            impact = item["impact_value"]

            if item["duplicate"]:
                result = _("Revisado")
                result_class = "warning"
            elif item["unexpected"] and float_is_zero(item["expected_qty"], precision_rounding=0.000001):
                result = _("No previsto")
                result_class = "warning"
            elif float_is_zero(difference, precision_rounding=0.000001):
                result = _("Correcto")
                result_class = "success"
            elif difference < 0:
                result = _("Faltante")
                result_class = "danger"
            else:
                result = _("Sobrante")
                result_class = "success"

            product_rows.append({
                **item,
                "code": product.default_code or "",
                "name": product.display_name,
                "lots_count": len(item["lots"]),
                "locations_count": len(item["locations"]),
                "result": result,
                "result_class": result_class,
                "expected_value_fmt": self._executive_money(item["expected_value"]),
                "impact_value_fmt": self._executive_money(impact),
                "abs_impact": abs(impact),
            })

        product_rows.sort(
            key=lambda row: (-row["abs_impact"], row["name"].lower())
        )

        shortages = [
            row for row in product_rows
            if row["impact_value"] < -rounding
        ][:10]
        surpluses = [
            row for row in product_rows
            if row["impact_value"] > rounding
        ][:10]

        self._ensure_location_progress_records()
        location_rows = []
        for progress in self.location_progress_ids.sorted(
            key=lambda item: item.location_id.complete_name or item.location_id.display_name
        ):
            location_rows.append({
                "location": progress.location_id,
                "state": progress.state,
                "state_label": dict(
                    progress._fields["state"]._description_selection(self.env)
                ).get(progress.state, progress.state),
                "expected": progress.expected_position_count,
                "scanned": progress.scanned_position_count,
                "pending": progress.pending_position_count,
                "differences": progress.difference_position_count,
                "progress_fmt": "{:.1f}%".format(progress.progress_percent or 0.0),
                "participants": ", ".join(
                    progress.participant_user_ids.mapped("display_name")
                ) or "-",
                "started_at": progress.started_at,
                "last_scan_at": progress.last_scan_at,
                "finished_at": progress.finished_at,
            })

        location_detail_rows = []
        for line in lines.sorted(
            key=lambda item: (
                item.location_id.complete_name or item.location_id.display_name or "",
                item.product_id.display_name or "",
                item.lot_id.name if item.lot_id else "",
            )
        ):
            location_detail_rows.append({
                "location": line.location_id.display_name,
                "product": line.product_id.display_name,
                "code": line.product_id.default_code or "",
                "lot": line.lot_id.name if line.lot_id else "",
                "expected_qty": line.expected_qty,
                "counted_qty": line.counted_qty,
                "difference_qty": line.difference_qty,
                "status": dict(
                    line._fields["status"]._description_selection(self.env)
                ).get(line.status, line.status),
                "user": line.last_user_id.display_name if line.last_user_id else "-",
                "session": line.last_session_id.display_name if line.last_session_id else "-",
                "last_scan_at": line.last_scan_at,
                "relocated": line.relocation_resolved,
            })

        relocation_rows = []
        for issue in self.relocation_issue_ids.filtered(
            lambda rec: rec.state == "resolved"
        ):
            for resolution in issue.resolution_line_ids:
                relocation_rows.append({
                    "product": issue.product_id.display_name,
                    "lot": issue.lot_id.name if issue.lot_id else "",
                    "source": resolution.source_location_id.display_name,
                    "destination": resolution.destination_location_id.display_name,
                    "quantity": resolution.quantity,
                    "picking": resolution.picking_id.display_name,
                    "user": resolution.user_id.display_name,
                    "date": resolution.date,
                })

        active_sessions = self.session_ids.filtered(lambda s: s.state != "Cancel")
        participant_users = active_sessions.mapped("user_ids")
        recounts = self.count_ids.sorted("id")

        adjustment = self.inventory_adj_ids.filtered(
            lambda adj: adj.state != "cancel"
        )[:1]


        expected_positions = self.expected_item_count
        counted_positions = self.counted_item_count
        matched = self.matched_item_count
        divergences = self.difference_item_count

        has_adjustment = bool(adjustment)
        final_status_label = (
            _("Inventario ajustado")
            if self.state == "Inventory Adjusted"
            else _("Conteo aprobado")
        )
        if self.state == "Inventory Adjusted":
            final_result_label = _("Diferencias aceptadas y ajustadas")
        elif divergences:
            final_result_label = _("Cerrado sin ajuste")
        else:
            final_result_label = _("Sin diferencias · ajuste no requerido")
        resolution_rate = (
            matched * 100.0 / counted_positions
            if counted_positions else 0.0
        )

        return {
            "count": self,
            "header": header,
            "product_rows": product_rows,
            "location_rows": location_rows,
            "location_detail_rows": location_detail_rows,
            "relocation_rows": relocation_rows,
            "shortages": shortages,
            "surpluses": surpluses,
            "product_count": len(product_rows),
            "expected_positions": expected_positions,
            "counted_positions": counted_positions,
            "matched": matched,
            "divergences": divergences,
            "zero_count": self.zero_item_count,
            "unexpected_count": self.unexpected_item_count,
            "duplicate_count": self.duplicate_item_count,
            "progress": self.progress_percent,
            "resolution_rate": resolution_rate,
            "expected_value_fmt": self._executive_money(self.expected_value),
            "counted_value_fmt": self._executive_money(self.counted_value),
            "shortage_value_fmt": self._executive_money(self.shortage_value),
            "surplus_value_fmt": self._executive_money(self.surplus_value),
            "net_adjustment_value_fmt": self._executive_money(self.net_adjustment_value),
            "session_count": len(active_sessions),
            "participants": participant_users,
            "recounts": recounts,
            "recount_count": len(recounts),
            "adjustment": adjustment,
            "final_status_label": final_status_label,
            "final_result_label": final_result_label,
            "has_adjustment": has_adjustment,
            "issued_at": fields.Datetime.now(),
            "issued_at_fmt": fields.Datetime.context_timestamp(
                self, fields.Datetime.now()
            ).strftime("%d/%m/%Y %H:%M"),
            "progress_fmt": "{:.2f}%".format(self.progress_percent or 0.0),
            "resolution_rate_fmt": "{:.1f}%".format(resolution_rate or 0.0),
            "currency": self.company_id.currency_id,
        }
