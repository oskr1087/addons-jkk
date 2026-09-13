from collections import defaultdict

from ..services.internal_stock import InternalWarehouseStock
from ..services.odoo19_compat import find_bom


class ComponentSourcingEngine:
    """Classify frozen APS components into Available/Move/Make/Buy.

    Normal BoM components generate APS sub-MOs. Phantom BoMs are exploded
    directly into the consuming MO. Subcontract BoMs are procured through
    Purchase/Subcontracting and leaf components are purchased.
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
            # Never use manufacturing created by THIS APS as generic product
            # supply. APS manufacturing is demand/node specific: an MO created
            # for one occurrence of BOPP must not cover another occurrence of
            # the same product in a different branch. Existing MOs of this plan
            # are accounted below by aps_planning_component_id only, to derive
            # pending_manufacture_qty without mutating the original APS decision.
            if mo.advanced_plan_id == self.plan:
                continue
            # Manufacturing committed to another APS is also demand-specific
            # and must not be consumed by this plan.
            if mo.advanced_plan_id:
                continue

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

    def _other_mo_unreserved_raw_demand(self, products, warehouses):
        """Raw-material demand committed to OTHER active MOs but not reserved.

        ``stock.quant.free`` already subtracts physically reserved quantities,
        but it does not subtract waiting/unreserved raw demand. Without this,
        a new APS can see stock as "free", buy only the apparent shortage, and
        later an older MO can reserve part of the receipt first.

        Return only the UNRESERVED remainder so reservations are never counted
        twice. MOs of this same APS are excluded because their reservations/
        execution commitments are handled separately.
        """
        result = defaultdict(float)
        if not products or not warehouses:
            return result

        stock_helper = InternalWarehouseStock(self.env, self.company)
        locations_by_wh = stock_helper.locations_by_warehouse(warehouses)
        location_to_wh = {}
        for warehouse in warehouses:
            for location in locations_by_wh.get(
                warehouse.id, self.env['stock.location']
            ):
                location_to_wh[location.id] = warehouse.id

        Move = self.env['stock.move'].sudo()
        moves = Move.search([
            ('company_id', '=', self.company.id),
            ('product_id', 'in', products.ids),
            ('raw_material_production_id', '!=', False),
            ('raw_material_production_id.state',
             'in', ('confirmed', 'progress', 'to_close')),
            ('state', 'not in', ('done', 'cancel')),
            ('location_id', 'in', list(location_to_wh)),
        ])

        moves = moves.filtered(
            lambda move:
                not move.raw_material_production_id.advanced_plan_id
                or move.raw_material_production_id.advanced_plan_id != self.plan
        )

        for move in moves:
            warehouse_id = location_to_wh.get(move.location_id.id)
            if not warehouse_id:
                continue

            required = move.product_uom._compute_quantity(
                move.product_uom_qty or 0.0,
                move.product_id.uom_id,
            )

            materialized = 0.0
            for ml in move.move_line_ids:
                qty = (
                    getattr(ml, 'quantity', 0.0)
                    or getattr(ml, 'qty_done', 0.0)
                    or 0.0
                )
                uom = (
                    getattr(ml, 'product_uom_id', False)
                    or getattr(ml, 'product_uom', False)
                )
                if uom and uom != move.product_id.uom_id:
                    qty = uom._compute_quantity(
                        qty, move.product_id.uom_id
                    )
                materialized += qty

            unreserved = max(required - materialized, 0.0)
            if unreserved > 1e-9:
                result[(move.product_id.id, warehouse_id)] += unreserved

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

    def _own_aps_reserved(self, products, warehouses):
        """Reserved raw material already secured by MOs of this APS.

        ``stock.quant`` free stock subtracts every Odoo reservation. Once the
        APS root/sub-MO is confirmed, its own reservation must NOT make the
        planner think the component became unavailable. This method adds back
        only reservations physically owned by manufacturing orders linked to
        the current plan.
        """
        result = defaultdict(float)
        if not products or not warehouses:
            return result

        stock_helper = InternalWarehouseStock(self.env, self.company)
        locations_by_wh = stock_helper.locations_by_warehouse(warehouses)
        location_to_wh = {}
        for warehouse in warehouses:
            for location in locations_by_wh.get(warehouse.id, self.env['stock.location']):
                location_to_wh[location.id] = warehouse.id

        productions = self.env['mrp.production'].sudo().search([
            ('advanced_plan_id', '=', self.plan.id),
            ('state', 'not in', ('done', 'cancel')),
        ])
        if not productions:
            return result

        moves = productions.mapped('move_raw_ids').filtered(
            lambda move:
                move.state not in ('done', 'cancel')
                and move.product_id in products
        )

        # Odoo 19 materializes reservations in stock.move.line. Summing move
        # lines avoids treating unreserved demand as secured stock.
        for line in moves.mapped('move_line_ids'):
            warehouse_id = location_to_wh.get(line.location_id.id)
            if not warehouse_id:
                continue

            qty = (
                getattr(line, 'quantity', 0.0)
                or getattr(line, 'qty_done', 0.0)
                or 0.0
            )
            if qty <= 1e-9:
                continue

            uom = (
                getattr(line, 'product_uom_id', False)
                or getattr(line, 'product_uom', False)
            )
            if uom and uom != line.product_id.uom_id:
                qty = uom._compute_quantity(qty, line.product_id.uom_id)

            result[(line.product_id.id, warehouse_id)] += qty

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

        # Repair traceability for sub-MOs created by older APS versions.
        # The authoritative link is mrp.production.aps_planning_component_id.
        # Persist the reverse component.generated_production_id so existing
        # plans recalculate exactly like newly-created ones.
        if components:
            existing_submos = self.env['mrp.production'].sudo().search([
                ('advanced_plan_id', '=', self.plan.id),
                ('aps_planning_component_id', 'in', components.ids),
                ('state', '!=', 'cancel'),
            ])
            for mo in existing_submos:
                component = mo.aps_planning_component_id
                if (
                    component
                    and component.generated_production_id != mo
                ):
                    component.with_context(
                        aps_skip_sourcing_refresh=True,
                        aps_skip_change_tracking=True,
                    ).write({
                        'generated_production_id': mo.id,
                    })
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
        # Other APS planning is demand-specific and must not be consumed as
        # generic supply by this APS.
        other_supply = defaultdict(float)
        internal_incoming = self._pending_internal_incoming(
            products, local_warehouses
        )
        own_aps_reserved = self._own_aps_reserved(
            products, local_warehouses
        )
        other_mo_unreserved = self._other_mo_unreserved_raw_demand(
            products, local_warehouses
        )

        # Native sub-MOs created from this APS are real execution commitments.
        # Once one exists, its remaining quantity still requires its own raw
        # materials even if a later transfer/open supply makes the parent
        # component itself appear covered. Otherwise APS incorrectly turns all
        # descendants into "No abastecer - padre cubierto" while the real
        # sub-MO still needs those materials.
        active_component_mo_qty = defaultdict(float)
        component_mos = self.env['mrp.production'].sudo().search([
            ('advanced_plan_id', '=', self.plan.id),
            ('aps_planning_component_id', 'in', components.ids),
            ('state', 'not in', ('done', 'cancel')),
        ])
        for mo in component_mos:
            component = mo.aps_planning_component_id
            if not component:
                continue
            remaining = max(
                (mo.product_qty or 0.0) - (mo.qty_produced or 0.0),
                0.0,
            )
            if remaining <= 1e-9:
                continue
            if mo.product_uom_id and mo.product_uom_id != component.product_id.uom_id:
                remaining = mo.product_uom_id._compute_quantity(
                    remaining, component.product_id.uom_id
                )
            active_component_mo_qty[component.id] += remaining

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
            'pending_manufacture_qty': 0.0,
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

            # Odoo MRP treats non-stockable goods as available for consumption:
            # there is no quant reservation to satisfy. APS must mirror that
            # behavior instead of manufacturing/purchasing a fictitious stock
            # shortage.
            if not component.product_id.is_storable:
                component.with_context(
                    aps_skip_subtree_rebuild=True,
                    aps_skip_sourcing_refresh=True,
                ).write({
                    'effective_required_qty': effective_required,
                    'local_supply_qty': effective_required,
                    'external_move_suggested_qty': 0.0,
                    'to_manufacture_qty': 0.0,
                    'pending_manufacture_qty': 0.0,
                    'to_purchase_qty': 0.0,
                    'supply_resolution': 'available',
                    'is_subcontracted': False,
                    'subcontract_bom_id': False,
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
                # Free quant stock is not truly free if an older/other active
                # MO still has waiting raw-material demand that is not yet
                # materialized as a quant reservation.
                max(
                    local_stock[key]['free']
                    - other_mo_unreserved[key],
                    0.0,
                )
                # Free stock excludes every Odoo reservation. Add back only
                # quantity already reserved by MOs of THIS same APS.
                + own_aps_reserved[key]
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

            active_children = component.child_line_ids.filtered('include_in_mo')
            # Prefer the BoM actually represented by the frozen subtree.  If
            # this node currently has no children, fall back to the product's
            # applicable manufacturing BoM.  This is the key case for
            # recursive submanufacturing: a fabricable leaf must still create
            # its own native child MO even when it has no raw children.
            component_bom = active_children[:1].source_bom_id if active_children else find_bom(
                self.env,
                component.product_id,
                company_id=self.company.id,
                picking_type_id=(
                    destination.manu_type_id.id
                    if destination and destination.manu_type_id else False
                ),
            )
            is_phantom = bool(component_bom and component_bom.type == 'phantom')
            is_manufacturable = bool(
                component_bom and component_bom.type == 'normal'
            )
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
                to_make = 0.0
                to_buy = supply_shortage
                resolution = (
                    'move_subcontract' if movable > 1e-9 else 'subcontract'
                )
            elif is_phantom:
                # Kit/phantom: consume its children directly.
                to_make = to_buy = 0.0
                resolution = 'phantom'
            elif is_manufacturable:
                to_make = supply_shortage
                to_buy = 0.0
                resolution = (
                    'move_manufacture' if movable > 1e-9 else 'manufacture'
                )
            else:
                to_make = 0.0
                to_buy = supply_shortage
                resolution = (
                    'move_purchase' if movable > 1e-9 else 'purchase'
                )

            # Keep the APS manufacturing decision immutable with respect to
            # execution documents. Existing child MOs reduce only what remains
            # to GENERATE, never the planned quantity itself. This prevents a
            # recalculation from turning 47.8384 into 0.4384 merely because a
            # 47.4000 MO exists for another/previous execution state.
            committed_make = active_component_mo_qty.get(component.id, 0.0)
            pending_make = max(to_make - committed_make, 0.0)

            component.with_context(
                aps_skip_subtree_rebuild=True,
                aps_skip_sourcing_refresh=True,
            ).write({
                'effective_required_qty': effective_required,
                'local_supply_qty': used_local,
                'external_move_suggested_qty': movable,
                'to_manufacture_qty': to_make,
                'pending_manufacture_qty': pending_make,
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

            # Descendant demand has two sources:
            #
            # 1) new manufacturing still required by this recalculation;
            # 2) manufacturing ALREADY committed in a native APS sub-MO.
            #
            # The second one is essential after transfers/recalculations:
            # an existing sub-MO does not stop needing RESINA/MARLEX/etc.
            # merely because its finished/intermediate product is now also
            # visible as covered supply.
            if is_phantom:
                descendant_demand = supply_shortage
            elif is_subcontracted:
                # A subcontracted parent is purchased from the subcontractor,
                # but the direct materials in its subcontract BoM still belong
                # to OUR supply responsibility. Plan only the portion that is
                # actually subcontracted (the uncovered parent shortage). This
                # keeps tracked materials eligible for APS lot reservation and
                # lets their own shortages be manufactured/purchased before the
                # native Odoo resupply-to-subcontractor movement is executed.
                descendant_demand = supply_shortage
            elif is_manufacturable:
                # The active sub-MO is the execution document for this same
                # component demand. Do not add it again to a fresh calculated
                # make quantity or descendants would be duplicated.
                descendant_demand = max(committed_make, to_make)
            else:
                descendant_demand = 0.0

            ratio = (
                descendant_demand / component.planned_qty
                if component.planned_qty > 1e-9 else 0.0
            )
            for child in component.child_line_ids:
                child_required = child.planned_qty * ratio
                resolve(child, child_required)

        roots = components.filtered(lambda c: not c.parent_line_id)
        for root in roots.sorted(key=lambda c: (c.planning_line_id.id, c.sequence, c.id)):
            resolve(root, root.planned_qty)

        components._aps_sync_default_lot_reservations()
        return components
