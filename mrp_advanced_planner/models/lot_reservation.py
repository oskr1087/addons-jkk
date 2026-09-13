from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class MrpPlanningComponentLotReservation(models.Model):
    _name = 'mrp.planning.component.lot.reservation'
    _description = 'Reserva APS de lote para componente'
    _order = 'plan_id, component_id, lot_id, id'

    plan_id = fields.Many2one(
        'mrp.planning.plan', required=True, ondelete='cascade', index=True,
    )
    planning_line_id = fields.Many2one(
        'mrp.planning.plan.line', required=True, ondelete='cascade', index=True,
    )
    component_id = fields.Many2one(
        'mrp.planning.production.component',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        related='plan_id.company_id', store=True, index=True,
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse', required=True, check_company=True, index=True,
    )
    product_id = fields.Many2one(
        related='component_id.product_id', store=True, index=True,
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lote / Serie',
        required=True,
        index=True,
        domain="[('product_id', '=', product_id), ('company_id', 'in', [False, company_id])]",
    )
    reserved_qty = fields.Float(
        string='Cantidad reservada',
        required=True,
        digits=(16, 4),
    )
    available_qty = fields.Float(
        string='Disponible actual',
        compute='_compute_available_qty',
        digits=(16, 4),
    )
    production_id = fields.Many2one(
        'mrp.production',
        string='Orden de fabricación',
        readonly=True,
        copy=False,
        ondelete='set null',
        index=True,
    )
    state = fields.Selection([
        ('reserved', 'Reservado APS'),
        ('assigned', 'Asignado a OF'),
        ('released', 'Liberado'),
        ('consumed', 'Consumido'),
    ], default='reserved', required=True, index=True)

    @api.depends('lot_id', 'warehouse_id', 'product_id')
    def _compute_available_qty(self):
        Quant = self.env['stock.quant'].sudo()
        for reservation in self:
            reservation.available_qty = 0.0
            if (
                not reservation.lot_id
                or not reservation.product_id
                or not reservation.warehouse_id
            ):
                continue
            locations = self.env['stock.location'].sudo().search([
                ('id', 'child_of', reservation.warehouse_id.view_location_id.id),
                ('usage', '=', 'internal'),
                ('company_id', 'in', [False, reservation.company_id.id]),
            ])
            quants = Quant.search([
                ('product_id', '=', reservation.product_id.id),
                ('lot_id', '=', reservation.lot_id.id),
                ('location_id', 'in', locations.ids),
            ])
            reservation.available_qty = sum(
                max(
                    (quant.quantity or 0.0)
                    - (getattr(quant, 'reserved_quantity', 0.0) or 0.0),
                    0.0,
                )
                for quant in quants
            )

    def _check_engineering_unlocked(self):
        locked = self.filtered('component_id.engineering_locked')
        if locked and not self.env.context.get(
            'aps_allow_locked_lot_reservation_write'
        ):
            raise UserError(_(
                'Los lotes de este componente ya no se pueden modificar '
                'porque la Orden de Fabricación fue generada.'
            ))

    @api.constrains(
        'lot_id', 'state', 'component_id', 'reserved_qty', 'warehouse_id'
    )
    def _check_exclusive_lot(self):
        """APS reservations cannot invade stock already reserved by Odoo.

        Capacity = physical lot quantity - Odoo reservations unrelated to APS.
        Odoo reservations belonging to APS MOs are already represented by the
        logical APS reservation and therefore are not counted twice.
        """
        Quant = self.env['stock.quant'].sudo()
        MoveLine = self.env['stock.move.line'].sudo()

        for reservation in self.filtered(
            lambda row:
                row.lot_id
                and row.warehouse_id
                and row.state in ('reserved', 'assigned')
        ):
            locations = self.env['stock.location'].sudo().search([
                ('id', 'child_of',
                 reservation.warehouse_id.view_location_id.id),
                ('usage', '=', 'internal'),
                ('company_id', 'in',
                 [False, reservation.company_id.id]),
            ])
            quants = Quant.search([
                ('product_id', '=', reservation.product_id.id),
                ('lot_id', '=', reservation.lot_id.id),
                ('location_id', 'in', locations.ids),
            ])
            physical_qty = sum(quants.mapped('quantity'))
            odoo_reserved_total = sum(
                getattr(quant, 'reserved_quantity', 0.0) or 0.0
                for quant in quants
            )

            active = self.search([
                ('lot_id', '=', reservation.lot_id.id),
                ('warehouse_id', '=', reservation.warehouse_id.id),
                ('state', 'in', ('reserved', 'assigned')),
                ('plan_id.state', 'in', ('calculated', 'approved')),
            ])
            aps_reserved_qty = sum(active.mapped('reserved_qty'))

            # Materialized Odoo reservations belonging to these same APS
            # logical demands must not reduce APS capacity a second time.
            # production_id is the primary owner. For legacy/transitional rows
            # also accept raw moves explicitly linked to any active component.
            aps_productions = active.mapped('production_id')
            active_components = active.mapped('component_id')
            move_domain = [
                ('product_id', '=', reservation.product_id.id),
                ('lot_id', '=', reservation.lot_id.id),
                ('location_id', 'in', locations.ids),
                ('move_id.state', 'not in', ('done', 'cancel')),
            ]
            move_lines = MoveLine.search(move_domain).filtered(
                lambda line:
                    (
                        line.move_id.raw_material_production_id
                        and line.move_id.raw_material_production_id
                        in aps_productions
                    )
                    or (
                        getattr(
                            line.move_id,
                            'aps_planning_component_id',
                            False,
                        )
                        and line.move_id.aps_planning_component_id
                        in active_components
                    )
            )

            odoo_reserved_by_aps = 0.0
            for line in move_lines:
                qty = (
                    getattr(line, 'quantity', 0.0)
                    or getattr(line, 'qty_done', 0.0)
                    or 0.0
                )
                uom = (
                    getattr(line, 'product_uom_id', False)
                    or getattr(line, 'product_uom', False)
                )
                if uom and uom != reservation.product_id.uom_id:
                    qty = uom._compute_quantity(
                        qty, reservation.product_id.uom_id
                    )
                odoo_reserved_by_aps += qty

            unrelated_odoo_reserved = max(
                odoo_reserved_total - odoo_reserved_by_aps,
                0.0,
            )
            capacity_for_aps = max(
                physical_qty - unrelated_odoo_reserved,
                0.0,
            )

            if aps_reserved_qty > capacity_for_aps + 1e-6:
                others = active - reservation
                owner = others[:1]
                raise ValidationError(_(
                    'No hay capacidad disponible para reservar el lote '
                    '%(lot)s.\n\n'
                    'Producto: %(product)s\n'
                    'Almacén: %(warehouse)s\n'
                    'Cantidad física: %(physical).4f\n'
                    'Reservas Odoo ajenas al APS: %(odoo).4f\n'
                    'Capacidad utilizable por APS: %(capacity).4f\n'
                    'Reservado APS total: %(aps).4f\n'
                    'Cantidad solicitada: %(requested).4f\n'
                    'Otra planificación: %(plan)s\n'
                    'OF que ocupan cantidad fuera de este APS: %(mos)s\n\n'
                    'Revise las reservas/movimientos existentes o utilice '
                    '"Reasignar lotes".'
                ) % {
                    'lot': reservation.lot_id.display_name,
                    'product': reservation.product_id.display_name,
                    'warehouse': reservation.warehouse_id.display_name,
                    'physical': physical_qty,
                    'odoo': unrelated_odoo_reserved,
                    'capacity': capacity_for_aps,
                    'aps': aps_reserved_qty,
                    'requested': reservation.reserved_qty,
                    'plan': (
                        owner.plan_id.display_name if owner else '-'
                    ),
                    'mos': ', '.join(
                        move_lines.filtered(
                            lambda line:
                                line.move_id.raw_material_production_id
                                and line.move_id.raw_material_production_id
                                not in aps_productions
                        ).mapped(
                            'move_id.raw_material_production_id.display_name'
                        )
                    ) or '-',
                })

    @api.constrains('reserved_qty')
    def _check_positive_qty(self):
        for reservation in self:
            if reservation.reserved_qty <= 0:
                raise ValidationError(
                    _('La cantidad reservada debe ser mayor que cero.')
                )

    @api.model_create_multi
    def create(self, vals_list):
        Component = self.env['mrp.planning.production.component']
        for vals in vals_list:
            component = Component.browse(vals.get('component_id')).exists()
            if (
                component
                and component.engineering_locked
                and not self.env.context.get(
                    'aps_allow_locked_lot_reservation_write'
                )
            ):
                raise UserError(_(
                    'No puede cambiar lotes después de generar la OF desde '
                    'edición manual. Use las acciones de cargar o reasignar '
                    'lotes APS.'
                ))
            if component:
                vals.setdefault('plan_id', component.plan_id.id)
                vals.setdefault(
                    'planning_line_id', component.planning_line_id.id
                )
                warehouse = (
                    component.planning_line_id.target_warehouse_id
                    or component.plan_id.warehouse_ids[:1]
                )
                if warehouse:
                    vals.setdefault('warehouse_id', warehouse.id)
        records = super().create(vals_list)
        records._check_exclusive_lot()
        return records

    def write(self, vals):
        if {
            'lot_id', 'reserved_qty', 'warehouse_id', 'component_id', 'state'
        } & set(vals):
            self._check_engineering_unlocked()
        result = super().write(vals)
        self._check_exclusive_lot()
        return result

    def unlink(self):
        self._check_engineering_unlocked()
        return super().unlink()

    def action_release(self):
        self._check_engineering_unlocked()
        self.write({'state': 'released'})
        return True


    @api.model
    def _aps_auto_complete_pending_for_products(self, products, warehouse=False):
        """Complete pending APS reservations with newly available physical lots.

        Allocation priority:
        1. earliest required date;
        2. oldest plan;
        3. planning line/component id.

        This method is intentionally allowed to allocate after the OF exists,
        because material may arrive later from purchase or subcontracting.
        Manual edits remain blocked once the OF is generated.
        """
        products = products.filtered(lambda product: product.tracking != 'none')
        if not products:
            return self

        Component = self.env['mrp.planning.production.component'].sudo()
        domain = [
            ('product_id', 'in', products.ids),
            ('include_in_mo', '=', True),
            ('plan_id.state', 'in', ('calculated', 'approved')),
        ]
        components = Component.search(
            domain,
            order='planning_line_id, id',
        )
        if warehouse:
            components = components.filtered(
                lambda component:
                    (
                        component.planning_line_id.target_warehouse_id
                        or component.plan_id.warehouse_ids[:1]
                    ) == warehouse
            )

        components = components.sorted(
            key=lambda component: (
                component.planning_line_id.date_required
                or component.plan_id.date_end
                or fields.Datetime.now(),
                component.plan_id.create_date
                or fields.Datetime.now(),
                component.id,
            )
        )

        created = self
        for component in components:
            active = component.lot_reservation_ids.filtered(
                lambda reservation:
                    reservation.state in ('reserved', 'assigned')
            )
            target_qty = component._aps_effective_lot_target_qty()
            missing = max(
                target_qty - sum(active.mapped('reserved_qty')),
                0.0,
            )
            if missing <= 1e-6:
                continue

            existing_lots = set(active.mapped('lot_id').ids)
            for lot, free_qty, target_wh in component._aps_lot_free_rows():
                if lot.id in existing_lots or missing <= 1e-6:
                    continue
                qty = min(free_qty, missing)
                vals = {
                    'plan_id': component.plan_id.id,
                    'planning_line_id': component.planning_line_id.id,
                    'component_id': component.id,
                    'warehouse_id': target_wh.id,
                    'lot_id': lot.id,
                    'reserved_qty': qty,
                }
                production = component._aps_lot_production()
                if production:
                    vals.update({
                        'production_id': production.id,
                        'state': 'assigned',
                    })
                created |= self.with_context(
                    aps_allow_locked_lot_reservation_write=True
                ).create(vals)
                existing_lots.add(lot.id)
                missing -= qty
        return created


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _aps_reassign_received_material_to_productions(self):
        """Reserve a completed APS purchase on its intended root/sub-MOs only.

        Never call action_assign on every active APS MO in the warehouse:
        doing so allowed older MOs to grab stock bought for a newer plan.

        Target resolution order:
        1. native move_dest_ids created on PO confirmation;
        2. APS purchase-plan -> component -> consuming MO traceability.
        """
        Component = self.env[
            'mrp.planning.production.component'
        ].sudo()

        for picking in self.filtered(lambda p: p.state == 'done'):
            target_productions = self.env['mrp.production']
            received_products = self.env['product.product']

            done_moves = picking.move_ids.filtered(
                lambda move:
                    move.state == 'done'
                    and move.location_dest_id.usage == 'internal'
            )
            for move in done_moves:
                received_products |= move.product_id

                # Preferred/native chain.
                target_productions |= move.move_dest_ids.mapped(
                    'raw_material_production_id'
                ).filtered(
                    lambda mo:
                        mo
                        and mo.advanced_plan_id
                        and mo.state not in ('done', 'cancel')
                )

                # Fallback for POs created before this version.
                pol = getattr(move, 'purchase_line_id', False)
                if (
                    pol
                    and pol.planning_plan_line_id
                    and pol.source_manufacturing_plan_id
                ):
                    components = Component.search([
                        ('plan_id', '=',
                         pol.source_manufacturing_plan_id.id),
                        ('generated_purchase_plan_line_id',
                         '=', pol.planning_plan_line_id.id),
                        ('product_id', '=', move.product_id.id),
                        ('include_in_mo', '=', True),
                    ])
                    for component in components:
                        mo = component._aps_lot_production()
                        if mo and mo.state not in ('done', 'cancel'):
                            target_productions |= mo

            for production in target_productions:
                relevant_moves = production.move_raw_ids.filtered(
                    lambda move:
                        move.state not in ('done', 'cancel')
                        and move.product_id in received_products
                )
                if relevant_moves:
                    relevant_moves._action_assign()

                if (
                    production.aps_component_snapshot
                    and production.planning_plan_line_id
                ):
                    direct_components = production._aps_snapshot_components()
                    tracked = direct_components.filtered(
                        lambda component:
                            component.product_id.is_storable
                            and component.product_id.tracking != 'none'
                            and component.product_id in received_products
                            and component.include_in_mo
                    )
                    if tracked:
                        tracked.with_context(
                            aps_allow_locked_lot_sync=True
                        )._aps_sync_default_lot_reservations()

        return True

    def button_validate(self):
        result = super().button_validate()

        # Only act after the picking actually reached DONE. If Odoo returns an
        # immediate-transfer/backorder wizard, the later successful validation
        # call will execute this block.
        done_pickings = self.filtered(lambda picking: picking.state == 'done')
        if done_pickings:
            # First reserve the physical stock on existing APS MOs.
            done_pickings._aps_reassign_received_material_to_productions()

            # Then complete any remaining logical APS lot reservations from
            # the newly received physical lots.
            for picking in done_pickings:
                warehouse = picking.picking_type_id.warehouse_id
                products = picking.move_ids.mapped('product_id').filtered(
                    lambda product:
                        product.is_storable
                        and product.tracking != 'none'
                )
                if not products:
                    continue
                self.env[
                    'mrp.planning.component.lot.reservation'
                ].sudo()._aps_auto_complete_pending_for_products(
                    products,
                    warehouse=warehouse,
                )
        return result


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    def _exclude_requiring_lot(self):
        """APS rule for non-stockable manufacturing components.

        Odoo 19 can still enforce ``tracking != 'none'`` on a move line even
        when the product is non-stockable. APS intentionally treats such
        components as consumable without quant/lot reservation.

        Scope is deliberately narrow:
        - raw material move of a manufacturing order;
        - manufacturing order belongs to an APS plan;
        - product is non-stockable.

        Outside APS, native Odoo behavior is preserved.
        """
        self.ensure_one()
        move = self.move_id
        production = move.raw_material_production_id if move else False

        is_aps_production = bool(
            production
            and (
                production.advanced_plan_id
                or production.planning_plan_line_id
                or production.aps_component_snapshot
            )
        )
        if (
            is_aps_production
            and self.product_id
            and not self.product_id.is_storable
        ):
            # In Odoo 19, False means "tracked line without lot" and is
            # precisely what raises the native missing-lot error. Keep True
            # here; the actual bypass for APS non-stockable consumption is
            # implemented in _action_done below.
            return True

        return super()._exclude_requiring_lot()

    def _aps_is_nonstockable_tracked_consumption(self):
        """Tracked non-stockable raw material consumed by an APS MO."""
        self.ensure_one()
        move = self.move_id
        production = move.raw_material_production_id if move else False
        return bool(
            production
            and (
                production.advanced_plan_id
                or production.planning_plan_line_id
                or production.aps_component_snapshot
            )
            and self.product_id
            and not self.product_id.is_storable
            and self.product_id.tracking != 'none'
            and not self.lot_id
        )

    def _action_done(self):
        """Finish APS non-stockable consumption without inventing a lot.

        Odoo 19's native stock.move.line._action_done() validates tracking
        before it reaches _synchronize_quant(). For a non-stockable product,
        however, _synchronize_quant() itself is a no-op. APS therefore removes
        only these specific raw-material lines from the native lot-validation
        batch, lets Odoo process every normal/storable line normally, and then
        finalizes the skipped non-stockable move lines without touching quants.

        This is intentionally scoped to APS manufacturing raw materials.
        """
        aps_nonstockable = self.filtered(
            lambda line: line._aps_is_nonstockable_tracked_consumption()
        )
        normal_lines = self - aps_nonstockable

        # Odoo 19 stock.move.line._action_done() is a procedure and returns
        # None. Do not treat its return value as a recordset.
        super(StockMoveLine, normal_lines)._action_done()

        if aps_nonstockable:
            # Match the relevant tail of native _action_done for a product
            # whose stock synchronization is intentionally a no-op.
            aps_nonstockable._check_company()
            aps_nonstockable.write({
                'date': fields.Datetime.now(),
                'picked': True,
            })

        # Preserve the native Odoo 19 return contract: None.
        return None

    def _aps_source_warehouse(self, move):
        """Warehouse from which the move consumes stock."""
        location = move.location_id
        if not location or location.usage != 'internal':
            return self.env['stock.warehouse']

        warehouse = getattr(location, 'warehouse_id', False)
        if warehouse:
            return warehouse

        warehouses = self.env['stock.warehouse'].sudo().search([
            ('company_id', '=', move.company_id.id),
        ])
        Location = self.env['stock.location'].sudo()
        for candidate in warehouses:
            if Location.search_count([
                ('id', '=', location.id),
                ('id', 'child_of', candidate.view_location_id.id),
            ]):
                return candidate
        return self.env['stock.warehouse']

    def _aps_operation_lot_qty(self, move, lot, warehouse):
        """Quantity this production/picking currently reserves on the lot."""
        MoveLine = self.env['stock.move.line'].sudo()
        domain = [
            ('product_id', '=', move.product_id.id),
            ('lot_id', '=', lot.id),
            ('location_id', 'child_of', warehouse.view_location_id.id),
            ('move_id.state', 'not in', ('done', 'cancel')),
        ]
        production = move.raw_material_production_id
        if production:
            domain.append(
                ('move_id.raw_material_production_id', '=', production.id)
            )
        elif move.picking_id:
            domain.append(('move_id.picking_id', '=', move.picking_id.id))
        else:
            domain.append(('move_id', '=', move.id))

        total = 0.0
        for line in MoveLine.search(domain):
            qty = (
                getattr(line, 'quantity', 0.0)
                or getattr(line, 'qty_done', 0.0)
                or 0.0
            )
            uom = (
                getattr(line, 'product_uom_id', False)
                or getattr(line, 'product_uom', False)
            )
            if uom and uom != move.product_id.uom_id:
                qty = uom._compute_quantity(
                    qty, move.product_id.uom_id
                )
            total += qty
        return total

    def _aps_lot_physical_qty(self, move, lot, warehouse):
        locations = self.env['stock.location'].sudo().search([
            ('id', 'child_of', warehouse.view_location_id.id),
            ('usage', '=', 'internal'),
            ('company_id', 'in', [False, move.company_id.id]),
        ])
        quants = self.env['stock.quant'].sudo().search([
            ('product_id', '=', move.product_id.id),
            ('lot_id', '=', lot.id),
            ('location_id', 'in', locations.ids),
        ])
        return sum(quants.mapped('quantity'))

    def _aps_validate_reserved_lot(self, move=False, lot=False):
        """Protect only the APS-reserved QUANTITY, never the whole lot.

        A direct/non-APS MO or internal transfer may use the remainder of a lot
        while enough physical quantity remains outside active APS reservations.
        This prevents the previous false conflict where any APS reservation
        made the complete lot unusable.
        """
        self.ensure_one()
        move = move or self.move_id
        lot = lot or self.lot_id
        if not move or not lot:
            return True

        warehouse = self._aps_source_warehouse(move)
        if not warehouse:
            # Incoming/supplier/customer moves do not consume internal stock.
            return True

        Reservation = self.env[
            'mrp.planning.component.lot.reservation'
        ].sudo()
        active = Reservation.search([
            ('lot_id', '=', lot.id),
            ('warehouse_id', '=', warehouse.id),
            ('state', 'in', ('reserved', 'assigned')),
            ('plan_id.state', 'in', ('calculated', 'approved')),
        ])
        if not active:
            return True

        production = move.raw_material_production_id
        component = getattr(move, 'aps_planning_component_id', False)

        # APS component MOs must use one of the lots explicitly selected for
        # that component. This remains strict even though lots are shareable by
        # quantity across plans.
        if (
            production
            and component
            and component.product_id.is_storable
            and component.product_id.tracking != 'none'
        ):
            own_reservations = component.lot_reservation_ids.filtered(
                lambda reservation:
                    reservation.state in ('reserved', 'assigned')
            )
            own_lots = own_reservations.mapped('lot_id')

            # During MO confirmation Odoo may create/reserve a stock.move.line
            # BEFORE APS has materialized its logical lot reservation.  That is
            # not consumption yet, so it must not block creation of the root
            # MO or a native sub-MO.  The quantitative protection below still
            # prevents stealing quantities reserved by OTHER APS plans, and
            # mrp.production.action_confirm/action_assign synchronizes the
            # physical lot back into this component immediately afterwards.
            #
            # Strict "there must be a complete APS lot reservation" validation
            # is intentionally performed at production START/DONE, not here.
            if own_lots and lot not in own_lots:
                current_plan = production.advanced_plan_id
                same_plan_lot = active.filtered(
                    lambda reservation:
                        reservation.plan_id == current_plan
                        and reservation.component_id == component
                        and reservation.lot_id == lot
                ) if current_plan else Reservation

                if not same_plan_lot:
                    raise UserError(_(
                        'El lote %(lot)s no está asignado al componente '
                        '%(component)s de la OF %(mo)s.'
                    ) % {
                        'lot': lot.display_name,
                        'component': component.product_id.display_name,
                        'mo': production.display_name,
                    })

        # Reservations owned by this exact APS operation do not reduce the
        # quantity available to that same operation.
        #
        # IMPORTANT: ownership is fundamentally APS-level first. A native
        # child MO created by Odoo can consume material reserved earlier by the
        # SAME manufacturing APS even if the reservation still points
        # temporarily to the parent/root MO. Blocking that case produced the
        # repeated false conflict "Reservado por otros APS" although both
        # operations belonged to the same APS.
        owned = Reservation
        if production:
            owned |= active.filtered(
                lambda reservation:
                    reservation.production_id == production
            )

            current_plan = production.advanced_plan_id
            if current_plan:
                same_plan = active.filtered(
                    lambda reservation:
                        reservation.plan_id == current_plan
                )
                owned |= same_plan

                # Repair stale parent/root ownership when the current
                # operation is an APS child MO consuming the exact reserved
                # product/lot. This keeps traceability correct after allowing
                # same-plan consumption.
                repairable = same_plan.filtered(
                    lambda reservation:
                        reservation.product_id == move.product_id
                        and (
                            not component
                            or reservation.component_id == component
                            or reservation.production_id
                               == production.aps_parent_production_id
                        )
                )
                if repairable:
                    repairable.with_context(
                        aps_allow_locked_lot_reservation_write=True
                    ).write({
                        'production_id': production.id,
                        'state': 'assigned',
                    })

        if component:
            owned |= active.filtered(
                lambda reservation:
                    reservation.component_id == component
            )

        protected = active - owned
        protected_qty = sum(protected.mapped('reserved_qty'))
        physical_qty = self._aps_lot_physical_qty(
            move, lot, warehouse
        )
        operation_qty = self._aps_operation_lot_qty(
            move, lot, warehouse
        )
        usable_outside_other_aps = max(
            physical_qty - protected_qty, 0.0
        )

        if operation_qty > usable_outside_other_aps + 1e-6:
            owner = protected[:1] or active[:1]
            raise UserError(_(
                'Conflicto de cantidad reservada por APS.\n\n'
                'Producto: %(product)s\n'
                'Lote: %(lot)s\n'
                'Almacén: %(warehouse)s\n'
                'Cantidad física del lote: %(physical).4f\n'
                'Reservado por otras planificaciones APS: %(aps_reserved).4f\n'
                'Disponible fuera de esas reservas: %(free).4f\n'
                'Cantidad de esta operación: %(operation).4f\n'
                'Planificación que protege la cantidad: %(plan)s\n'
                'OF asociada a esa reserva: %(owner_mo)s\n'
                'Operación actual: %(current)s\n\n'
                'Puede utilizar este lote mientras la operación no invada '
                'la cantidad protegida por APS. Si necesita esa cantidad, '
                'libere o reasigne primero la reserva correspondiente.'
            ) % {
                'product': move.product_id.display_name,
                'lot': lot.display_name,
                'warehouse': warehouse.display_name,
                'physical': physical_qty,
                'aps_reserved': protected_qty,
                'free': usable_outside_other_aps,
                'operation': operation_qty,
                'plan': owner.plan_id.display_name if owner else '-',
                'owner_mo': (
                    owner.production_id.display_name
                    if owner and owner.production_id else '-'
                ),
                'current': (
                    production.display_name
                    if production
                    else (
                        move.picking_id.display_name
                        if move.picking_id
                        else move.display_name
                    )
                ),
            })
        return True

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for line in records.filtered(lambda row: row.move_id and row.lot_id):
            line._aps_validate_reserved_lot()
        return records

    def write(self, vals):
        result = super().write(vals)
        if {
            'lot_id', 'move_id', 'quantity', 'qty_done'
        } & set(vals):
            for line in self.filtered(
                lambda row: row.move_id and row.lot_id
            ):
                line._aps_validate_reserved_lot()
        return result
