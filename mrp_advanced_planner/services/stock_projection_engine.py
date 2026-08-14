from collections import defaultdict

from odoo import fields


class StockProjectionEngine:
    """Projects inventory without mutating quants or stock moves."""

    def __init__(self, plan):
        self.plan = plan

    def _locations(self):
        warehouse = self.plan.warehouse_id
        return self.plan.env['stock.location'].search([
            ('id', 'child_of', warehouse.view_location_id.id),
            ('usage', '=', 'internal'),
            ('company_id', 'in', (False, self.plan.company_id.id)),
        ])

    def _quantities(self, product_ids):
        quants = self.plan.env['stock.quant'].search([
            ('product_id', 'in', product_ids),
            ('location_id', 'in', self._locations().ids),
            ('company_id', '=', self.plan.company_id.id),
        ])
        result = defaultdict(lambda: {'stock': 0.0, 'reserved': 0.0})
        for quant in quants:
            result[quant.product_id.id]['stock'] += quant.quantity
            result[quant.product_id.id]['reserved'] += quant.reserved_quantity
        return result

    def _future_moves(self, product_ids):
        moves = self.plan.env['stock.move'].search([
            ('product_id', 'in', product_ids),
            ('company_id', '=', self.plan.company_id.id),
            ('state', 'not in', ('done', 'cancel')),
            ('date', '>=', self.plan.date_start),
            ('date', '<=', self.plan.date_end),
            '|',
            ('location_dest_id', 'in', self._locations().ids),
            ('location_id', 'in', self._locations().ids),
        ])
        result = defaultdict(lambda: {'incoming': 0.0, 'outgoing': 0.0})
        locations = self._locations()
        for move in moves:
            quantity = move.product_uom_id._compute_quantity(move.product_uom_qty, move.product_id.uom_id)
            if move.location_dest_id in locations and move.location_id not in locations:
                result[move.product_id.id]['incoming'] += quantity
            elif move.location_id in locations and move.location_dest_id not in locations:
                result[move.product_id.id]['outgoing'] += quantity
        return result

    def run(self):
        lines = self.plan.line_ids.filtered(lambda line: line.product_id)
        product_ids = lines.mapped('product_id').ids
        quantities = self._quantities(product_ids)
        moves = self._future_moves(product_ids)
        for line in lines.sorted(key=lambda item: (item.date_required or fields.Datetime.now(), item.id)):
            current = quantities[line.product_id.id]
            future = moves[line.product_id.id]
            projected = current['stock'] - current['reserved'] + future['incoming'] - future['outgoing']
            net = max(line.demand_qty - projected, 0.0)
            line.write({
                'stock_qty': current['stock'],
                'reserved_qty': current['reserved'],
                'incoming_qty': future['incoming'],
                'outgoing_qty': future['outgoing'],
                'net_requirement_qty': net,
                'state': 'blocked' if net else 'planned',
            })
        return True
