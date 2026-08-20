from collections import defaultdict


class ReplanningEngine:
    """Deterministic resequencing pass that preserves dependencies and priorities."""

    def __init__(self, plan):
        self.plan = plan

    def run(self):
        operations = self.plan.operation_ids.filtered(
            lambda row: row.state != "cancelled"
        )
        by_workcenter = defaultdict(list)
        for operation in operations:
            by_workcenter[operation.workcenter_id].append(operation)
        for workcenter, rows in by_workcenter.items():
            ordered = sorted(
                rows,
                key=lambda row: (
                    -int(row.production_proposal_id.priority or 0),
                    row.date_end or "",
                    row.id,
                ),
            )
            cursor = None
            for sequence, operation in enumerate(ordered, 1):
                if cursor and operation.date_start < cursor:
                    duration = operation.load_hours
                    operation.write(
                        {
                            "date_start": cursor,
                            "date_end": cursor + self._hours(duration),
                        }
                    )
                operation.sequence = sequence
                cursor = operation.date_end
        return operations

    @staticmethod
    def _hours(hours):
        from datetime import timedelta

        return timedelta(hours=hours or 0.0)
