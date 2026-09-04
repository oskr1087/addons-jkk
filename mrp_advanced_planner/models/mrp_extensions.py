from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    advanced_plan_id = fields.Many2one('mrp.planning.plan', string='Planificación de origen', index=True, copy=False, readonly=True)
    planning_plan_line_id = fields.Many2one('mrp.planning.plan.line', string='Línea de planificación', index=True, copy=False, readonly=True)
    planning_sale_line_id = fields.Many2one('sale.order.line', string='Línea de venta origen', index=True, copy=False, readonly=True)
    planning_sale_line_ids = fields.Many2many(
        related='planning_plan_line_id.sale_line_ids',
        string='Líneas de venta origen',
        readonly=True,
    )
    planning_sale_order_ids = fields.Many2many(
        related='planning_plan_line_id.source_sale_order_ids',
        string='Pedidos de venta origen',
        readonly=True,
    )
    planning_production_proposal_id = fields.Many2one('mrp.planning.production.proposal', string='Propuesta de planificación', index=True, copy=False, readonly=True)
    aps_component_snapshot = fields.Boolean(
        string='Componentes congelados por APS', copy=False, readonly=True,
        help='La OF usa exclusivamente el snapshot de componentes del Planificador APS.',
    )
    aps_planning_component_id = fields.Many2one(
        'mrp.planning.production.component',
        string='Componente APS origen',
        copy=False,
        readonly=True,
        ondelete='set null',
        help='Cuando la OF corresponde a un subproducto, identifica el nodo del árbol APS que la originó.',
    )

    component_purchase_count = fields.Integer(
        string='Compras de componentes',
        compute='_compute_component_purchase_count',
    )
    planning_sale_order_count = fields.Integer(
        string='Ventas origen',
        compute='_compute_planning_sale_order_count',
        compute_sudo=True,
    )

    @api.depends('planning_plan_line_id.sale_line_ids.order_id')
    def _compute_planning_sale_order_count(self):
        for production in self:
            production.planning_sale_order_count = len(
                production.sudo().planning_sale_order_ids
            )

    def action_open_planning_sale_orders(self):
        self.ensure_one()
        orders = self.planning_sale_order_ids
        if not orders:
            return False
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Pedidos de venta origen'),
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', orders.ids)],
            'target': 'current',
        }
        if len(orders) == 1:
            action.update({
                'res_id': orders.id,
                'view_mode': 'form',
                'views': [(False, 'form')],
            })
        return action


    def _aps_snapshot_components(self):
        self.ensure_one()
        if not self.aps_component_snapshot or not self.planning_plan_line_id:
            return self.env['mrp.planning.production.component']
        if self.aps_planning_component_id:
            return self.aps_planning_component_id.child_line_ids.filtered(
                lambda c: c.include_in_mo and c.planned_qty > 1e-9
            )
        return self.planning_plan_line_id.production_component_ids.filtered(
            lambda c: not c.parent_line_id
            and c.include_in_mo
            and c.planned_qty > 1e-9
        )

    def _aps_raw_move_values(self):
        """Build raw move vals with Odoo 19's complete native structure.

        Odoo 19's ``_compute_move_raw_ids`` expects every values dictionary to
        contain at least ``bom_line_id`` and downstream stock/MRP code expects
        the rest of the keys prepared by ``_get_move_raw_values``. Therefore
        APS delegates the base dictionary to Odoo and only replaces the
        engineering source with the frozen planner snapshot.
        """
        self.ensure_one()
        planning_line = self.planning_plan_line_id
        if not self.aps_component_snapshot or not planning_line:
            return False

        components = self._aps_snapshot_components()
        if self.aps_planning_component_id:
            base_qty = (
                self.aps_planning_component_id.planned_qty
                or self.product_qty
                or 1.0
            )
        else:
            base_qty = (
                planning_line.planner_production_qty
                or self.product_qty
                or 1.0
            )

        factor = (self.product_qty or 0.0) / base_qty if base_qty else 1.0
        values = []
        for component in components:
            qty = component.planned_qty * factor
            if qty <= 1e-9:
                continue

            source_line = component.source_bom_line_id
            # Keep a native BoM-line relation only when this snapshot line is
            # still the exact original engineering component of this MO's BoM.
            # Replaced/manual components are intentionally manual raw moves.
            # Only a completely untouched engineering line keeps the native
            # BoM-line relation.  Any intentional APS change (quantity change,
            # product replacement or manual line) is a frozen/manual component
            # of the APS snapshot.  Keeping bom_line_id on a modified quantity
            # makes Odoo compare it again with the original BoM during
            # production validation and incorrectly report a consumption
            # deviation even though the planner change is intentional.
            native_bom_line = (
                source_line
                if source_line
                and component.change_type == 'original'
                and source_line.bom_id == self.bom_id
                and source_line.product_id == component.product_id
                else self.env['mrp.bom.line']
            )
            operation_id = (
                source_line.operation_id.id
                if source_line and source_line.operation_id
                else False
            )

            move_vals = self._get_move_raw_values(
                component.product_id,
                qty,
                component.product_uom_id,
                operation_id=operation_id,
                bom_line=native_bom_line,
            )
            # These two fields belong to the APS extension, not Odoo base.
            move_vals.update({
                'planning_plan_line_id': planning_line.id,
                'aps_planning_component_id': component.id,
            })
            values.append(move_vals)
        return values

    def _get_moves_raw_values(self):
        """Use the frozen APS snapshot for APS MOs and native BoM otherwise."""
        self.ensure_one()
        snapshot = self._aps_raw_move_values()
        if snapshot is not False:
            return snapshot
        return super()._get_moves_raw_values()

    def _aps_sync_raw_moves(self):
        """Rebuild draft raw moves exclusively from the APS snapshot.

        Native ``move_raw_ids`` computation is explicitly skipped while this
        method runs. This prevents Odoo from reloading the original BoM after
        the user substituted, omitted or manually added components.
        """
        self.ensure_one()
        if not self.aps_component_snapshot:
            return self.move_raw_ids

        values = self._aps_raw_move_values()
        if values is False:
            return self.move_raw_ids

        draft_moves = self.move_raw_ids.filtered(lambda move: move.state == 'draft')
        if draft_moves:
            draft_moves.unlink()

        Move = self.env['stock.move'].with_context(skip_compute_move_raw_ids=True)
        created = Move
        for vals in values:
            created |= Move.create(vals)
        return created

    def action_confirm(self):
        """Confirm APS MOs strictly from planner snapshot raw moves.

        Standard MOs keep Odoo's native behavior. APS MOs bypass the native
        BoM-driven raw-move recomputation and rebuild their components from the
        planner snapshot immediately before confirmation.
        """
        aps = self.filtered(
            lambda mo: mo.aps_component_snapshot and mo.planning_plan_line_id
        )
        regular = self - aps
        result = True

        if regular:
            result = super(MrpProduction, regular).action_confirm()

        for mo in aps:
            snapshot = mo._aps_snapshot_components()
            if not snapshot:
                raise UserError(
                    _('La orden APS %s no tiene componentes activos en el snapshot. '
                      'Revise la pestaña Componentes de la OF antes de confirmar.')
                    % mo.display_name
                )

            aps_mo = mo.with_context(skip_compute_move_raw_ids=True)
            aps_mo._aps_sync_raw_moves()

            result = super(
                MrpProduction,
                aps_mo,
            ).action_confirm()

            expected_products = set(snapshot.mapped('product_id').ids)
            actual_moves = mo.move_raw_ids.filtered(
                lambda move: move.state != 'cancel'
            )
            actual_products = set(actual_moves.mapped('product_id').ids)
            if actual_products != expected_products:
                raise UserError(
                    _('La OF APS %s generó componentes distintos al snapshot. '
                      'Esperados: %s. Generados: %s.')
                    % (
                        mo.display_name,
                        ', '.join(snapshot.mapped('product_id.display_name')),
                        ', '.join(
                            mo.move_raw_ids.filtered(
                                lambda move: move.state != 'cancel'
                            ).mapped('product_id.display_name')
                        ),
                    )
                )

            # Quantity-level integrity: every active snapshot row must produce a
            # raw move with a positive quantity. This catches small four-decimal
            # BoM factors that previously disappeared as 0.00.
            for component in snapshot:
                expected_qty = component.planned_qty * (
                    (mo.product_qty or 0.0)
                    / (
                        (
                            mo.aps_planning_component_id.planned_qty
                            if mo.aps_planning_component_id
                            else mo.planning_plan_line_id.planner_production_qty
                        )
                        or mo.product_qty
                        or 1.0
                    )
                )
                component_moves = actual_moves.filtered(
                    lambda move:
                        move.aps_planning_component_id == component
                )
                actual_qty = sum(component_moves.mapped('product_uom_qty'))
                if expected_qty > 1e-9 and actual_qty <= 1e-9:
                    raise UserError(_(
                        'La OF APS %(mo)s quedó incompleta: el componente '
                        '%(component)s requiere %(qty).4f %(uom)s y no se '
                        'generó en los movimientos de materia prima.'
                    ) % {
                        'mo': mo.display_name,
                        'component': component.product_id.display_name,
                        'qty': expected_qty,
                        'uom': component.product_uom_id.display_name,
                    })
        return result


    def _compute_component_purchase_count(self):
        Purchase = self.env['purchase.order']
        for production in self:
            production.component_purchase_count = Purchase.search_count([
                ('mrp_production_id', '=', production.id)
            ])

    def action_open_component_purchases(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Compras de componentes - %s') % self.display_name,
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('mrp_production_id', '=', self.id)],
            'context': {'default_mrp_production_id': self.id},
        }

    def action_open_advanced_plan(self):
        self.ensure_one()
        if not self.advanced_plan_id:
            return False
        return {
            'type': 'ir.actions.act_window', 'name': _('Planificación de origen'),
            'res_model': 'mrp.planning.plan', 'view_mode': 'form', 'views': [(False, 'form')],
            'res_id': self.advanced_plan_id.id, 'target': 'current',
        }


    def _aps_validate_lot_reservation_coverage(self):
        for production in self.filtered(
            lambda mo:
                mo.aps_component_snapshot and mo.planning_plan_line_id
        ):
            components = production._aps_snapshot_components().filtered(
                lambda component:
                    component.product_id.tracking != 'none'
                    and component.include_in_mo
                    and component.planned_qty > 1e-9
            )
            incomplete = components.filtered(
                lambda component:
                    not component._aps_has_complete_lot_reservation()
            )
            if incomplete:
                details = []
                for component in incomplete:
                    details.append(
                        '%s: requerido %.2f / reservado %.2f / pendiente %.2f'
                        % (
                            component.product_id.display_name,
                            component.effective_required_qty
                            or component.planned_qty,
                            component.reserved_lot_qty,
                            component.pending_lot_qty,
                        )
                    )
                raise UserError(_(
                    'No puede finalizar la OF %s porque existen componentes '
                    'con seguimiento por lote sin reserva completa:\n- %s\n\n'
                    'Reciba o disponga el material y complete la reserva de '
                    'lotes antes de finalizar la producción.'
                ) % (
                    production.display_name,
                    '\n- '.join(details),
                ))
        return True

    def button_mark_done(self):
        self._aps_validate_lot_reservation_coverage()
        return super().button_mark_done()

    def write(self, vals):
        result = super().write(vals)
        if 'state' in vals:
            Reservation = self.env[
                'mrp.planning.component.lot.reservation'
            ].sudo()
            for production in self:
                reservations = Reservation.search([
                    ('production_id', '=', production.id),
                    ('state', 'in', ('reserved', 'assigned')),
                ])
                if not reservations:
                    continue
                if production.state == 'cancel':
                    reservations.with_context(
                        aps_allow_locked_lot_reservation_write=True
                    ).write({
                        'state': 'released',
                        'production_id': False,
                    })
                elif production.state == 'done':
                    reservations.with_context(
                        aps_allow_locked_lot_reservation_write=True
                    ).write({'state': 'consumed'})
        return result


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    advanced_plan_id = fields.Many2one('mrp.planning.plan', string='Planificación de origen', index=True, copy=False, readonly=True)
    planning_plan_line_ids = fields.Many2many(
        'mrp.planning.plan.line',
        string='Líneas de planificación',
        compute='_compute_aps_traceability',
        compute_sudo=True,
        readonly=True,
    )
    planning_sale_line_ids = fields.Many2many(
        'sale.order.line',
        string='Líneas de venta origen',
        compute='_compute_aps_traceability',
        compute_sudo=True,
        readonly=True,
    )
    planning_sale_order_ids = fields.Many2many(
        'sale.order',
        string='Pedidos de venta origen',
        compute='_compute_aps_traceability',
        compute_sudo=True,
        readonly=True,
    )
    mrp_production_id = fields.Many2one(
        'mrp.production',
        string='Orden de fabricación origen',
        index=True,
        copy=False,
        readonly=True,
    )
    planning_sale_order_count = fields.Integer(
        string='Ventas origen',
        compute='_compute_aps_traceability',
        compute_sudo=True,
    )
    source_manufacturing_plan_id = fields.Many2one(
        related='advanced_plan_id.source_manufacturing_plan_id',
        string='Plan fabricación origen',
        readonly=True,
    )

    @api.depends(
        'order_line.planning_plan_line_id',
        'order_line.planning_plan_line_id.sale_line_ids',
    )
    def _compute_aps_traceability(self):
        for order in self:
            plan_lines = order.sudo().order_line.mapped('planning_plan_line_id')
            order.planning_plan_line_ids = plan_lines
            order.planning_sale_line_ids = plan_lines.mapped('sale_line_ids')
            order.planning_sale_order_ids = plan_lines.mapped(
                'source_sale_order_ids'
            )
            order.planning_sale_order_count = len(
                order.planning_sale_order_ids
            )

    def action_open_planning_sale_orders(self):
        self.ensure_one()
        orders = self.planning_sale_order_ids
        if not orders:
            return False
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Pedidos de venta origen'),
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', orders.ids)],
            'target': 'current',
        }
        if len(orders) == 1:
            action.update({
                'res_id': orders.id,
                'view_mode': 'form',
                'views': [(False, 'form')],
            })
        return action

    def action_open_advanced_plan(self):
        self.ensure_one()
        if not self.advanced_plan_id:
            return False
        return {
            'type': 'ir.actions.act_window', 'name': _('Planificación de origen'),
            'res_model': 'mrp.planning.plan', 'res_id': self.advanced_plan_id.id,
            'view_mode': 'form', 'views': [(False, 'form')], 'target': 'current',
        }


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    planning_plan_line_id = fields.Many2one('mrp.planning.plan.line', string='Línea de planificación', index=True, copy=False, readonly=True)
    planning_plan_id = fields.Many2one(
        related='planning_plan_line_id.plan_id',
        string='Planificación APS',
        readonly=True,
    )
    source_manufacturing_plan_id = fields.Many2one(
        related='planning_plan_line_id.plan_id.source_manufacturing_plan_id',
        string='Plan fabricación origen',
        readonly=True,
    )
    planning_sale_line_ids = fields.Many2many(
        related='planning_plan_line_id.sale_line_ids',
        string='Líneas de venta origen',
        readonly=True,
    )
    planning_sale_order_ids = fields.Many2many(
        related='planning_plan_line_id.source_sale_order_ids',
        string='Pedidos de venta origen',
        readonly=True,
    )
    mrp_component_move_id = fields.Many2one(
        'stock.move',
        string='Componente de OF',
        index=True,
        copy=False,
        readonly=True,
    )


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    advanced_plan_id = fields.Many2one('mrp.planning.plan', string='Planificación de origen', index=True, copy=False, readonly=True)
    planning_plan_line_ids = fields.Many2many(
        'mrp.planning.plan.line',
        string='Líneas de planificación',
        compute='_compute_aps_traceability',
        compute_sudo=True,
        readonly=True,
    )
    planning_sale_line_ids = fields.Many2many(
        'sale.order.line',
        string='Líneas de venta origen',
        compute='_compute_aps_traceability',
        compute_sudo=True,
        readonly=True,
    )
    planning_sale_order_ids = fields.Many2many(
        'sale.order',
        string='Pedidos de venta origen',
        compute='_compute_aps_traceability',
        compute_sudo=True,
        readonly=True,
    )

    @api.depends(
        'move_ids.planning_plan_line_id',
        'move_ids.planning_plan_line_id.sale_line_ids',
    )
    def _compute_aps_traceability(self):
        for picking in self:
            plan_lines = picking.sudo().move_ids.mapped('planning_plan_line_id')
            picking.planning_plan_line_ids = plan_lines
            picking.planning_sale_line_ids = plan_lines.mapped('sale_line_ids')
            picking.planning_sale_order_ids = plan_lines.mapped(
                'source_sale_order_ids'
            )

    def action_open_advanced_plan(self):
        self.ensure_one()
        if not self.advanced_plan_id:
            return False
        return {
            'type': 'ir.actions.act_window', 'name': _('Planificación de origen'),
            'res_model': 'mrp.planning.plan', 'res_id': self.advanced_plan_id.id,
            'view_mode': 'form', 'views': [(False, 'form')], 'target': 'current',
        }


class StockMove(models.Model):
    _inherit = 'stock.move'

    planning_plan_line_id = fields.Many2one('mrp.planning.plan.line', string='Línea de planificación', index=True, copy=False, readonly=True)
    aps_planning_component_id = fields.Many2one(
        'mrp.planning.production.component',
        string='Componente APS',
        index=True,
        copy=False,
        readonly=True,
        ondelete='set null',
    )
    planning_purchase_vendor_id = fields.Many2one(
        'res.partner',
        string='Proveedor compra',
        domain="[('supplier_rank', '>', 0)]",
        help='Proveedor que se utilizará para comprar este componente. Puede ser cualquier proveedor activo de Odoo.',
    )
    planning_purchase_qty = fields.Float(
        string='Cantidad a comprar (legacy)',
        help='Campo conservado únicamente por compatibilidad con versiones anteriores.',
     digits=(16, 4))
    planning_can_purchase_component = fields.Boolean(
        string='Puede comprar componente',
        compute='_compute_planning_can_purchase_component',
    )
    planning_purchase_order_line_id = fields.Many2one(
        'purchase.order.line',
        string='Compra generada',
        copy=False,
        readonly=True,
    )

    def _planning_draft_purchase_supply(self, warehouse, to_date):
        """RFQ / to-approve supply is not yet represented by stock moves."""
        self.ensure_one()
        if not warehouse:
            return 0.0
        lines = self.env['purchase.order.line'].search([
            ('company_id', '=', self.company_id.id),
            ('product_id', '=', self.product_id.id),
            ('order_id.state', 'in', ('draft', 'sent', 'to approve')),
            ('order_id.picking_type_id.warehouse_id', '=', warehouse.id),
            '|',
            ('date_planned', '=', False),
            ('date_planned', '<=', to_date),
        ])
        total = 0.0
        for line in lines:
            pending = max((line.product_qty or 0.0) - (line.qty_received or 0.0), 0.0)
            total += line.product_uom_id._compute_quantity(
                pending, self.product_id.uom_id
            )
        return total

    def _planning_forecast_shortage(self):
        """Return component shortage using forecast, safe for onchange/new records."""
        self.ensure_one()

        production = self.raw_material_production_id
        product = self.product_id

        if not production or not product:
            return 0.0
        if production.state in ('done', 'cancel'):
            return 0.0

        warehouse = production.picking_type_id.warehouse_id
        if not warehouse and self.location_id:
            warehouse = self.location_id.warehouse_id
        if not warehouse:
            return 0.0

        to_date = (
            self.date
            or production.date_start
            or production.date_deadline
            or fields.Datetime.now()
        )

        product_ctx = product.with_company(production.company_id).with_context(
            warehouse_id=warehouse.id,
            to_date=to_date,
            allowed_company_ids=[production.company_id.id],
            company_owned=True,
        )

        forecast = float(product_ctx.virtual_available or 0.0)

        if self.state == 'draft' and self.product_uom and self.product_uom_qty:
            required_product_uom = self.product_uom._compute_quantity(
                self.product_uom_qty,
                product.uom_id,
            )
            forecast -= required_product_uom

        forecast += self._planning_draft_purchase_supply(warehouse, to_date)

        shortage_product_uom = max(-forecast, 0.0)
        if not self.product_uom:
            return shortage_product_uom

        return product.uom_id._compute_quantity(
            shortage_product_uom,
            self.product_uom,
        )

    @api.depends(
        'raw_material_production_id',
        'raw_material_production_id.state',
        'product_uom_qty',
        'product_uom',
        'product_id',
        'date',
        'state',
        'planning_purchase_order_line_id',
    )
    def _compute_planning_can_purchase_component(self):
        for move in self:
            move.planning_can_purchase_component = False
            if (
                not move.product_id
                or not move.raw_material_production_id
                or move.planning_purchase_order_line_id
            ):
                continue
            move.planning_can_purchase_component = (
                move._planning_forecast_shortage() > 1e-9
            )

    def action_create_component_purchase(self):
        self.ensure_one()
        production = self.raw_material_production_id
        if not production:
            raise UserError(_('Esta línea no pertenece a los componentes de una orden de fabricación.'))
        if production.state in ('done', 'cancel'):
            raise UserError(_('No puede generar una compra desde una orden de fabricación terminada o cancelada.'))
        if self.planning_purchase_order_line_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Compra del componente'),
                'res_model': 'purchase.order',
                'res_id': self.planning_purchase_order_line_id.order_id.id,
                'view_mode': 'form',
                'views': [(False, 'form')],
                'target': 'current',
            }
        if not self.planning_purchase_vendor_id:
            raise UserError(_('Seleccione un proveedor para el componente %s.') % self.product_id.display_name)

        vendor = self.planning_purchase_vendor_id
        if not self.planning_can_purchase_component:
            raise UserError(_(
                'El componente %s tiene disponibilidad suficiente o ya no requiere una compra desde la OF.'
            ) % self.product_id.display_name)

        # Recalcular en el momento de crear la RFQ para no comprar una cantidad
        # que otra compra/OF/transferencia ya vaya a cubrir.
        qty = self._planning_forecast_shortage()
        if qty <= 0:
            raise UserError(_(
                'El pronóstico ya cubre el componente %s; no es necesario comprar.'
            ) % self.product_id.display_name)

        warehouse = production.picking_type_id.warehouse_id
        picking_type = warehouse.in_type_id if warehouse else False
        Purchase = self.env['purchase.order']
        PurchaseLine = self.env['purchase.order.line']

        domain = [
            ('state', '=', 'draft'),
            ('mrp_production_id', '=', production.id),
            ('partner_id', '=', vendor.commercial_partner_id.id),
        ]
        if picking_type:
            domain.append(('picking_type_id', '=', picking_type.id))
        po = Purchase.search(domain, limit=1)
        if not po:
            vals = {
                'partner_id': vendor.commercial_partner_id.id,
                'company_id': production.company_id.id,
                'origin': production.name,
                'mrp_production_id': production.id,
                'advanced_plan_id': production.advanced_plan_id.id if production.advanced_plan_id else False,
            }
            if picking_type:
                vals['picking_type_id'] = picking_type.id
            po = Purchase.create(vals)

        vals = PurchaseLine._prepare_purchase_order_line(
            self.product_id,
            qty,
            self.product_uom,
            production.company_id,
            po.partner_id,
            po,
        )
        vals.update({
            'mrp_component_move_id': self.id,
            'planning_plan_line_id': self.planning_plan_line_id.id
            if self.planning_plan_line_id else False,
        })
        pol = PurchaseLine.create(vals)
        self.write({
            'planning_purchase_order_line_id': pol.id,
            'planning_purchase_qty': qty,
        })
        production.message_post(body=_(
            'Se creó la compra %s para el componente %s, cantidad %s, proveedor %s.'
        ) % (po.name, self.product_id.display_name, qty, vendor.display_name))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Compra de componente'),
            'res_model': 'purchase.order',
            'res_id': po.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    planning_operation_id = fields.Many2one('mrp.planning.operation', copy=False)
