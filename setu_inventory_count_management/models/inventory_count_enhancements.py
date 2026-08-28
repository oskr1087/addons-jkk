# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare


DISCREPANCY_TYPES = [
    ('match', 'No Difference'),
    ('shortage', 'Faltante'),
    ('surplus', 'Sobrante'),
    ('serial_mismatch', 'Serie incorrecta'),
]


class SetuStockInventoryCountEnhancements(models.Model):
    _inherit = 'setu.stock.inventory.count'

    blind_count = fields.Boolean(
        string='Conteo ciego', default=True,
        help='Oculta las cantidades teóricas y las diferencias mientras el personal realiza el conteo.')
    tolerance_mode = fields.Selection([
        ('none', 'Sin tolerancia'),
        ('quantity', 'Cantidad'),
        ('percentage', 'Porcentaje'),
        ('value', 'Valor'),
    ], string='Modo de tolerancia', default='none')
    tolerance_quantity = fields.Float(string='Tolerancia de cantidad', default=0.0)
    tolerance_percentage = fields.Float(string='Tolerancia porcentual', default=0.0)
    tolerance_value = fields.Monetary(string='Tolerancia de valor', default=0.0, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True)
    auto_approve_exact = fields.Boolean(string='Autoaprobar coincidencias exactas', default=True)
    auto_approve_tolerance = fields.Boolean(string='Autoaprobar dentro de tolerancia', default=False)
    movement_policy = fields.Selection([
        ('allow', 'Permitir movimientos'),
        ('warn', 'Permitir y rastrear'),
        ('block', 'Bloquear movimientos en ubicaciones contadas'),
    ], string='Movimientos durante el conteo', default='block', required=True,
       help='Por seguridad, los conteos activos bloquean siempre todo el almacén hasta su aprobación.')

    @api.constrains('tolerance_quantity', 'tolerance_percentage', 'tolerance_value')
    def _check_tolerance_values(self):
        for count in self:
            if count.tolerance_quantity < 0 or count.tolerance_percentage < 0 or count.tolerance_value < 0:
                raise ValidationError(_('Las tolerancias del conteo no pueden ser negativas.'))

    def action_apply_review_policy(self):
        self.ensure_one()
        if not self.env.user.has_group('setu_inventory_count_management.group_setu_inventory_count_manager'):
            raise UserError(_('Solo un responsable de conteo de inventario puede aplicar la política de revisión.'))
        if self.state not in ('In Progress', 'To Be Approved'):
            raise UserError(_('La política de revisión automática solo puede aplicarse durante el conteo o la aprobación.'))
        approved = 0
        for line in self.line_ids.filtered(lambda l: l.state == 'Pending Review'):
            if (self.auto_approve_exact and not line.is_discrepancy_found) or (
                    self.auto_approve_tolerance and line.within_tolerance):
                line.state = 'Approve'
                approved += 1
        self.message_post(body=_('%s count line(s) were approved automatically using the configured review policy.') % approved)
        return True

    def create_inventory_adj(self):
        """Make adjustment generation idempotent."""
        self.ensure_one()
        existing = self.inventory_adj_ids.filtered(lambda a: a.state != 'cancel')
        if existing:
            raise UserError(_(
                'An active Inventory Adjustment already exists for this Inventory Count. '
                'Open the existing adjustment instead of creating a duplicate.'
            ))
        return super().create_inventory_adj()


class SetuInventoryCountSessionEnhancements(models.Model):
    _inherit = 'setu.inventory.count.session'

    blind_count = fields.Boolean(related='inventory_count_id.blind_count', readonly=True)
    movement_policy = fields.Selection(related='inventory_count_id.movement_policy', readonly=True)
    scan_instruction = fields.Char(compute='_compute_scan_instruction', string='Next Scan')

    @api.depends('current_scanning_location_id', 'current_scanning_product_id', 'current_scanning_lot_id', 'current_state')
    def _compute_scan_instruction(self):
        for session in self:
            if session.current_state not in ('Start', 'Resume'):
                session.scan_instruction = _('Inicie o reanude la sesión para escanear.')
            elif not session.current_scanning_location_id:
                session.scan_instruction = _('Escanee primero una ubicación.')
            elif not session.current_scanning_product_id:
                session.scan_instruction = _('Escanee un producto, lote o número de serie.')
            elif session.current_scanning_product_id.tracking in ('lot', 'serial') and not session.current_scanning_lot_id:
                session.scan_instruction = _('Escanee el lote o número de serie.')
            else:
                session.scan_instruction = _('Continúe escaneando productos o cambie la ubicación.')

    def on_barcode_scanned(self, barcode):
        # Tag all changes created by the standard Setu barcode flow as scanner-originated.
        return super(SetuInventoryCountSessionEnhancements, self.with_context(setu_scan_capture=True)).on_barcode_scanned(barcode)


class InventorySessionLineEnhancements(models.Model):
    _inherit = 'setu.inventory.count.session.line'

    blind_count = fields.Boolean(related='inventory_count_id.blind_count', readonly=True)
    discrepancy_type = fields.Selection(DISCREPANCY_TYPES, compute='_compute_review_metadata', store=True,
                                        string='Tipo de discrepancia')
    within_tolerance = fields.Boolean(compute='_compute_review_metadata', store=True, string='Dentro de tolerancia')
    capture_source = fields.Selection([
        ('manual', 'Manual'),
        ('scanner', 'Escáner / Cámara'),
        ('system', 'Sistema'),
    ], default='manual', copy=False, readonly=True, string='Capture Source')
    manual_edit_count = fields.Integer(default=0, copy=False, readonly=True)
    last_manual_edit_by = fields.Many2one('res.users', copy=False, readonly=True)
    last_manual_edit_at = fields.Datetime(copy=False, readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        source = 'scanner' if self.env.context.get('setu_scan_capture') else self.env.context.get('setu_capture_source', 'manual')
        for vals in vals_list:
            vals.setdefault('capture_source', source)
        return super().create(vals_list)

    def write(self, vals):
        audit = 'scanned_qty' in vals and not self.env.context.get('setu_scan_capture') and not self.env.context.get('setu_skip_manual_audit')
        old_values = {line.id: line.scanned_qty for line in self} if audit else {}
        result = super().write(vals)
        if audit:
            now = fields.Datetime.now()
            for line in self:
                old = old_values.get(line.id)
                if old is not None and float_compare(old, line.scanned_qty, precision_rounding=line.product_id.uom_id.rounding or 0.01) != 0:
                    super(InventorySessionLineEnhancements, line.with_context(setu_skip_manual_audit=True)).write({
                        'manual_edit_count': line.manual_edit_count + 1,
                        'last_manual_edit_by': self.env.user.id,
                        'last_manual_edit_at': now,
                        'capture_source': 'manual',
                    })
                    if line.session_id:
                        line.session_id.message_post(body=_(
                            'Counted quantity for %(product)s was manually changed from %(old)s to %(new)s by %(user)s.'
                        ) % {
                            'product': line.product_id.display_name,
                            'old': old,
                            'new': line.scanned_qty,
                            'user': self.env.user.display_name,
                        })
        return result

    @api.depends('difference_qty', 'discrepancy_value', 'theoretical_qty', 'product_id',
                 'serial_number_ids', 'inventory_count_id.tolerance_mode',
                 'inventory_count_id.tolerance_quantity', 'inventory_count_id.tolerance_percentage',
                 'inventory_count_id.tolerance_value')
    def _compute_review_metadata(self):
        for line in self:
            diff = line.difference_qty
            if line.product_id.tracking == 'serial' and line.is_discrepancy_found:
                dtype = 'serial_mismatch'
            elif diff < 0:
                dtype = 'shortage'
            elif diff > 0:
                dtype = 'surplus'
            else:
                dtype = 'match'
            line.discrepancy_type = dtype
            line.within_tolerance = line._is_within_configured_tolerance()

    def _is_within_configured_tolerance(self):
        self.ensure_one()
        count = self.inventory_count_id
        if not count or not self.is_discrepancy_found:
            return True
        diff = abs(self.difference_qty)
        if count.tolerance_mode == 'quantity':
            return diff <= count.tolerance_quantity
        if count.tolerance_mode == 'percentage':
            base = abs(self.theoretical_qty)
            pct = (diff / base * 100.0) if base else (0.0 if not diff else 100.0)
            return pct <= count.tolerance_percentage
        if count.tolerance_mode == 'value':
            return abs(self.discrepancy_value) <= count.tolerance_value
        return False

    def _get_counted_qty(self, line, count_line_exists_already=False):
        """Reconcile movements after scanning using the exact counted location.

        The original implementation searched outgoing moves for the product without
        restricting their source location, so a delivery from another warehouse could
        alter this count. It also ignored receipts/internal moves entering the location.
        """
        if line.product_id.tracking == 'serial':
            return super()._get_counted_qty(line, count_line_exists_already=count_line_exists_already)

        if line.session_id.session_id:
            qty = line.scanned_qty
        else:
            qty = (count_line_exists_already.counted_qty if count_line_exists_already else 0.0) + line.scanned_qty

        common = [
            ('state', '=', 'done'),
            ('product_id', '=', line.product_id.id),
            ('company_id', '=', line.session_id.company_id.id),
            ('date', '>=', line.date_of_scanning),
        ]
        if line.product_id.tracking == 'lot':
            common.append(('lot_id', '=', line.lot_id.id))

        MoveLine = self.env['stock.move.line'].sudo()
        outgoing = MoveLine.search(common + [
            ('location_id', '=', line.location_id.id),
            ('location_dest_id', '!=', line.location_id.id),
        ])
        incoming = MoveLine.search(common + [
            ('location_dest_id', '=', line.location_id.id),
            ('location_id', '!=', line.location_id.id),
        ])
        involved = outgoing | incoming
        if involved:
            involved.write({'count_id': line.session_id.inventory_count_id.id})
        return qty - sum(outgoing.mapped('quantity')) + sum(incoming.mapped('quantity'))


class StockInventoryCountLineEnhancements(models.Model):
    _inherit = 'setu.stock.inventory.count.line'

    discrepancy_type = fields.Selection(DISCREPANCY_TYPES, compute='_compute_review_metadata', store=True,
                                        string='Tipo de discrepancia')
    within_tolerance = fields.Boolean(compute='_compute_review_metadata', store=True, string='Dentro de tolerancia')

    @api.depends('difference_qty', 'discrepancy_value', 'theoretical_qty', 'product_id',
                 'serial_number_ids', 'inventory_count_id.tolerance_mode',
                 'inventory_count_id.tolerance_quantity', 'inventory_count_id.tolerance_percentage',
                 'inventory_count_id.tolerance_value')
    def _compute_review_metadata(self):
        for line in self:
            diff = line.difference_qty
            if line.product_id.tracking == 'serial' and line.is_discrepancy_found:
                dtype = 'serial_mismatch'
            elif diff < 0:
                dtype = 'shortage'
            elif diff > 0:
                dtype = 'surplus'
            else:
                dtype = 'match'
            line.discrepancy_type = dtype
            line.within_tolerance = line._is_within_configured_tolerance()

    def _is_within_configured_tolerance(self):
        self.ensure_one()
        count = self.inventory_count_id
        if not count or not self.is_discrepancy_found:
            return True
        diff = abs(self.difference_qty)
        if count.tolerance_mode == 'quantity':
            return diff <= count.tolerance_quantity
        if count.tolerance_mode == 'percentage':
            base = abs(self.theoretical_qty)
            pct = (diff / base * 100.0) if base else (0.0 if not diff else 100.0)
            return pct <= count.tolerance_percentage
        if count.tolerance_mode == 'value':
            return abs(self.discrepancy_value) <= count.tolerance_value
        return False


class StockMoveLineInventoryCountProtection(models.Model):
    _inherit = 'stock.move.line'

    def _check_inventory_count_warehouse_lock(self):
        Count = self.env['setu.stock.inventory.count']
        for move_line in self:
            locations = move_line.location_id | move_line.location_dest_id
            locked_count = Count._get_locked_count_for_locations(
                locations,
                company=move_line.company_id,
            )
            if locked_count:
                raise UserError(_(
                    'No puede realizar este movimiento porque el almacén %(warehouse)s '
                    'está bloqueado por el conteo %(count)s. El bloqueo se libera '
                    'cuando el conteo sea aprobado, rechazado o cancelado.'
                ) % {
                    'warehouse': locked_count.warehouse_id.display_name,
                    'count': locked_count.display_name,
                })
        return True

    def _action_done(self):
        # Última barrera antes de modificar stock.quant. Aplica a compras,
        # ventas, transferencias, MRP, scrap, POS e inventarios.
        self._check_inventory_count_warehouse_lock()
        return super()._action_done()

