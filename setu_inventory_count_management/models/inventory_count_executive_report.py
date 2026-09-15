# -*- coding: utf-8 -*-
from collections import defaultdict
import base64
import io

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

    def action_export_final_xlsx(self):
        """Exporta el cierre auditable en Excel con las 4 secciones definitivas."""
        self.ensure_one()
        if self.state not in ("Approved", "Inventory Adjusted"):
            raise ValidationError(
                _("El Excel final solo está disponible cuando el conteo ya está cerrado.")
            )

        try:
            import xlsxwriter
        except ImportError as exc:
            raise ValidationError(
                _("El servidor no tiene disponible la librería xlsxwriter.")
            ) from exc

        data = self._get_executive_report_data()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        title = workbook.add_format({"bold": True, "font_size": 14})
        section = workbook.add_format({"bold": True, "font_size": 12, "bottom": 1})
        header = workbook.add_format({"bold": True, "border": 1})
        cell = workbook.add_format({"border": 1})
        qty = workbook.add_format({"border": 1, "num_format": "#,##0.00"})
        money = workbook.add_format({"border": 1, "num_format": '#,##0.00'})
        percent = workbook.add_format({"border": 1, "num_format": "0.00%"})

        ws = workbook.add_worksheet("Cierre de inventario")
        ws.freeze_panes(4, 0)
        ws.set_column("A:A", 20)
        ws.set_column("B:B", 42)
        ws.set_column("C:D", 22)
        ws.set_column("E:H", 16)
        ws.set_column("I:L", 28)

        row = 0
        ws.write(row, 0, "CIERRE DEFINITIVO DE CONTEO DE INVENTARIO", title)
        row += 2

        # 1. Resumen ejecutivo
        ws.write(row, 0, "1. RESUMEN EJECUTIVO", section); row += 1
        summary = [
            ("Conteo", self.display_name),
            ("Almacén", self.warehouse_id.display_name),
            ("Fecha", str(self.inventory_count_date or "")),
            ("Estado", data["final_status_label"]),
            ("Sesiones", data["session_count"]),
            ("Participantes", ", ".join(data["participants"].mapped("display_name"))),
            ("Posiciones esperadas", data["expected_positions"]),
            ("Posiciones procesadas", data["counted_positions"]),
            ("Avance %", data["progress"] / 100.0),
            ("Efectividad %", data["resolution_rate"] / 100.0),
            ("Reconteos", data["recount_count"]),
            ("Ajuste", data["adjustment"].display_name if data["adjustment"] else "No requerido"),
            ("Impacto neto", self.net_adjustment_value),
        ]
        for label, value in summary:
            ws.write(row, 0, label, header)
            fmt = percent if label.endswith("%") else (money if label == "Impacto neto" else cell)
            ws.write(row, 1, value, fmt)
            row += 1
        row += 2

        # 2. Sin novedad
        ws.write(row, 0, "2. PRODUCTOS SIN NOVEDAD", section); row += 1
        cols = ["Ubicación", "Producto", "Código", "Lote/Serie", "Sistema", "Físico", "Diferencia", "Usuario"]
        for c, label in enumerate(cols): ws.write(row, c, label, header)
        row += 1
        for item in data["location_detail_rows"]:
            if abs(item["difference_qty"]) > 0.000001 or item["status"] not in ("Coincide", "Matched", "matched"):
                continue
            values = [item["location"], item["product"], item["code"], item["lot"],
                      item["expected_qty"], item["counted_qty"], item["difference_qty"], item["user"]]
            for c, value in enumerate(values):
                ws.write(row, c, value, qty if c in (4,5,6) else cell)
            row += 1
        row += 2

        # 3. Novedades / observaciones / reconteos
        ws.write(row, 0, "3. PRODUCTOS CON NOVEDAD, OBSERVACIONES Y RECONTEOS", section); row += 1
        cols = ["Ubicación", "Producto", "Lote/Serie", "Sistema", "Físico final", "Diferencia",
                "Estado", "Decisión", "Observación", "Última sesión", "Último usuario"]
        for c, label in enumerate(cols): ws.write(row, c, label, header)
        row += 1
        for item in data["novelty_rows"]:
            values = [
                item["location"], item["product"], item["lot"], item["expected_qty"],
                item["counted_qty"], item["difference_qty"], item["status"],
                item["decision"], item["observation"], item["session"], item["user"],
            ]
            for c, value in enumerate(values):
                ws.write(row, c, value, qty if c in (3,4,5) else cell)
            row += 1
        row += 2

        # 4. Movimientos y contabilidad
        ws.write(row, 0, "4. MOVIMIENTOS DE STOCK Y CONTABILIDAD", section); row += 1
        cols = ["Tipo", "Documento", "Producto/Referencia", "Origen", "Destino",
                "Cantidad", "Estado", "Asiento", "Diario", "Fecha"]
        for c, label in enumerate(cols): ws.write(row, c, label, header)
        row += 1
        for item in data["movement_accounting_rows"]:
            values = [item[k] for k in ("type", "document", "reference", "source", "destination",
                                        "quantity", "state", "account_move", "journal", "date")]
            for c, value in enumerate(values):
                ws.write(row, c, value, qty if c == 5 else cell)
            row += 1

        workbook.close()
        content = base64.b64encode(output.getvalue())
        filename = "Cierre_%s.xlsx" % (self.name or str(self.id)).replace("/", "_")
        attachment = self.env["ir.attachment"].create({
            "name": filename,
            "type": "binary",
            "datas": content,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "res_model": self._name,
            "res_id": self.id,
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

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

        novelty_rows = []
        decision_selection = dict(
            self.env["setu.inventory.count.snapshot.line"]._fields[
                "review_decision"
            ]._description_selection(self.env)
        )
        for line in lines.sorted("id"):
            if (
                not line.review_required
                and not line.has_observation
                and float_is_zero(line.difference_qty, precision_rounding=0.000001)
                and not line.unexpected
                and not line.duplicate
            ):
                continue
            novelty_rows.append({
                "location": line.location_id.display_name,
                "product": line.product_id.display_name,
                "lot": line.lot_id.name if line.lot_id else "",
                "expected_qty": line.expected_qty,
                "counted_qty": line.counted_qty,
                "difference_qty": line.difference_qty,
                "status": dict(
                    line._fields["status"]._description_selection(self.env)
                ).get(line.status, line.status),
                "decision": decision_selection.get(line.review_decision, line.review_decision or ""),
                "observation": line.observation_note or "",
                "session": line.last_session_id.display_name if line.last_session_id else "",
                "user": line.last_user_id.display_name if line.last_user_id else "",
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

        movement_accounting_rows = []
        # Traslados de reubicación ya resueltos.
        for row in relocation_rows:
            movement_accounting_rows.append({
                "type": _("Traslado interno"),
                "document": row["picking"],
                "reference": "%s%s" % (
                    row["product"],
                    (" · " + row["lot"]) if row["lot"] else "",
                ),
                "source": row["source"],
                "destination": row["destination"],
                "quantity": row["quantity"],
                "state": _("Realizado"),
                "account_move": "",
                "journal": "",
                "date": str(row["date"] or ""),
            })

        # Movimientos y asientos generados por el ajuste definitivo.
        for inventory in self.inventory_adj_ids.filtered(lambda adj: adj.state != "cancel"):
            for move in inventory.move_ids:
                account_move = (
                    move.account_move_id
                    if "account_move_id" in move._fields
                    else self.env["account.move"]
                )
                movement_accounting_rows.append({
                    "type": _("Ajuste de inventario"),
                    "document": inventory.display_name,
                    "reference": move.product_id.display_name,
                    "source": move.location_id.display_name,
                    "destination": move.location_dest_id.display_name,
                    "quantity": move.product_uom_qty,
                    "state": move.state,
                    "account_move": account_move.display_name if account_move else "",
                    "journal": account_move.journal_id.display_name if account_move else "",
                    "date": str(account_move.date or "") if account_move else "",
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
            "novelty_rows": novelty_rows,
            "relocation_rows": relocation_rows,
            "movement_accounting_rows": movement_accounting_rows,
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
