from odoo import fields

from .demand_engine import DemandEngine
from .stock_projection_engine import StockProjectionEngine
from .bom_explosion_engine import BomExplosionEngine
from .supply_engine import SupplyEngine
from .operation_generation_engine import OperationGenerationEngine
from .calendar_scheduling_engine import CalendarSchedulingEngine
from .capacity_finite_engine import CapacityFiniteEngine
from .setup_sequence_engine import SetupSequenceEngine
from .conflict_resolution_engine import ConflictResolutionEngine
from .replanning_engine import ReplanningEngine


class PlanningEngine:
    def __init__(self, plan):
        self.plan = plan

    def run(self):
        run = self.plan.env['mrp.planning.run'].create({
            'plan_id': self.plan.id,
            'run_type': 'calculation',
            'state': 'running',
        })
        try:
            demand_count = DemandEngine(self.plan).run()
            StockProjectionEngine(self.plan).run()
            requirements = BomExplosionEngine(self.plan).run()
            supplies = SupplyEngine(self.plan).run()
            OperationGenerationEngine(self.plan).run()
            CalendarSchedulingEngine(self.plan).run()
            SetupSequenceEngine(self.plan).run()
            CalendarSchedulingEngine(self.plan).run()
            CapacityFiniteEngine(self.plan).run()
            ConflictResolutionEngine(self.plan).run()
            ReplanningEngine(self.plan).run()
            run.write({'state': 'completed', 'finished_at': fields.Datetime.now(), 'lines_processed': len(requirements) + len(supplies)})
            return {'demand_count': demand_count, 'run': run}
        except Exception as error:
            run.write({'state': 'failed', 'finished_at': fields.Datetime.now(), 'error_message': str(error)})
            raise
