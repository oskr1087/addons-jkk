from odoo import fields


class OperationGenerationEngine:
    def __init__(self, plan):
        self.plan = plan
        self.env = plan.env

    def run(self):
        self.plan.operation_ids.unlink()
        operations = self.env["mrp.planning.operation"]
        for proposal in self.plan.production_proposal_ids.filtered(
            lambda item: item.state != "cancelled"
        ):
            if not proposal.bom_id:
                continue
            for routing in proposal.bom_id.operation_ids.sorted("sequence"):
                workcenter = routing.workcenter_id
                if not workcenter:
                    self.env["mrp.planning.conflict"].create(
                        {
                            "plan_id": self.plan.id,
                            "conflict_type": "calendar_conflict",
                            "severity": "error",
                            "product_id": proposal.product_id.id,
                            "message": "Routing operation has no work center.",
                        }
                    )
                    continue
                capacity, setup_minutes, cleanup_minutes = workcenter._get_capacity(
                    proposal.product_id,
                    proposal.product_uom_id,
                    proposal.bom_id.product_qty or 1.0,
                )
                capacity = max(capacity or 1.0, 1.0)
                cycles = max(proposal.quantity / capacity, 0.0)
                efficiency = max(workcenter.time_efficiency or 100.0, 1.0)
                processing_minutes = cycles * routing.time_cycle * 100.0 / efficiency
                operations.create(
                    {
                        "plan_id": self.plan.id,
                        "production_proposal_id": proposal.id,
                        "product_id": proposal.product_id.id,
                        "bom_operation_id": routing.id,
                        "workcenter_id": workcenter.id,
                        "name": routing.name,
                        "sequence": routing.sequence,
                        "quantity": proposal.quantity,
                        "duration": processing_minutes / 60.0,
                        "setup_duration": (setup_minutes + cleanup_minutes) / 60.0,
                        "date_end": proposal.date_required,
                    }
                )
        return self.plan.operation_ids
