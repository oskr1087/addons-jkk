from odoo import fields

from .odoo19_compat import find_bom


class PlanningApplyService:
    def __init__(self, plan):
        self.plan = plan
        self.env = plan.env

    def run(self):
        snapshot = self.env['mrp.planning.snapshot'].create({
            'name': 'Before %s' % self.plan.name,
            'plan_id': self.plan.id,
            'payload': {'state': self.plan.state, 'supply_ids': self.plan.supply_ids.ids},
        })
        productions = self.env['mrp.production']
        purchases = self.env['purchase.order']
        for supply in self.plan.supply_ids.filtered(lambda row: row.state != 'applied' and row.supply_type in ('make', 'buy')):
            if supply.supply_type == 'make' and getattr(self.plan, 'include_manufacturing', True):
                production = self._get_or_create_mo(supply)
                supply.production_id = production.id
                if supply.production_proposal_id:
                    supply.production_proposal_id.write({'production_id': production.id, 'state': 'applied'})
                productions |= production
            elif supply.supply_type == 'buy' and getattr(self.plan, 'include_purchase', True):
                purchase = self._get_or_create_po(supply)
                supply.purchase_order_id = purchase.id
                purchases |= purchase
            supply.state = 'applied'
        snapshot.write({'production_ids': [(6, 0, productions.ids)], 'purchase_ids': [(6, 0, purchases.ids)]})
        self.plan.write({'state': 'applied'})
        return snapshot

    def _get_or_create_mo(self, supply):
        proposal = supply.production_proposal_id
        domain = [('state', '!=', 'cancel')]
        if proposal:
            domain.append(('planning_production_proposal_id', '=', proposal.id))
        else:
            domain += [('origin', '=', self.plan.name), ('product_id', '=', supply.product_id.id)]
        production = self.env['mrp.production'].search(domain, limit=1)
        if production:
            return production
        bom = proposal.bom_id if proposal and proposal.bom_id else find_bom(self.env, supply.product_id, company_id=self.plan.company_id.id)
        quantity = proposal.quantity if proposal else supply.quantity
        vals = {'origin': self.plan.name, 'product_id': supply.product_id.id, 'product_qty': quantity, 'product_uom_id': supply.product_id.uom_id.id, 'bom_id': bom.id if bom else False, 'company_id': self.plan.company_id.id, 'advanced_plan_id': self.plan.id, 'planning_production_proposal_id': proposal.id if proposal else False}
        production = self.env['mrp.production'].create(vals)
        if hasattr(production, 'action_confirm'):
            production.action_confirm()
        return production

    def _get_or_create_po(self, supply):
        proposal = supply.purchase_proposal_id
        seller = proposal.supplierinfo_id if proposal else supply.product_id.seller_ids.filtered(lambda s: not s.company_id or s.company_id == self.plan.company_id)[:1]
        if not seller:
            return self.env['purchase.order']
        purchase = self.env['purchase.order'].search([('origin', '=', self.plan.name), ('partner_id', '=', seller.partner_id.id), ('state', '!=', 'cancel')], limit=1)
        if not purchase:
            purchase = self.env['purchase.order'].create({'partner_id': seller.partner_id.id, 'origin': self.plan.name, 'company_id': self.plan.company_id.id})
        line = self.env['purchase.order.line'].search([('order_id', '=', purchase.id), ('product_id', '=', supply.product_id.id), ('product_uom_id', '=', supply.product_id.uom_id.id)], limit=1)
        if line:
            line.product_qty += supply.quantity
        else:
            price_unit = seller.product_uom_id._compute_price(seller.price_discounted, supply.product_id.uom_id)
            if seller.currency_id != purchase.currency_id:
                price_unit = seller.currency_id._convert(
                    price_unit, purchase.currency_id, self.plan.company_id,
                    fields.Date.to_date(supply.date_required or fields.Datetime.now()),
                )
            self.env['purchase.order.line'].create({
                'order_id': purchase.id,
                'product_id': supply.product_id.id,
                'name': supply.product_id.display_name,
                'product_qty': supply.quantity,
                'product_uom_id': supply.product_id.uom_id.id,
                'price_unit': price_unit,
                'date_planned': supply.date_required or fields.Datetime.now(),
            })
        if proposal:
            proposal.write({'purchase_order_id': purchase.id, 'state': 'applied'})
        return purchase
