from collections import defaultdict

from odoo import fields


class ConflictResolutionEngine:
    """Rebuilds derived conflicts after scheduling without changing native MRP data."""

    def __init__(self, plan):
        self.plan = plan
        self.env = plan.env

    def run(self):
        self.plan.conflict_ids.filtered(lambda conflict: conflict.conflict_type in ('capacity_shortage', 'calendar_conflict', 'date_conflict')).unlink()
        self._check_overlaps()
        self._check_dependencies()
        self._check_late_operations()
        return self.plan.conflict_ids

    def _check_overlaps(self):
        by_workcenter = defaultdict(list)
        for operation in self.plan.operation_ids.filtered(lambda item: item.state != 'cancelled' and item.date_start and item.date_end):
            by_workcenter[operation.workcenter_id.id].append(operation)
        for operations in by_workcenter.values():
            ordered = sorted(operations, key=lambda item: (item.date_start, item.date_end))
            for previous, current in zip(ordered, ordered[1:]):
                if current.date_start < previous.date_end:
                    previous.state = current.state = 'conflict'
                    self.env['mrp.planning.conflict'].create({
                        'plan_id': self.plan.id,
                        'conflict_type': 'capacity_shortage',
                        'severity': 'error',
                        'workcenter_id': current.workcenter_id.id,
                        'operation_id': current.id,
                        'message': 'Operations overlap on the same work center.',
                    })

    def _check_dependencies(self):
        for operation in self.plan.operation_ids.filtered(lambda item: item.date_start and item.date_end):
            parent = operation.production_proposal_id
            if not parent:
                continue
            children = self.plan.operation_ids.filtered(lambda item: item.production_proposal_id == parent and item.sequence < operation.sequence)
            if children and max(children.mapped('date_end')) > operation.date_start:
                operation.state = 'conflict'
                self.env['mrp.planning.conflict'].create({
                    'plan_id': self.plan.id,
                    'conflict_type': 'date_conflict',
                    'severity': 'error',
                    'operation_id': operation.id,
                    'message': 'Operation starts before a preceding operation ends.',
                })

    def _check_late_operations(self):
        for operation in self.plan.operation_ids.filtered(lambda item: item.date_end and item.production_proposal_id):
            if operation.production_proposal_id.date_required and operation.date_end > operation.production_proposal_id.date_required:
                self.env['mrp.planning.conflict'].create({
                    'plan_id': self.plan.id,
                    'conflict_type': 'date_conflict',
                    'severity': 'warning',
                    'operation_id': operation.id,
                    'message': 'Operation finishes after the required production date.',
                })
