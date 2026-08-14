from collections import defaultdict
from datetime import timedelta
from odoo import fields

class PlannerEngine:
    """Orchestrates a non-invasive calculation and an idempotent application."""
    def __init__(self, plan): self.plan = plan

    def calculate(self):
        self._clear_previous()
        self._collect_demands(); self._project_stock(); self._explode_boms(); self._plan_supply(); self._schedule()

    def _clear_previous(self):
        self.plan.demand_ids.unlink(); self.plan.requirement_ids.unlink(); self.plan.supply_ids.unlink(); self.plan.operation_ids.unlink(); self.plan.conflict_ids.unlink()

    def _collect_demands(self):
        DemandEngine(self.plan).run()
    def _project_stock(self):
        StockProjectionEngine(self.plan).run()
    def _explode_boms(self):
        BomExplosionEngine(self.plan).run()
    def _plan_supply(self):
        SupplyEngine(self.plan).run()
    def _schedule(self):
        CapacityEngine(self.plan).run(); SchedulingEngine(self.plan).run()

    def apply(self):
        """Creates only proposals not previously applied; no duplicate MO/PO on retries."""
        SupplyApplication(self.plan).run()

class DemandEngine:
    def __init__(self, plan): self.plan = plan
    def run(self):
        lines = self.plan.env['sale.order.line'].search([('order_id.state','in',('sale','done')),('order_id.warehouse_id','=',self.plan.warehouse_id.id),('product_id','!=',False)])
        for line in lines:
            qty = line.product_uom_qty - line.qty_delivered
            if qty > 0 and self.plan.date_start <= line.order_id.commitment_date <= self.plan.date_end:
                self.plan.env['mrp.advanced.demand'].create({'plan_id': self.plan.id, 'sale_line_id': line.id, 'origin': f'sale.order,{line.order_id.id}', 'product_id': line.product_id.id, 'quantity': qty, 'uom_id': line.product_uom.id, 'date_required': line.order_id.commitment_date})

class StockProjectionEngine:
    def __init__(self, plan): self.plan = plan
    def run(self):
        for demand in self.plan.demand_ids:
            available = sum(self.plan.env['stock.quant'].search([('product_id','=',demand.product_id.id),('location_id.usage','=','internal')]).mapped('quantity'))
            demand.write({'qty_available': available, 'qty_short': max(demand.quantity - available, 0), 'state': 'covered' if available >= demand.quantity else 'open'})

class BomExplosionEngine:
    def __init__(self, plan): self.plan = plan
    def run(self):
        for demand in self.plan.demand_ids.filtered(lambda d: d.qty_short > 0):
            bom = self.plan.env['mrp.bom']._bom_find(demand.product_id, company_id=self.plan.company_id.id).get(demand.product_id)
            self._explode(demand.product_id, demand.qty_short, demand.date_required, demand, bom, 0)
    def _explode(self, product, qty, due, demand, bom, level):
        req = self.plan.env['mrp.advanced.requirement'].create({'plan_id': self.plan.id, 'demand_id': demand.id, 'product_id': product.id, 'quantity': qty, 'date_required': due, 'level': level, 'trace_key': f'{demand.id}:{product.id}:{level}'})
        if not bom: return req
        for line in bom.bom_line_ids:
            child_bom = self.plan.env['mrp.bom']._bom_find(line.product_id, company_id=self.plan.company_id.id).get(line.product_id)
            child = self._explode(line.product_id, qty * line.product_qty / bom.product_qty, due, demand, child_bom, level + 1)
            child.parent_id = req.id
        return req

class SupplyEngine:
    def __init__(self, plan): self.plan = plan
    def run(self):
        for req in self.plan.requirement_ids:
            if self.plan.env['stock.quant'].search_count([('product_id','=',req.product_id.id),('quantity','>=',req.quantity)]): kind = 'available'
            elif req.product_id.bom_count: kind = 'make'
            elif req.product_id.seller_ids: kind = 'buy'
            else: kind = 'blocked'; self.plan.env['mrp.advanced.conflict'].create({'plan_id': self.plan.id, 'severity':'error', 'conflict_type':'material', 'product_id':req.product_id.id, 'message':'No route, BOM or vendor available.'})
            self.plan.env['mrp.advanced.supply'].create({'plan_id':self.plan.id,'requirement_id':req.id,'product_id':req.product_id.id,'supply_type':kind,'quantity':req.quantity,'date_required':req.date_required})

class CapacityEngine:
    def __init__(self, plan): self.plan = plan

    def run(self):
        for supply in self.plan.supply_ids.filtered(lambda s: s.supply_type == 'make'):
            bom = self.plan.env['mrp.bom']._bom_find(supply.product_id, company_id=self.plan.company_id.id).get(supply.product_id)
            if not bom:
                continue
            for sequence, operation in enumerate(bom.operation_ids):
                if not operation.workcenter_id:
                    self.plan.env['mrp.advanced.conflict'].create({'plan_id': self.plan.id, 'severity': 'error', 'conflict_type': 'route', 'product_id': supply.product_id.id, 'message': 'Operation has no work center.'})
                    continue
                hours = (operation.time_cycle * supply.quantity / (bom.product_qty or 1.0)) / 60.0
                self.plan.env['mrp.advanced.operation'].create({'plan_id': self.plan.id, 'workcenter_id': operation.workcenter_id.id, 'product_id': supply.product_id.id, 'name': operation.name, 'duration': hours, 'sequence': sequence, 'date_start': supply.date_required, 'date_end': supply.date_required})


class SchedulingEngine:
    def __init__(self, plan): self.plan = plan

    def run(self):
        from datetime import timedelta
        operations = self.plan.operation_ids.sorted(key=lambda op: (op.workcenter_id.id, op.sequence))
        for operation in operations:
            end = operation.date_end or fields.Datetime.now()
            start = end - timedelta(hours=operation.duration + operation.setup_duration)
            operation.write({'date_start': start, 'date_end': end})
        if not self.plan.finite_capacity:
            return
        for workcenter in self.plan.env['mrp.workcenter'].search([('company_id', '=', self.plan.company_id.id)]):
            ops = operations.filtered(lambda op: op.workcenter_id == workcenter)
            for left in ops:
                for right in ops:
                    if left.id >= right.id:
                        continue
                    if left.date_start < right.date_end and right.date_start < left.date_end:
                        left.state = right.state = 'conflict'
                        self.plan.env['mrp.advanced.conflict'].create({'plan_id': self.plan.id, 'severity': 'warning', 'conflict_type': 'capacity', 'workcenter_id': workcenter.id, 'message': 'Overlapping operations exceed finite capacity.'})
                        break


class SupplyApplication:
    def __init__(self, plan): self.plan = plan

    def run(self):
        for supply in self.plan.supply_ids.filtered(lambda s: s.state not in ('applied', 'cancelled') and s.supply_type in ('make', 'buy')):
            if supply.supply_type == 'make' and self.plan.include_manufacturing:
                mo = self.plan.env['mrp.production'].search([('origin', '=', self.plan.name), ('product_id', '=', supply.product_id.id), ('state', '!=', 'cancel')], limit=1)
                if not mo:
                    bom = self.plan.env['mrp.bom']._bom_find(supply.product_id, company_id=self.plan.company_id.id).get(supply.product_id)
                    mo = self.plan.env['mrp.production'].create({'origin': self.plan.name, 'product_id': supply.product_id.id, 'product_qty': supply.quantity, 'product_uom_id': supply.product_id.uom_id.id, 'bom_id': bom.id if bom else False, 'date_start': supply.date_required})
                supply.production_id = mo.id
                if supply.production_proposal_id:
                    supply.production_proposal_id.write({'production_id': mo.id, 'state': 'applied'})
            elif supply.supply_type == 'buy' and self.plan.include_purchase:
                seller = supply.product_id.seller_ids[:1]
                if seller:
                    po = self.plan.env['purchase.order'].search([('origin', '=', self.plan.name), ('partner_id', '=', seller.partner_id.id), ('state', '!=', 'cancel')], limit=1)
                    if not po:
                        po = self.plan.env['purchase.order'].create({'partner_id': seller.partner_id.id, 'origin': self.plan.name})
                    line = self.plan.env['purchase.order.line'].search([('order_id', '=', po.id), ('product_id', '=', supply.product_id.id)], limit=1)
                    if not line:
                        line = self.plan.env['purchase.order.line'].create({'order_id': po.id, 'product_id': supply.product_id.id, 'name': supply.product_id.display_name, 'product_qty': supply.quantity, 'product_uom': supply.product_id.uom_id.id, 'price_unit': seller.price, 'date_planned': supply.date_required})
                    else:
                        line.product_qty += supply.quantity
                    supply.purchase_order_id = po.id
                    if supply.purchase_proposal_id:
                        supply.purchase_proposal_id.write({'purchase_order_id': po.id, 'state': 'applied'})
            supply.state = 'applied'
