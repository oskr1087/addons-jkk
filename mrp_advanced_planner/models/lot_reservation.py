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

    @api.constrains('lot_id', 'state', 'component_id', 'reserved_qty')
    def _check_exclusive_lot(self):
        """Validate capacity instead of making a whole lot exclusive.

        For lot-tracked products, the same physical lot can be split among
        several APS demands while quantity remains. Serial-tracked products
        naturally remain effectively exclusive because their available qty is 1.
        """
        Quant = self.env['stock.quant'].sudo()
        for reservation in self.filtered(
            lambda r: r.lot_id and r.state in ('reserved', 'assigned')
        ):
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
            physical_qty = sum(quants.mapped('quantity'))

            active = self.search([
                ('lot_id', '=', reservation.lot_id.id),
                ('warehouse_id', '=', reservation.warehouse_id.id),
                ('state', 'in', ('reserved', 'assigned')),
                ('plan_id.state', 'in', ('calculated', 'approved')),
            ])
            aps_reserved_qty = sum(active.mapped('reserved_qty'))

            if aps_reserved_qty > physical_qty + 1e-6:
                others = active - reservation
                owner = others[:1]
                raise ValidationError(_(
                    'No hay cantidad suficiente del lote %(lot)s.\n\n'
                    'Producto: %(product)s\n'
                    'Almacén: %(warehouse)s\n'
                    'Cantidad física del lote: %(physical).2f\n'
                    'Reservado APS total: %(reserved).2f\n'
                    'Cantidad solicitada: %(requested).2f\n'
                    'Otra planificación: %(plan)s\n'
                    'Componente de la otra planificación: %(other_product)s\n\n'
                    'Use "Reasignar lotes" o libere/revise la reserva anterior.'
                ) % {
                    'lot': reservation.lot_id.display_name,
                    'product': reservation.product_id.display_name,
                    'warehouse': reservation.warehouse_id.display_name,
                    'physical': physical_qty,
                    'reserved': aps_reserved_qty,
                    'requested': reservation.reserved_qty,
                    'plan': owner.plan_id.display_name if owner else '-',
                    'other_product': (
                        owner.component_id.product_id.display_name
                        if owner else '-'
                    ),
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
            target_qty = max(
                component.effective_required_qty or component.planned_qty,
                0.0,
            )
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
                if component.planning_line_id.created_production_id:
                    vals.update({
                        'production_id':
                            component.planning_line_id.created_production_id.id,
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

    def button_validate(self):
        result = super().button_validate()

        # After a real receipt (normal purchase or subcontracting), newly
        # received lot stock can satisfy APS reservations that were pending.
        for picking in self:
            if picking.state != 'done':
                continue
            warehouse = picking.picking_type_id.warehouse_id
            products = picking.move_ids.mapped('product_id').filtered(
                lambda product: product.tracking != 'none'
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

    def _aps_validate_reserved_lot(self, move=False, lot=False):
        move = move or self.move_id
        lot = lot or self.lot_id
        if not move or not lot:
            return True
        production = move.raw_material_production_id
        if not production:
            return True

        Reservation = self.env[
            'mrp.planning.component.lot.reservation'
        ].sudo()
        active = Reservation.search([
            ('lot_id', '=', lot.id),
            ('state', 'in', ('reserved', 'assigned')),
        ])
        if not active:
            return True

        # A lot reserved for another APS demand may not be consumed by this MO.
        allowed = active.filtered(
            lambda reservation:
                reservation.production_id == production
                or (
                    production.advanced_plan_id
                    and reservation.plan_id == production.advanced_plan_id
                )
        )
        if not allowed:
            owner = active[:1]
            raise UserError(_(
                'Conflicto de reserva de lote.\n\n'
                'Producto: %(product)s\n'
                'Lote: %(lot)s\n'
                'Cantidad reservada APS: %(qty).2f\n'
                'Estado de la reserva: %(reservation_state)s\n'
                'Reservado por planificación: %(plan)s\n'
                'Producto/componente origen: %(owner_product)s\n'
                'OF asociada a la reserva: %(owner_mo)s\n'
                'OF actual: %(current_mo)s\n\n'
                'Este lote tiene una reserva APS activa para otra demanda. '
                'Revise la cantidad disponible o utilice "Reasignar lotes".'
            ) % {
                'product': move.product_id.display_name,
                'lot': lot.display_name,
                'qty': owner.reserved_qty,
                'reservation_state': dict(
                    owner._fields['state'].selection
                ).get(owner.state, owner.state),
                'plan': owner.plan_id.display_name,
                'owner_product': owner.component_id.product_id.display_name,
                'owner_mo': (
                    owner.production_id.display_name
                    if owner.production_id else '-'
                ),
                'current_mo': production.display_name,
            })

        # For an APS raw move with a specific component, enforce its own lots.
        component = getattr(move, 'aps_planning_component_id', False)
        if component and component.product_id.tracking != 'none':
            component_lots = component.lot_reservation_ids.filtered(
                lambda reservation:
                    reservation.state in ('reserved', 'assigned')
            ).mapped('lot_id')
            if not component_lots:
                raise UserError(_(
                    'El componente %s requiere lote, pero APS todavía no tiene '
                    'ningún lote reservado. Reciba/disponga material y complete '
                    'la reserva antes de consumir.'
                ) % component.product_id.display_name)
            if lot not in component_lots:
                raise UserError(_(
                    'El lote %s no está reservado para el componente %s de '
                    'esta planificación APS.'
                ) % (lot.display_name, component.product_id.display_name))
        return True

    @api.model_create_multi
    def create(self, vals_list):
        Move = self.env['stock.move']
        Lot = self.env['stock.lot']
        for vals in vals_list:
            move = Move.browse(vals.get('move_id')).exists()
            lot = Lot.browse(vals.get('lot_id')).exists()
            if move and lot:
                self._aps_validate_reserved_lot(move=move, lot=lot)
        return super().create(vals_list)

    def write(self, vals):
        result = super().write(vals)
        if 'lot_id' in vals or 'move_id' in vals:
            for line in self:
                line._aps_validate_reserved_lot()
        return result
