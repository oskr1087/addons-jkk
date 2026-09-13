from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class MrpApsLotReassignmentWizard(models.TransientModel):
    _name = 'mrp.aps.lot.reassignment.wizard'
    _description = 'Reasignar lotes entre fabricaciones APS'

    production_id = fields.Many2one(
        'mrp.production', required=True, readonly=True,
    )
    component_id = fields.Many2one(
        'mrp.planning.production.component',
        required=True, readonly=True,
    )
    product_id = fields.Many2one(
        related='component_id.product_id', readonly=True,
    )
    required_qty = fields.Float(
        string='Necesario', related='component_id.planned_qty',
        readonly=True, digits=(16, 4),
    )
    reserved_qty = fields.Float(
        string='Reservado APS', related='component_id.reserved_lot_qty',
        readonly=True, digits=(16, 4),
    )
    pending_qty = fields.Float(
        string='Pendiente de lote', related='component_id.pending_lot_qty',
        readonly=True, digits=(16, 4),
    )
    line_ids = fields.One2many(
        'mrp.aps.lot.reassignment.wizard.line',
        'wizard_id', string='Lotes candidatos',
    )

    @api.model
    def default_get(self, field_list):
        vals = super().default_get(field_list)
        production = self.env['mrp.production'].browse(
            self.env.context.get('default_production_id')
            or self.env.context.get('active_id')
        ).exists()
        component = self.env['mrp.planning.production.component'].browse(
            self.env.context.get('default_component_id')
        ).exists()
        if production and component:
            vals.update({
                'production_id': production.id,
                'component_id': component.id,
            })
        return vals

    def _candidate_lines(self):
        self.ensure_one()
        component = self.component_id
        production = self.production_id
        component._aps_validate_lot_reassignment_allowed()

        warehouse = (
            component.planning_line_id.target_warehouse_id
            or component.plan_id.warehouse_ids[:1]
        )
        if not warehouse:
            return []

        Reservation = self.env[
            'mrp.planning.component.lot.reservation'
        ].sudo()
        reservations = Reservation.search([
            ('product_id', '=', component.product_id.id),
            ('warehouse_id', '=', warehouse.id),
            ('state', 'in', ('reserved', 'assigned')),
            ('plan_id.state', 'in', ('calculated', 'approved')),
        ])

        # Physical/free candidates already reconcile Odoo + APS reservations.
        free_by_lot = {
            lot.id: (lot, qty)
            for lot, qty, wh in component._aps_lot_free_rows()
            if wh == warehouse and qty > 1e-6
        }
        lot_ids = set(free_by_lot)
        lot_ids.update(reservations.mapped('lot_id').ids)

        result = []
        for lot_id in lot_ids:
            lot = self.env['stock.lot'].browse(lot_id)
            own = reservations.filtered(
                lambda r: r.component_id == component and r.lot_id == lot
            )
            donors = reservations.filtered(
                lambda r: r.component_id != component and r.lot_id == lot
            )
            free_qty = free_by_lot.get(lot_id, (lot, 0.0))[1]
            donor_qty = 0.0
            donor_names = []
            for donor in donors:
                donor_component = donor.component_id
                donor_production = donor.production_id or donor_component._aps_lot_production()
                if not donor_production:
                    continue
                if donor_production.state in ('done', 'cancel'):
                    continue
                if donor_component._aps_consumed_qty_for_lot(
                    donor.lot_id, donor_production
                ) > 1e-6:
                    continue
                donor_qty += donor.reserved_qty
                donor_names.append(donor_production.display_name)
            result.append((0, 0, {
                'lot_id': lot.id,
                'current_qty': sum(own.mapped('reserved_qty')),
                'free_qty': free_qty,
                'reassignable_qty': donor_qty,
                'source_production_names': ', '.join(sorted(set(donor_names))),
            }))
        return result

    def action_load_candidates(self):
        self.ensure_one()
        self.line_ids = [(5, 0, 0)] + self._candidate_lines()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reasignar lotes'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_apply(self):
        self.ensure_one()
        selected = self.line_ids.filtered(lambda line: line.qty_to_assign > 1e-6)
        if not selected:
            raise UserError(_('Ingrese una cantidad a asignar.'))

        target = self.component_id
        target._aps_validate_lot_reassignment_allowed()
        target_qty = target._aps_effective_lot_target_qty()
        total_requested = sum(selected.mapped('qty_to_assign'))
        if total_requested > target_qty + 1e-6:
            raise ValidationError(_(
                'La asignación solicitada (%.4f) supera la necesidad del '
                'componente (%.4f).'
            ) % (total_requested, target_qty))

        Reservation = self.env[
            'mrp.planning.component.lot.reservation'
        ].sudo()
        touched_productions = self.production_id

        # Replace the target allocation intentionally. Existing target
        # reservations become released; history is preserved.
        old_target = target.lot_reservation_ids.filtered(
            lambda r: r.state in ('reserved', 'assigned')
        )
        if old_target:
            old_target.with_context(
                aps_allow_locked_lot_reservation_write=True
            ).write({'state': 'released', 'production_id': False})

        for line in selected:
            needed = line.qty_to_assign
            free = min(line.free_qty, needed)
            if free > 1e-6:
                Reservation.with_context(
                    aps_allow_locked_lot_reservation_write=True
                ).create({
                    'plan_id': target.plan_id.id,
                    'planning_line_id': target.planning_line_id.id,
                    'component_id': target.id,
                    'warehouse_id': line.warehouse_id.id,
                    'lot_id': line.lot_id.id,
                    'reserved_qty': free,
                    'production_id': self.production_id.id,
                    'state': 'assigned',
                })
                needed -= free

            if needed > 1e-6:
                donors = Reservation.search([
                    ('lot_id', '=', line.lot_id.id),
                    ('warehouse_id', '=', line.warehouse_id.id),
                    ('component_id', '!=', target.id),
                    ('state', 'in', ('reserved', 'assigned')),
                    ('plan_id.state', 'in', ('calculated', 'approved')),
                ], order='planning_line_id, id')
                for donor in donors:
                    if needed <= 1e-6:
                        break
                    donor_component = donor.component_id
                    donor_production = (
                        donor.production_id
                        or donor_component._aps_lot_production()
                    )
                    if (
                        not donor_production
                        or donor_production.state in ('done', 'cancel')
                        or donor_component._aps_consumed_qty_for_lot(
                            donor.lot_id, donor_production
                        ) > 1e-6
                    ):
                        continue
                    take = min(donor.reserved_qty, needed)
                    remaining = donor.reserved_qty - take
                    vals = {'reserved_qty': remaining} if remaining > 1e-6 else {
                        'state': 'released',
                        'production_id': False,
                    }
                    donor.with_context(
                        aps_allow_locked_lot_reservation_write=True
                    ).write(vals)
                    Reservation.with_context(
                        aps_allow_locked_lot_reservation_write=True
                    ).create({
                        'plan_id': target.plan_id.id,
                        'planning_line_id': target.planning_line_id.id,
                        'component_id': target.id,
                        'warehouse_id': line.warehouse_id.id,
                        'lot_id': line.lot_id.id,
                        'reserved_qty': take,
                        'production_id': self.production_id.id,
                        'state': 'assigned',
                    })
                    touched_productions |= donor_production
                    donor_production.message_post(body=_(
                        'Reserva APS reasignada: %(qty).4f de %(product)s, '
                        'lote %(lot)s, hacia %(target)s.'
                    ) % {
                        'qty': take,
                        'product': target.product_id.display_name,
                        'lot': line.lot_id.display_name,
                        'target': self.production_id.display_name,
                    })
                    needed -= take
            if needed > 1e-6:
                raise UserError(_(
                    'No existe cantidad suficiente libre o reasignable del '
                    'lote %(lot)s. Faltan %(qty).4f.'
                ) % {'lot': line.lot_id.display_name, 'qty': needed})

        # Reconcile native Odoo reservations without writing stock.quant.
        # Only raw moves of the affected component/product are unreserved and
        # reassigned; no other picking/MO is touched.
        for production in touched_productions.exists():
            moves = production.move_raw_ids.filtered(
                lambda m:
                    m.state not in ('done', 'cancel')
                    and m.product_id == target.product_id
            )
            if moves:
                moves._do_unreserve()
                moves._action_assign()

        self.production_id.message_post(body=_(
            'Lotes APS reasignados para %(product)s. Cantidad seleccionada: '
            '%(qty).4f.'
        ) % {
            'product': target.product_id.display_name,
            'qty': total_requested,
        })
        return {'type': 'ir.actions.act_window_close'}


class MrpApsLotReassignmentWizardLine(models.TransientModel):
    _name = 'mrp.aps.lot.reassignment.wizard.line'
    _description = 'Lote candidato para reasignación APS'
    _order = 'lot_id'

    wizard_id = fields.Many2one(
        'mrp.aps.lot.reassignment.wizard',
        required=True, ondelete='cascade',
    )
    warehouse_id = fields.Many2one(
        related='wizard_id.component_id.planning_line_id.target_warehouse_id',
        readonly=True,
    )
    lot_id = fields.Many2one('stock.lot', required=True, readonly=True)
    current_qty = fields.Float(
        string='Esta OF', readonly=True, digits=(16, 4),
    )
    free_qty = fields.Float(
        string='Libre', readonly=True, digits=(16, 4),
    )
    reassignable_qty = fields.Float(
        string='En otras OF', readonly=True, digits=(16, 4),
    )
    source_production_names = fields.Char(
        string='OF origen', readonly=True,
    )
    qty_to_assign = fields.Float(
        string='Asignar', digits=(16, 4),
    )

    @api.constrains('qty_to_assign')
    def _check_qty(self):
        for line in self:
            if line.qty_to_assign < -1e-6:
                raise ValidationError(_('La cantidad no puede ser negativa.'))
            maximum = line.free_qty + line.reassignable_qty
            if line.qty_to_assign > maximum + 1e-6:
                raise ValidationError(_(
                    'Solo hay %.4f disponible/reasignable para el lote %s.'
                ) % (maximum, line.lot_id.display_name))
