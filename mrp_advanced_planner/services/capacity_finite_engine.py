from collections import defaultdict
from datetime import timedelta

from odoo import fields


class CapacityFiniteEngine:
    def __init__(self, plan):
        self.plan = plan
        self.env = plan.env

    def run(self):
        operations = self.plan.operation_ids.filtered(
            lambda operation: operation.state != "cancelled"
        )
        self.plan.load_ids.unlink()
        self.plan.conflict_ids.filtered(
            lambda conflict: conflict.conflict_type
            in ("capacity_shortage", "calendar_conflict")
        ).unlink()
        grouped = defaultdict(list)
        for operation in operations:
            grouped[operation.workcenter_id.id].append(operation)
        loads = []
        for workcenter_id, workcenter_operations in grouped.items():
            workcenter = self.env["mrp.workcenter"].browse(workcenter_id)
            for operation in workcenter_operations:
                available = self._available_hours(
                    workcenter, operation.date_start, operation.date_end
                )
                load = self.env["mrp.planning.workcenter.load"].create(
                    {
                        "plan_id": self.plan.id,
                        "workcenter_id": workcenter.id,
                        "date_start": operation.date_start,
                        "date_end": operation.date_end,
                        "available_hours": available,
                        "load_hours": operation.load_hours,
                    }
                )
                loads.append(load)
                if (
                    not operation.date_start
                    or not operation.date_end
                    or available < operation.load_hours
                ):
                    operation.action_mark_conflict()
                    conflict_type = (
                        "calendar_conflict"
                        if not operation.date_start
                        or not operation.date_end
                        or available <= 0
                        else "capacity_shortage"
                    )
                    self.env["mrp.planning.conflict"].create(
                        {
                            "plan_id": self.plan.id,
                            "conflict_type": conflict_type,
                            "severity": "error",
                            "workcenter_id": workcenter.id,
                            "operation_id": operation.id,
                            "message": "Operation has insufficient workcenter capacity or no valid calendar interval.",
                        }
                    )
        return loads

    def _available_hours(self, workcenter, start, end):
        if not start or not end:
            return 0.0
        calendar = workcenter.resource_calendar_id
        if not calendar:
            return 0.0
        start_dt = fields.Datetime.to_datetime(start)
        end_dt = fields.Datetime.to_datetime(end)
        try:
            data = calendar.get_work_duration_data(
                start_dt, end_dt, compute_leaves=True
            )
            return data.get("hours", 0.0)
        except (AttributeError, TypeError):
            return 0.0
