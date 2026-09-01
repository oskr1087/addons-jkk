from collections import defaultdict


class InternalWarehouseStock:
    """Explicit warehouse stock helper for APS.

    Stock availability is computed only from stock.quant records located in
    internal locations under the selected warehouse view location and belonging
    to the requested company. This intentionally avoids global stock leakage.
    """

    def __init__(self, env, company):
        self.env = env
        self.company = company

    def locations_by_warehouse(self, warehouses):
        Location = self.env['stock.location'].sudo()
        result = {}
        for warehouse in warehouses:
            result[warehouse.id] = Location.search([
                ('id', 'child_of', warehouse.view_location_id.id),
                ('usage', '=', 'internal'),
                ('company_id', 'in', [False, self.company.id]),
            ])
        return result

    def quantities(self, products, warehouses):
        """Return on_hand/reserved/free keyed by (product_id, warehouse_id)."""
        result = defaultdict(lambda: {
            'on_hand': 0.0,
            'reserved': 0.0,
            'free': 0.0,
        })
        if not products or not warehouses:
            return result

        Quant = self.env['stock.quant'].sudo()
        locations = self.locations_by_warehouse(warehouses)

        # One quant query per warehouse; aggregation happens in memory.
        for warehouse in warehouses:
            wh_locations = locations.get(warehouse.id)
            if not wh_locations:
                continue
            quants = Quant.search([
                ('company_id', '=', self.company.id),
                ('product_id', 'in', products.ids),
                ('location_id', 'in', wh_locations.ids),
            ])
            for quant in quants:
                key = (quant.product_id.id, warehouse.id)
                qty = quant.quantity or 0.0
                reserved = quant.reserved_quantity or 0.0
                result[key]['on_hand'] += qty
                result[key]['reserved'] += reserved

        for values in result.values():
            values['free'] = max(
                values['on_hand'] - values['reserved'],
                0.0,
            )
        return result
