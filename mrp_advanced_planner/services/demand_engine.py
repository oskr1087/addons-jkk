from collections import defaultdict

from odoo import fields


class DemandEngine:
    """Extracts open confirmed sales demand into an isolated planning run."""

    def __init__(self, plan):
        self.plan = plan

    def run(self):
        Demand = self.plan.env["mrp.planning.demand"]
        Line = self.plan.env["mrp.planning.plan.line"]
        Demand.search([("plan_id", "=", self.plan.id)]).unlink()
        Line.search(
            [("plan_id", "=", self.plan.id), ("source_type", "=", "sale")]
        ).unlink()
        domain = [
            ("order_id.state", "in", ("sale", "done")),
            ("order_id.company_id", "=", self.plan.company_id.id),
            ("product_id", "!=", False),
            ("product_uom_qty", ">", 0),
        ]
        sale_lines = self.plan.env["sale.order.line"].search(domain)
        grouped = defaultdict(lambda: {"qty": 0.0, "sources": []})
        for sale_line in sale_lines:
            if (
                sale_line.order_id.warehouse_id
                and sale_line.order_id.warehouse_id != self.plan.warehouse_id
            ):
                continue
            remaining = max(sale_line.product_uom_qty - sale_line.qty_delivered, 0.0)
            if not remaining:
                continue
            date_required = (
                sale_line.order_id.commitment_date
                or sale_line.order_id.expected_date
                or self.plan.date_end
            )
            if (
                date_required < self.plan.date_start
                or date_required > self.plan.date_end
            ):
                continue
            quantity = sale_line.product_uom_id._compute_quantity(
                remaining, sale_line.product_id.uom_id
            )
            date_key = fields.Datetime.to_string(date_required)
            grouped[(sale_line.product_id.id, date_key)]["qty"] += quantity
            grouped[(sale_line.product_id.id, date_key)]["sources"].append(sale_line)
            Demand.create(
                {
                    "plan_id": self.plan.id,
                    "sale_line_id": sale_line.id,
                    "product_id": sale_line.product_id.id,
                    "date_required": date_required,
                    "quantity": quantity,
                    "delivered_qty": 0.0,
                    "priority": sale_line.order_id.priority or self.plan.priority,
                    "source_reference": "%s / %s"
                    % (sale_line.order_id.name, sale_line.name),
                }
            )
        for (product_id, date_key), values in grouped.items():
            product = self.plan.env["product.product"].browse(product_id)
            line = Line.search(
                [
                    ("plan_id", "=", self.plan.id),
                    ("product_id", "=", product_id),
                    ("date_required", "=", date_key),
                ],
                limit=1,
            )
            vals = {
                "plan_id": self.plan.id,
                "product_id": product.id,
                "demand_qty": values["qty"],
                "sales_qty": values["qty"],
                "date_required": date_key,
                "source_type": "sale",
                "source_reference": ", ".join(
                    sorted(set(s.order_id.name for s in values["sources"]))
                ),
                "state": "draft",
            }
            line.write(vals) if line else Line.create(vals)
        return len(grouped)
