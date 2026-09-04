from collections import defaultdict

from ..services.internal_stock import InternalWarehouseStock


class ComponentSourcingEngine:
    """Classify frozen APS components into Available/Move/Make/Buy.

    "Manufacture" is an APS visibility/sourcing classification only. APS does
    not create a child MO for that component; Odoo standard MRP is responsible
    for resolving its manufacturing supply from the finished-product flow.
    """

    MO_STATES = ('confirmed', 'progress', 'to_close')

    def __init__(self, plan):
        self.plan = plan
        self.env = plan.env
        self.company = plan.company_id

    def _confirmed_po(self, products, warehouses):
        result = defaultdict(float)
        if not products or not warehouses:
            return result
        lines = self.env['purchase.order.line'].sudo().search([
            ('company_id', '=', self.company.id),
            ('product_id', 'in', products.ids),
            ('order_id.state', '=', 'purchase'),
            ('order_id.picking_type_id.warehouse_id', 'in', warehouses.ids),
            ('date_planned', '<=', self.plan.date_end),
        ])
        for line in lines:
            warehouse = line.order_id.picking_type_id.warehouse_id
            pending = max(
                (line.product_qty or 0.0) - (line.qty_received or 0.0), 0.0
            )
            if warehouse and pending > 1e-9:
                result[(line.product_id.id, warehouse.id)] += (
                    line.product_uom_id._compute_quantity(
                        pending, line.product_id.uom_id
                    )
                )
        return result

    def _open_mo(self, products, warehouses):
        result = defaultdict(float)
        if not products or not warehouses:
            return result
        Production = self.env['mrp.production'].sudo()
        selection = Production._fields['state'].selection
        if callable(selection):
            selection = selection(self.env)
        valid_states = [
            state for state in self.MO_STATES
            if state in dict(selection)
        ]
        if not valid_states:
            return result
        mos = Production.search([
            ('company_id', '=', self.company.id),
            ('product_id', 'in', products.ids),
            ('state', 'in', valid_states),
            ('picking_type_id.warehouse_id', 'in', warehouses.ids),
        ])
        for mo in mos:
            warehouse = mo.picking_type_id.warehouse_id
            pending = max((mo.product_qty or 0.0) - (mo.qty_produced or 0.0), 0.0)
            if warehouse and pending > 1e-9:
                result[(mo.product_id.id, warehouse.id)] += (
                    mo.product_uom_id._compute_quantity(
                        pending, mo.product_id.uom_id
                    )
                )
        return result

    def _other_plan_supply(self, products, warehouses):
        result = defaultdict(float)
        domain = [
            ('plan_id', '!=', self.plan.id),
            ('plan_id.company_id', '=', self.company.id),
            ('plan_id.state', '=', 'calculated'),
            ('product_id', 'in', products.ids),
            ('target_warehouse_id', 'in', warehouses.ids),
            ('planner_production_qty', '>', 0),
        ]
        if self.plan.generated_purchase_plan_id:
            domain.append(
                ('plan_id', '!=', self.plan.generated_purchase_plan_id.id)
            )
        lines = self.env['mrp.planning.plan.line'].sudo().search(domain)
        for line in lines:
            key = (line.product_id.id, line.target_warehouse_id.id)
            if line.action_manufacture and not line.created_production_id:
                result[key] += line.planner_production_qty
            elif line.action_purchase and not line.created_purchase_line_id:
                result[key] += line.planner_production_qty
        return result

    def _pending_internal_incoming(self, products, warehouses):
        result = defaultdict(float)
        if not products or not warehouses:
            return result
        location_map = InternalWarehouseStock(
            self.env, self.company
        ).locations_by_warehouse(warehouses)
        Move = self.env['stock.move'].sudo()
        for warehouse in warehouses:
            locations = location_map.get(warehouse.id)
            if not locations:
                continue
            moves = Move.search([
                ('company_id', '=', self.company.id),
                ('product_id', 'in', products.ids),
                ('location_dest_id', 'in', locations.ids),
                ('location_id.usage', '=', 'internal'),
                ('state', 'in', ('confirmed', 'waiting', 'assigned', 'partially_available')),
            ])
            for move in moves:
                pending = max(
                    (move.product_uom_qty or 0.0)
                    - (getattr(move, 'quantity', 0.0) or 0.0),
                    0.0,
                )
                if pending > 1e-9:
                    result[(move.product_id.id, warehouse.id)] += (
                        move.product_uom._compute_quantity(
                            pending, move.product_id.uom_id
                        )
                    )
        return result

    def _subcontract_bom_map(self, products):
        """Return subcontracting BoM by product, in batch."""
        result = {}
        if not products:
            return result
        boms = self.env['mrp.bom'].sudo().search([
            ('active', '=', True),
            ('company_id', 'in', [False, self.company.id]),
            ('type', '=', 'subcontract'),
            ('product_tmpl_id', 'in', products.product_tmpl_id.ids),
        ], order='company_id desc, sequence, id')
        by_template = {}
        for bom in boms.sorted(key=lambda b: (b.sequence, b.id)):
            by_template.setdefault(bom.product_tmpl_id.id, self.env['mrp.bom'])
            by_template[bom.product_tmpl_id.id] |= bom

        for product in products:
            candidates = by_template.get(
                product.product_tmpl_id.id, self.env['mrp.bom']
            )
            exact = candidates.filtered(lambda bom: bom.product_id == product)
            generic = candidates.filtered(lambda bom: not bom.product_id)
            bom = exact[:1] or generic[:1]
            if bom:
                result[product.id] = bom
        return result

    def run(self):
        if self.plan.plan_type != 'manufacturing':
            return self.env['mrp.planning.production.component']

        components = self.plan.production_component_ids.filtered(
            lambda c: c.include_in_mo and c.product_id and c.planned_qty > 1e-9
        )
        # Preserve an explicit user decision not to move (move_qty = 0)
        # across sourcing refreshes.
        old_pending = self.plan.external_move_ids.filtered(
            lambda m: m.production_component_id and m.state == 'pending'
        )
        ignored_move_keys = {
            (
                move.production_component_id.id,
                move.source_warehouse_id.id,
                move.destination_warehouse_id.id,
            )
            for move in old_pending
            if move.move_qty <= 1e-9
        }
        old_pending.unlink()

        if not components:
            return components

        products = components.mapped('product_id')
        subcontract_boms = self._subcontract_bom_map(products)
        local_warehouses = self.plan.warehouse_ids
        all_wh = self.env['stock.warehouse'].sudo().search([
            ('company_id', '=', self.company.id)
        ])
        stock_helper = InternalWarehouseStock(self.env, self.company)
        local_stock = stock_helper.quantities(products, local_warehouses)
        # Any company warehouse other than the component destination can be
        # proposed as a transfer source, including another selected warehouse.
        external_stock = stock_helper.quantities(products, all_wh)
        po_supply = self._confirmed_po(products, local_warehouses)
        mo_supply = self._open_mo(products, local_warehouses)
        other_supply = self._other_plan_supply(products, local_warehouses)
        internal_incoming = self._pending_internal_incoming(
            products, local_warehouses
        )

        local_consumed = defaultdict(float)
        external_consumed = defaultdict(float)
        Component = self.env['mrp.planning.production.component']
        ExternalMove = self.env['mrp.planning.external.warehouse.move']

        # Reset all sourcing values, including omitted descendants.
        self.plan.production_component_ids.write({
            'effective_required_qty': 0.0,
            'local_supply_qty': 0.0,
            'external_move_suggested_qty': 0.0,
            'to_manufacture_qty': 0.0,
            'to_purchase_qty': 0.0,
            'supply_resolution': 'not_required',
            'is_subcontracted': False,
            'subcontract_bom_id': False,
        })

        by_parent = defaultdict(lambda: Component)
        for component in components:
            by_parent[component.parent_line_id.id if component.parent_line_id else False] |= component

        def resolve(component, effective_required):
            if effective_required <= 1e-9 or not component.include_in_mo:
                component.write({
                    'effective_required_qty': max(effective_required, 0.0),
                    'supply_resolution': 'not_required',
                })
                for child in component.child_line_ids:
                    resolve(child, 0.0)
                return

            destination = (
                component.planning_line_id.target_warehouse_id
                or self.plan.warehouse_ids[:1]
            )
            key = (component.product_id.id, destination.id)

            available_total = (
                local_stock[key]['free']
                + po_supply[key]
                + mo_supply[key]
                + other_supply[key]
                + internal_incoming[key]
            )
            remaining_local = max(
                available_total - local_consumed[key], 0.0
            )
            used_local = min(effective_required, remaining_local)
            local_consumed[key] += used_local
            shortage = max(effective_required - used_local, 0.0)

            # Other warehouses are suggestions only; they do not reduce the
            # buy/make quantity until the transfer is actually generated and
            # the plan is recalculated.
            movable = 0.0
            move_rows = []
            remaining_for_suggestion = shortage
            for source_wh in all_wh:
                if source_wh == destination:
                    continue
                ext_key = (component.product_id.id, source_wh.id)
                ext_free = max(
                    external_stock[ext_key]['free']
                    - external_consumed[ext_key],
                    0.0,
                )
                if ext_free <= 1e-9 or remaining_for_suggestion <= 1e-9:
                    continue
                move_key = (
                    component.id, source_wh.id, destination.id
                )
                if move_key in ignored_move_keys:
                    continue
                qty = min(ext_free, remaining_for_suggestion)
                external_consumed[ext_key] += qty
                movable += qty
                remaining_for_suggestion -= qty
                move_rows.append((source_wh, destination, qty, ext_free))

            has_children = bool(component.child_line_ids.filtered('include_in_mo'))
            subcontract_bom = subcontract_boms.get(component.product_id.id)
            is_subcontracted = bool(subcontract_bom)

            # A transfer from another warehouse is only a suggestion.  Do NOT
            # deduct it from the supply requirement until the transfer has
            # actually been created.  Once created, the plan is recalculated
            # and `_pending_internal_incoming()` incorporates that real move.
            #
            # This lets the planner choose:
            #   * move stock, then recalculate, OR
            #   * ignore the suggestion and manufacture/purchase the shortage.
            supply_shortage = shortage

            if shortage <= 1e-9:
                resolution = 'available'
                to_make = to_buy = 0.0
            elif is_subcontracted:
                # A subcontracted component is procured through Purchase.
                to_make = 0.0
                to_buy = supply_shortage
                resolution = (
                    'move_subcontract'
                    if movable > 1e-9
                    else 'subcontract'
                )
            elif has_children:
                to_make = supply_shortage
                to_buy = 0.0
                resolution = (
                    'move_manufacture'
                    if movable > 1e-9
                    else 'manufacture'
                )
            else:
                to_make = 0.0
                to_buy = supply_shortage
                resolution = (
                    'move_purchase'
                    if movable > 1e-9
                    else 'purchase'
                )

            component.with_context(
                aps_skip_subtree_rebuild=True,
                aps_skip_sourcing_refresh=True,
            ).write({
                'effective_required_qty': effective_required,
                'local_supply_qty': used_local,
                'external_move_suggested_qty': movable,
                'to_manufacture_qty': to_make,
                'to_purchase_qty': to_buy,
                'supply_resolution': resolution,
                'is_subcontracted': is_subcontracted,
                'subcontract_bom_id': subcontract_bom.id if subcontract_bom else False,
            })

            for source_wh, destination_wh, qty, ext_free in move_rows:
                ExternalMove.create({
                    'plan_id': self.plan.id,
                    'planning_line_id': component.planning_line_id.id,
                    'production_component_id': component.id,
                    'product_id': component.product_id.id,
                    'source_warehouse_id': source_wh.id,
                    'destination_warehouse_id': destination_wh.id,
                    'source_on_hand_qty': external_stock[
                        (component.product_id.id, source_wh.id)
                    ]['on_hand'],
                    'source_free_qty': ext_free,
                    'source_forecast_qty': ext_free,
                    'source_open_mo_qty': 0.0,
                    'destination_shortage_qty': shortage,
                    'suggested_qty': qty,
                    'move_qty': qty,
                })

            # Descendants are required only for the portion of this component
            # that APS really needs to manufacture.
            ratio = (
                to_make / component.planned_qty
                if component.planned_qty > 1e-9 else 0.0
            )
            for child in component.child_line_ids:
                # If the parent is subcontracted, APS purchases the parent
                # component. Its child materials remain visible in the tree
                # but are not separately purchased by this planner.
                child_required = (
                    0.0
                    if is_subcontracted
                    else child.planned_qty * ratio
                )
                resolve(child, child_required)

        roots = components.filtered(lambda c: not c.parent_line_id)
        for root in roots.sorted(key=lambda c: (c.planning_line_id.id, c.sequence, c.id)):
            resolve(root, root.planned_qty)

        components._aps_sync_default_lot_reservations()
        return components
