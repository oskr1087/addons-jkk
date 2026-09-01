from datetime import timedelta

from odoo import fields


class CalendarSchedulingEngine:
    def __init__(self, plan):
        self.plan = plan
        self.env = plan.env

    def run(self):
        operations = self.plan.operation_ids.sorted(key=lambda op: (op.workcenter_id.id, op.sequence, op.date_end or fields.Datetime.now()))
        for operation in operations:
            if not operation.date_end:
                continue
            duration = operation.duration + operation.setup_duration
            start = self._subtract_work_hours(operation.workcenter_id, operation.date_end, duration)
            if start:
                operation.date_start = start
        return operations

    def _subtract_work_hours(self, workcenter, end, hours):
        calendar = workcenter.resource_calendar_id
        if not calendar:
            return False
        end_dt = fields.Datetime.to_datetime(end)
        candidate = end_dt - timedelta(hours=max(hours, 0.0))
        try:
            return calendar.plan_hours(-hours, end_dt, compute_leaves=True)
        except (AttributeError, TypeError):
            return candidate
