class StockProjectionEngine:
    """Legacy compatibility engine.

    The active planner uses SimplePlanningEngine. If this engine is invoked by
    legacy code, it also uses Odoo's forecast instead of manual quant arithmetic.
    """

    def __init__(self, plan):
        self.plan = plan

    def run(self):
        lines = self.plan.line_ids.filtered(lambda line: line.product_id)
        warehouses = self.plan.warehouse_ids or self.plan.warehouse_id
        if not lines or not warehouses:
            return True

        for line in lines:
            forecasts = []
            for warehouse in warehouses:
                values = line.product_id.with_context(
                    warehouse_id=warehouse.id,
                    to_date=self.plan.date_end,
                    allowed_company_ids=[self.plan.company_id.id],
                    company_owned=True,
                    prefetch_fields=False,
                ).read(['incoming_qty', 'outgoing_qty', 'virtual_available'])[0]
                forecasts.append(values)

            forecast_qty = sum(row.get('virtual_available') or 0.0 for row in forecasts)
            incoming_qty = sum(row.get('incoming_qty') or 0.0 for row in forecasts)
            outgoing_qty = sum(row.get('outgoing_qty') or 0.0 for row in forecasts)
            line.write({
                'stock_qty': forecast_qty,
                'incoming_qty': incoming_qty,
                'outgoing_qty': outgoing_qty,
                'net_requirement_qty': max(-forecast_qty, 0.0),
                'state': 'blocked' if forecast_qty < 0 else 'planned',
            })
        return True
