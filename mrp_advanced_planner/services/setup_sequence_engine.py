from collections import defaultdict


class SetupSequenceEngine:
    """Sequences operations by work center and adds setup time between product changes."""

    def __init__(self, plan):
        self.plan = plan

    def run(self):
        by_workcenter = defaultdict(list)
        for operation in self.plan.operation_ids.filtered(
            lambda item: item.state != "cancelled"
        ):
            by_workcenter[operation.workcenter_id.id].append(operation)
        for operations in by_workcenter.values():
            ordered = sorted(
                operations,
                key=lambda item: (
                    item.date_start or "",
                    -getattr(item.production_proposal_id, "priority", 0),
                    item.sequence,
                    item.id,
                ),
            )
            previous_product = False
            for sequence, operation in enumerate(ordered, 1):
                setup = operation.setup_duration
                if previous_product and previous_product != operation.product_id:
                    bom_qty = operation.production_proposal_id.bom_id.product_qty or 1.0
                    _capacity, setup_minutes, _cleanup_minutes = (
                        operation.workcenter_id._get_capacity(
                            operation.product_id, operation.product_id.uom_id, bom_qty
                        )
                    )
                    setup = max(setup, (setup_minutes or 0.0) / 60.0)
                operation.write({"sequence": sequence, "setup_duration": setup})
                previous_product = operation.product_id
        return self.plan.operation_ids
