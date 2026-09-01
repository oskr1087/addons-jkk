from collections import defaultdict
from datetime import timedelta

from odoo import fields

from .run_cache import PlanningRunCache
from .odoo19_compat import find_bom


class SupplyEngine:
    """Selects the least disruptive native route for each material requirement."""

    def __init__(self, plan):
        self.plan = plan
        self.env = plan.env
        self.cache = PlanningRunCache(self.env)

    def _find_bom(self, product):
        return find_bom(self.env, product, company_id=self.plan.company_id.id)

    def _available(self, product):
        return self.cache.stock_available(product, self.plan.company_id.id, self.plan.warehouse_id.id)

    def _vendor(self, product, date_required):
        required_date = fields.Date.to_date(date_required) if date_required else fields.Date.context_today(product)
        sellers = product.seller_ids.filtered(
            lambda seller: (not seller.company_id or seller.company_id == self.plan.company_id)
            and (not seller.product_id or seller.product_id == product)
            and (not seller.date_start or seller.date_start <= required_date)
            and (not seller.date_end or seller.date_end >= required_date)
        )
        return sellers.sorted(key=lambda seller: (seller.sequence, -seller.min_qty, seller.price, seller.id))[0] if sellers else False

    def _route(self, requirement):
        available = self._available(requirement.product_id)
        if available >= requirement.required_qty:
            return 'available', available
        if self._find_bom(requirement.product_id):
            return 'make', available
        if self._vendor(requirement.product_id, requirement.date_required):
            return 'buy', available
        return 'blocked', available

    def run(self):
        # Rebuild all derived supply/proposal records from scratch. Operations are
        # regenerated later by OperationGenerationEngine, so stale proposals must
        # not survive a recalculation (their UNIQUE keys would otherwise collide).
        self.plan.operation_ids.unlink()
        self.plan.supply_ids.unlink()
        self.plan.production_proposal_ids.unlink()
        self.plan.purchase_proposal_ids.unlink()
        conflicts = self.env['mrp.planning.conflict']
        for requirement in self.plan.requirement_ids.sorted(key=lambda item: (item.date_required, item.level, item.id)):
            kind, available = self._route(requirement)
            net = max(requirement.required_qty - available, 0.0)
            requirement.write({'available_qty': available, 'net_qty': net, 'supply_type': kind})
            if kind == 'available':
                continue
            if kind == 'blocked':
                conflicts.create({
                    'plan_id': self.plan.id,
                    'severity': 'error',
                    'conflict_type': 'material_shortage',
                    'product_id': requirement.product_id.id,
                    'message': 'No usable BOM or vendor is configured for this requirement.',
                })
                continue
            self.env['mrp.planning.supply'].create({
                'plan_id': self.plan.id,
                'requirement_id': requirement.id,
                'product_id': requirement.product_id.id,
                'supply_type': kind,
                'quantity': net or requirement.required_qty,
                'date_required': requirement.date_required,
                'logical_key': f'{self.plan.id}:{requirement.id}:{kind}',
                'state': 'draft',
            })
        self._build_proposals()
        return self.plan.supply_ids

    def _build_proposals(self):
        production_model = self.env['mrp.planning.production.proposal']
        purchase_model = self.env['mrp.planning.purchase.proposal']
        production_groups = defaultdict(list)
        purchase_groups = defaultdict(list)
        for supply in self.plan.supply_ids.filtered(lambda item: item.supply_type in ('make', 'buy')):
            if supply.supply_type == 'make':
                production_groups[(supply.product_id.id, supply.date_required)].append(supply)
            else:
                vendor = self._vendor(supply.product_id, supply.date_required)
                if vendor:
                    purchase_groups[(supply.product_id.id, vendor.partner_id.id, supply.date_required)].append((supply, vendor))
        for (product_id, date_required), supplies in production_groups.items():
            product = self.env['product.product'].browse(product_id)
            bom = self._find_bom(product)
            proposal = production_model.create({'name': 'MO Proposal - %s' % product.display_name, 'plan_id': self.plan.id, 'product_id': product.id, 'bom_id': bom.id if bom else False, 'quantity': sum(item.quantity for item in supplies), 'date_required': date_required, 'origin': self.plan.name})
            for supply in supplies:
                supply.production_proposal_id = proposal.id
        for (product_id, vendor_id, date_required), entries in purchase_groups.items():
            product = self.env['product.product'].browse(product_id)
            vendor = self.env['res.partner'].browse(vendor_id)
            supplierinfo = self._vendor(product, date_required)
            delay = supplierinfo.delay if supplierinfo else 0
            proposal = purchase_model.create({'name': 'PO Proposal - %s' % product.display_name, 'plan_id': self.plan.id, 'product_id': product.id, 'vendor_id': vendor.id, 'supplierinfo_id': supplierinfo.id if supplierinfo else False, 'quantity': sum(item.quantity for item, _vendor in entries), 'date_required': date_required, 'date_planned': date_required - timedelta(days=delay), 'price_unit': supplierinfo.price if supplierinfo else 0.0, 'origin': self.plan.name})
            for supply, _vendor in entries:
                supply.purchase_proposal_id = proposal.id
