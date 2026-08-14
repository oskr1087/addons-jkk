from collections import defaultdict


class PlanningRunCache:
    """Per-run cache; never shared between companies or planning executions."""

    def __init__(self, env):
        self.env = env
        self.boms = {}
        self.vendors = {}
        self.locations = {}
        self.stock = {}

    def internal_locations(self, company_id, warehouse_id):
        key = (company_id, warehouse_id)
        if key not in self.locations:
            warehouse = self.env['stock.warehouse'].browse(warehouse_id)
            self.locations[key] = self.env['stock.location'].search([
                ('usage', '=', 'internal'),
                ('company_id', 'in', (False, company_id)),
                ('id', 'child_of', warehouse.lot_stock_id.id),
            ])
        return self.locations[key]

    def stock_available(self, product, company_id, warehouse_id):
        key = (product.id, company_id, warehouse_id)
        if key not in self.stock:
            quants = self.env['stock.quant'].search([
                ('product_id', '=', product.id),
                ('location_id', 'in', self.internal_locations(company_id, warehouse_id).ids),
            ])
            self.stock[key] = sum(quants.mapped('quantity')) - sum(quants.mapped('reserved_quantity'))
        return self.stock[key]
