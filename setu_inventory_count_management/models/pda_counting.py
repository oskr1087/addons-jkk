# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class StockInventoryCountPDA(models.Model):
    _inherit = 'setu.stock.inventory.count'

    zero_result_count = fields.Integer(
        string="Cantidad cero",
        compute="_compute_pda_result_counts"
    )

    # Compatibilidad temporal con vistas heredadas guardadas en la base.
    # Estos campos no precargan productos ni consultan stock.
    pending_result_count = fields.Integer(
        string="Pendientes",
        compute="_compute_legacy_result_counts",
    )
    unexpected_result_count = fields.Integer(
        string="No esperados",
        compute="_compute_legacy_result_counts",
    )

    @api.depends('line_ids.pda_result')
    def _compute_legacy_result_counts(self):
        for count in self:
            count.pending_result_count = len(
                count.line_ids.filtered(lambda l: l.pda_result == 'pending')
            )
            count.unexpected_result_count = len(
                count.line_ids.filtered(lambda l: l.pda_result == 'unexpected')
            )

    @api.depends('line_ids.pda_result')
    def _compute_pda_result_counts(self):
        for count in self:
            count.zero_result_count = len(
                count.line_ids.filtered(lambda l: l.pda_result == 'zero')
            )

    def _action_open_result_lines(self, result, title):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': title,
            'res_model': 'setu.stock.inventory.count.line',
            'view_mode': 'list,form',
            'domain': [('inventory_count_id', '=', self.id), ('pda_result', '=', result)],
            'target': 'current',
        }

    def action_open_zero_result_lines(self):
        return self._action_open_result_lines('zero', _('Cero físico / No encontrado'))

    def action_open_pending_result_lines(self):
        """Compatibilidad con vistas antiguas; solo filtra líneas ya existentes."""
        return self._action_open_result_lines('pending', _('Pendientes'))

    def action_open_unexpected_result_lines(self):
        """Compatibilidad con vistas antiguas; solo filtra líneas ya existentes."""
        return self._action_open_result_lines('unexpected', _('No esperados'))

    def create_session(self):
        self.ensure_one()
        wizard = self.env['setu.inventory.session.creator'].create({
            'inventory_count_id': self.id,
            'is_multi_session': self.type == 'Multi Session',
        })
        return {
            'name': _('Crear sesión'),
            'view_mode': 'form',
            'res_model': 'setu.inventory.session.creator',
            'type': 'ir.actions.act_window',
            'view_id': self.env.ref(
                'setu_inventory_count_management.setu_inventory_session_creator_form_view'
            ).id,
            'res_id': wizard.id,
            'target': 'new',
        }


class StockInventoryCountLinePDA(models.Model):
    _inherit = 'setu.stock.inventory.count.line'

    is_expected_snapshot = fields.Boolean(
        string="Esperado en la ubicación",
        default=False,
        copy=False,
        help="Campo técnico de compatibilidad; no participa en el conteo actual."
    )
    expected_serial_number_ids = fields.Many2many(
        'stock.lot',
        'setu_count_line_expected_serial_rel',
        'count_line_id',
        'lot_id',
        string="Series esperadas",
        copy=False,
    )
    pda_result = fields.Selection(
        [
            ('pending', 'Pendiente'),
            ('counted', 'Contado'),
            ('zero', 'Cero físico / No encontrado'),
            ('unexpected', 'No esperado / Sobrante'),
        ],
        string="Resultado del conteo",
        compute="_compute_pda_result",
        store=True,
    )

    @api.depends('session_line_ids.pda_status', 'counted_qty')
    def _compute_pda_result(self):
        for line in self:
            statuses = line.session_line_ids.mapped('pda_status')
            if 'zero' in statuses:
                line.pda_result = 'zero'
            elif 'counted' in statuses or line.counted_qty > 0:
                line.pda_result = 'counted'
            else:
                line.pda_result = 'pending'


    @api.depends(
        'pda_result', 'counted_qty', 'qty_in_stock', 'serial_number_ids',
        'product_id', 'location_id'
    )
    def _compute_is_discrepancy_found(self):
        for line in self:
            if line.pda_result == 'pending':
                line.is_discrepancy_found = False
                continue
            if line.product_id.tracking == 'serial':
                quants = self.env['stock.quant'].sudo().search([
                    ('location_id', '=', line.location_id.id),
                    ('quantity', '>', 0),
                    ('product_id', '=', line.product_id.id),
                ])
                line.is_discrepancy_found = set(quants.mapped('lot_id').ids) != set(line.serial_number_ids.ids)
            else:
                line.is_discrepancy_found = line.counted_qty != line.qty_in_stock


class InventoryCountSessionLinePDA(models.Model):
    _inherit = 'setu.inventory.count.session.line'

    is_expected_snapshot = fields.Boolean(
        string="Esperado",
        default=False,
        copy=False,
    )
    expected_serial_number_ids = fields.Many2many(
        'stock.lot',
        'setu_session_line_expected_serial_rel',
        'session_line_id',
        'lot_id',
        string="Series esperadas",
        copy=False,
    )
    assumed_zero = fields.Boolean(
        string="Cero por no escaneo",
        default=False,
        copy=False,
        help="Campo técnico de compatibilidad; no participa en el conteo actual."
    )
    pda_status = fields.Selection(
        [
            ('pending', 'Pendiente'),
            ('counted', 'Contado'),
            ('zero', 'Cero físico / No encontrado'),
            ('unexpected', 'No esperado / Sobrante'),
        ],
        string="Estado PDA",
        default='pending',
        copy=False,
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('product_scanned') and vals.get('scanned_qty', 0) == 0:
                vals.setdefault('pda_status', 'zero')
            elif vals.get('scanned_qty', 0) > 0:
                vals.setdefault('pda_status', 'counted')
        return super().create(vals_list)

    def write(self, vals):
        result = super().write(vals)
        if self.env.context.get('skip_pda_status'):
            return result

        watched = {'scanned_qty', 'product_scanned', 'serial_number_ids'}
        if watched.intersection(vals):
            for line in self:
                updates = {}
                if vals.get('product_scanned') and line.scanned_qty == 0:
                    updates.update({'pda_status': 'zero'})
                elif line.scanned_qty > 0 or line.serial_number_ids:
                    updates.update({
                        'pda_status': 'counted',
                        'assumed_zero': False,
                    })
                if updates:
                    super(InventoryCountSessionLinePDA, line.with_context(skip_pda_status=True)).write(updates)
        return result


class InventoryCountSessionPDA(models.Model):
    _inherit = 'setu.inventory.count.session'

    def action_open_mobile_count(self):
        """Open the lightweight OWL workspace instead of a full form view."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'setu_inventory_count_management.pda_fast_count',
            'name': _('Conteo PDA'),
            'params': {'session_id': self.id},
        }

    def _get_pda_fast_state(self):
        self.ensure_one()

        Line = self.env['setu.inventory.count.session.line']
        counted = Line.search_count([
            ('session_id', '=', self.id),
            ('pda_status', 'in', ['counted', 'zero']),
        ])
        zero = Line.search_count([
            ('session_id', '=', self.id),
            ('pda_status', '=', 'zero'),
        ])
        recent = Line.search(
            [('session_id', '=', self.id), ('product_id', '!=', False)],
            order='date_of_scanning desc, id desc',
            limit=3,
        )

        scan_context = self._get_user_scan_context(create=True)
        product = self.current_scanning_product_id
        lot = self.current_scanning_lot_id
        tracking = product.tracking if product else False
        tracking_label = ''
        if product:
            tracking_label = dict(
                product._fields['tracking']._description_selection(self.env)
            ).get(tracking, tracking or '')
        can_set_qty = bool(
            product
            and tracking != 'serial'
            and (tracking != 'lot' or lot)
            and self.current_state in ('Start', 'Resume')
        )

        return {
            'id': self.id,
            'name': self.name or '',
            'warehouse': {
                'id': self.warehouse_id.id,
                'name': self.warehouse_id.display_name or '',
            } if self.warehouse_id else False,
            'scope_location': {
                'id': self.location_id.id,
                'name': self.location_id.display_name or '',
            } if self.location_id else False,
            'state': self.state or '',
            'current_state': self.current_state or '',
            'running': (
                self.current_state in ('Start', 'Resume')
                and not scan_context.paused
                and not scan_context.finished
            ),
            'paused': scan_context.paused,
            'finished': (
                self.state in ('Submitted', 'Done', 'Cancel')
                or scan_context.finished
            ),
            'location': {
                'id': self.current_scanning_location_id.id,
                'name': self.current_scanning_location_id.display_name or '',
            } if self.current_scanning_location_id else False,
            'product': {
                'id': product.id,
                'name': product.display_name or '',
                'barcode': product.barcode or '',
                'tracking': tracking,
                'tracking_label': tracking_label,
                'uom': product.uom_id.display_name or '',
            } if product else False,
            'lot': {
                'id': lot.id,
                'name': lot.name or '',
            } if lot else False,
            'qty': self.mobile_count_qty or 0.0,
            'qr_detected': scan_context.qr_detected,
            'qr_quantity': scan_context.qr_quantity or 0.0,
            'qr_payload': scan_context.qr_payload or '',
            'can_set_qty': can_set_qty,
            'is_serial': tracking == 'serial',
            'counted': counted,
            'zero': zero,
            'feedback': scan_context.last_feedback or '',
            'feedback_type': scan_context.last_feedback_type or 'info',
            'duplicate_warning': (
                'ya fue escaneado' in (scan_context.last_feedback or '').lower()
                or 'pendiente de confirmar' in (scan_context.last_feedback or '').lower()
            ),
            'instruction': (
                _('Escanee primero el QR o código de barras de la ubicación.')
                if self.current_state in ('Start', 'Resume') and not self.current_scanning_location_id
                else _('Escanee cada número de serie.')
                if tracking == 'serial'
                else _('Escanee el lote.')
                if tracking == 'lot' and not lot
                else _('Ingrese la cantidad física y confirme.')
                if can_set_qty
                else _('Escanee el lote, serie o producto de la ubicación activa.')
            ),
            'recent': [{
                'id': line.id,
                'product': line.product_id.display_name or '',
                'lot': line.lot_id.name or '',
                'qty': line.scanned_qty,
                'status': line.pda_status or 'counted',
            } for line in recent],
        }

    def pda_fast_get_state(self):
        return self._get_pda_fast_state()

    def pda_fast_scan(self, barcode):
        self.ensure_one()
        self.on_barcode_scanned(barcode)
        return self._get_pda_fast_state()

    def pda_fast_confirm_qty(self, quantity):
        self.ensure_one()
        product = self.current_scanning_product_id
        lot = self.current_scanning_lot_id

        if product and product.tracking == 'lot' and lot:
            existing_line = self._find_scanned_product_lot_line(product, lot)
            if existing_line:
                self.messege_return(
                    "Advertencia",
                    "El producto %s con lote %s ya fue escaneado en esta sesión. Cantidad registrada: %s."
                    % (product.display_name, lot.name, existing_line.scanned_qty),
                )
                return self._get_pda_fast_state()

        scan_context = self._get_user_scan_context(create=True)
        scan_context.mobile_count_qty = quantity
        self.invalidate_recordset(['mobile_count_qty'])
        self.action_mobile_confirm_qty()
        scan_context.write({
            'qr_payload': False,
            'qr_quantity': 0.0,
            'qr_detected': False,
            'last_feedback': _('Cantidad registrada correctamente.'),
            'last_feedback_type': 'success',
        })
        return self._get_pda_fast_state()

    def pda_fast_finish_location(self):
        """Finaliza la ubicación SOLO para el usuario actual."""
        self.ensure_one()
        location = self.current_scanning_location_id
        if not location:
            raise ValidationError(_("No hay una ubicación activa para finalizar."))

        progress = self.inventory_count_id._location_progress(
            location, create=True
        )
        scan_context = self._get_user_scan_context(create=True)
        scan_context.write({
            'current_location_id': False,
            'current_product_id': False,
            'current_lot_id': False,
            'mobile_count_qty': 1.0,
        })
        self.invalidate_recordset([
            'current_scanning_location_id',
            'current_scanning_product_id',
            'current_scanning_lot_id',
            'mobile_count_qty',
        ])
        progress._mark_finished_by(self.env.user)
        scan_context.write({
            'last_feedback': _(
                "Ubicación %s finalizada. Escanee la siguiente ubicación."
            ) % location.display_name,
            'last_feedback_type': 'success',
        })
        return self._get_pda_fast_state()

    def pda_fast_clear_location(self):
        """Vuelve al Paso 1 solo para el usuario actual.

        No modifica la ubicación ni el producto/lote activo de los demás
        usuarios que estén trabajando en la misma sesión.
        """
        self.ensure_one()
        self._clear_current_user_scan_context(keep_location=False)
        scan_context = self._get_user_scan_context(create=True)
        scan_context.write({
            'last_feedback': _('Escanee la nueva ubicación para continuar.'),
            'last_feedback_type': 'info',
        })
        return self._get_pda_fast_state()

    def pda_fast_clear_item(self):
        self.ensure_one()
        scan_context = self._get_user_scan_context(create=True)
        scan_context.write({
            'current_product_id': False,
            'current_lot_id': False,
            'mobile_count_qty': 1.0,
            'qr_payload': False,
            'qr_quantity': 0.0,
            'qr_detected': False,
            'last_feedback': False,
            'last_feedback_type': 'info',
        })
        self.invalidate_recordset([
            'current_scanning_product_id',
            'current_scanning_lot_id',
            'mobile_count_qty',
        ])
        return self._get_pda_fast_state()

    def pda_fast_control(self, operation):
        self.ensure_one()
        scan_context = self._get_user_scan_context(create=True)
        multiuser = len(self.user_ids) > 1

        if operation == 'start':
            if self.state == 'Draft':
                self.start()
            scan_context.write({
                'paused': False,
                'finished': False,
                'finished_at': False,
            })
        elif operation == 'resume':
            if multiuser:
                scan_context.write({
                    'paused': False,
                    'finished': False,
                })
            else:
                self.resume()
        elif operation == 'pause':
            if multiuser:
                scan_context.paused = True
            else:
                self.pause()
        elif operation == 'submit':
            if multiuser:
                if self.current_scanning_location_id:
                    self.pda_fast_finish_location()
                    scan_context = self._get_user_scan_context(create=True)
                scan_context.write({
                    'finished': True,
                    'finished_at': fields.Datetime.now(),
                    'paused': False,
                })

                assigned = self.user_ids
                contexts = self.env[
                    'setu.inventory.count.session.user.context'
                ].sudo().search([
                    ('session_id', '=', self.id),
                    ('user_id', 'in', assigned.ids),
                    ('finished', '=', True),
                ])
                finished_users = contexts.mapped('user_id')
                if assigned and not (assigned - finished_users):
                    self.submit()
            else:
                self.submit()
        else:
            raise ValidationError(_('Operación PDA no válida.'))
        return self._get_pda_fast_state()

    mobile_simulation_mode = fields.Boolean(
        string="Modo prueba desde celular",
        default=False,
        copy=False,
        help="Permite escribir un código y procesarlo con la misma lógica del lector PDA."
    )
    mobile_simulated_barcode = fields.Char(
        string="Código de prueba",
        copy=False,
    )
    mobile_qr_payload = fields.Char(
        string="QR leído",
        readonly=True,
        copy=False,
    )
    mobile_qr_quantity = fields.Float(
        string="Cantidad indicada en QR",
        readonly=True,
        copy=False,
    )
    mobile_qr_detected = fields.Boolean(
        string="Lectura QR enriquecida",
        readonly=True,
        copy=False,
    )
    mobile_current_product_barcode = fields.Char(
        related="current_scanning_product_id.barcode",
        string="Código del producto",
        readonly=True,
    )
    mobile_current_tracking = fields.Selection(
        related="current_scanning_product_id.tracking",
        string="Seguimiento",
        readonly=True,
    )
    mobile_current_uom_id = fields.Many2one(
        related="current_scanning_product_id.uom_id",
        string="Unidad",
        readonly=True,
    )
    mobile_last_feedback = fields.Char(
        string="Último resultado",
        readonly=True,
        copy=False,
    )
    mobile_last_feedback_type = fields.Selection(
        [
            ('info', 'Información'),
            ('success', 'Correcto'),
            ('warning', 'Advertencia'),
            ('danger', 'Error'),
        ],
        string="Tipo de resultado",
        default='info',
        readonly=True,
        copy=False,
    )

    def messege_return(self, msg_type, message):
        result = super().messege_return(msg_type, message)
        type_map = {
            'Correcto': 'success',
            'Success': 'success',
            'Información': 'info',
            'Notification': 'info',
            'Advertencia': 'warning',
            'Warning': 'warning',
            'Error': 'danger',
        }
        for session in self:
            scan_context = session._get_user_scan_context(create=True)
            scan_context.write({
                'last_feedback': message,
                'last_feedback_type': type_map.get(msg_type, 'info'),
            })
        return result

    def action_mobile_simulate_barcode(self):
        self.ensure_one()
        barcode = (self.mobile_simulated_barcode or '').strip()
        if not barcode:
            raise ValidationError(_("Ingrese un código de barras para simular la lectura."))
        self.mobile_simulated_barcode = False
        self.on_barcode_scanned(barcode)
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_mobile_qty_minus(self):
        self.ensure_one()
        self.mobile_count_qty = max(0.0, (self.mobile_count_qty or 0.0) - 1.0)
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_mobile_qty_plus(self):
        self.ensure_one()
        self.mobile_count_qty = (self.mobile_count_qty or 0.0) + 1.0
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_mobile_qty_zero(self):
        self.ensure_one()
        self.mobile_count_qty = 0.0
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def _parse_lot_qr(self, barcode):
        """Parse labels produced by the packing module.

        Expected individual-label format:
            ARTICULO/LOTE/CANTIDAD

        rsplit() is used so an article code may itself contain '/'.
        Returns False when the scanned value is not a valid enriched QR.
        """
        self.ensure_one()
        if not isinstance(barcode, str) or barcode.count('/') < 2:
            return False

        article, lot_name, quantity_text = [
            value.strip() for value in barcode.rsplit('/', 2)
        ]
        if not article or not lot_name or not quantity_text:
            return False

        normalized_quantity = quantity_text.replace(',', '.')
        try:
            quantity = float(normalized_quantity)
        except (TypeError, ValueError):
            return False

        if quantity < 0:
            return False

        return {
            'article': article,
            'lot_name': lot_name,
            'quantity': quantity,
            'payload': barcode,
        }

    def _find_qr_product(self, article):
        self.ensure_one()
        return self.env['product.product'].sudo().search([
            ('active', '=', True),
            '|',
            ('barcode', '=', article),
            ('default_code', '=', article),
        ], limit=1)

    def _find_qr_lot(self, product, lot_name):
        self.ensure_one()
        return self.env['stock.lot'].sudo().search([
            ('product_id', '=', product.id),
            ('name', '=', lot_name),
            '|',
            ('company_id', '=', False),
            ('company_id', '=', self.company_id.id),
        ], limit=1)

    def _find_scanned_product_lot_line(self, product, lot):
        self.ensure_one()
        return self.session_line_ids.filtered(
            lambda line: (
                line.product_id == product
                and line.lot_id == lot
                and line.location_id == self.current_scanning_location_id
                and line.product_scanned
            )
        )[:1]

    def _scan_enriched_lot_qr(self, barcode):
        """Handle ARTICULO/LOTE/CANTIDAD QR in one read.

        The QR quantity is proposed in the physical quantity field, but the
        operator still confirms it. Nothing is posted merely by scanning.
        """
        self.ensure_one()
        qr = self._parse_lot_qr(barcode)
        if not qr:
            return False

        product = self._find_qr_product(qr['article'])
        if not product:
            self.messege_return(
                "Advertencia",
                "El artículo %s indicado en el QR no existe o no está activo."
                % qr['article'],
            )
            return True

        if product.tracking != 'lot':
            self.messege_return(
                "Advertencia",
                "El QR corresponde a %s, pero el producto no está configurado con seguimiento por lote."
                % product.display_name,
            )
            return True

        lot = self._find_qr_lot(product, qr['lot_name'])
        if not lot:
            self.messege_return(
                "Advertencia",
                "El lote %s no existe para el producto %s."
                % (qr['lot_name'], product.display_name),
            )
            return True

        # Same QR/product+lot currently loaded but not yet confirmed.
        if (
            self.current_scanning_product_id == product
            and self.current_scanning_lot_id == lot
        ):
            self.messege_return(
                "Advertencia",
                "El producto %s con lote %s ya fue escaneado y está pendiente de confirmar."
                % (product.display_name, lot.name),
            )
            return True

        # Already confirmed in this session/location: never duplicate.
        existing_line = self._find_scanned_product_lot_line(product, lot)
        if existing_line:
            self.write({
                'current_scanning_product_id': False,
                'current_scanning_lot_id': False,
                'mobile_qr_payload': False,
                'mobile_qr_quantity': 0.0,
                'mobile_qr_detected': False,
                'mobile_count_qty': 1.0,
            })
            self.messege_return(
                "Advertencia",
                "El producto %s con lote %s ya fue escaneado en esta sesión. Cantidad registrada: %s."
                % (
                    product.display_name,
                    lot.name,
                    existing_line.scanned_qty,
                ),
            )
            return True

        self.write({
            'current_scanning_product_id': product.id,
            'current_scanning_lot_id': lot.id,
            'mobile_count_qty': qr['quantity'],
            'mobile_qr_payload': qr['payload'],
            'mobile_qr_quantity': qr['quantity'],
            'mobile_qr_detected': True,
        })
        self.messege_return(
            "Correcto",
            "QR leído: %s | Lote %s | Cantidad %s. Verifique y confirme la cantidad física."
            % (product.display_name, lot.name, qr['quantity']),
        )
        return True

    def on_barcode_scanned(self, barcode):
        """Flujo principal de lectura para PDA.

        Producto: selecciona el artículo y espera la cantidad física.
        Lote: selecciona producto+lote y espera la cantidad física.
        Serie: cada serie válida suma exactamente una unidad.
        """
        self.ensure_one()
        barcode = (barcode or '').strip() if isinstance(barcode, str) else barcode
        if not barcode:
            return self.messege_return("Advertencia", "No se detectó ningún código de barras.")
        if not self.use_barcode_scanner:
            return self.messege_return("Advertencia", "El conteo por PDA no está habilitado.")
        if self.current_state not in ('Start', 'Resume'):
            return self.messege_return("Advertencia", "Inicie o reanude la sesión para escanear.")

        # Una ubicación siempre tiene prioridad. Esto permite cambiar de
        # ubicación simplemente escaneando el siguiente QR/código.
        location = self._find_scanning_location(barcode)
        if location:
            self._activate_scanned_location(location)
            return self.messege_return(
                "Correcto",
                "Ubicación %s activada. Continúe con los lotes/productos."
                % location.display_name,
            )

        # Ningún lote/producto se procesa sin una ubicación física activa.
        if not self.current_scanning_location_id:
            return self.messege_return(
                "Advertencia",
                "Escanee primero el QR o código de barras de la ubicación."
            )

        # One-scan path for packing labels: ARTICULO/LOTE/CANTIDAD.
        # If it looks like our enriched QR, it is fully handled here.
        if self._scan_enriched_lot_qr(barcode):
            return

        # Fast path para productos dentro de la ubicación físicamente escaneada.
        # Search the product first. Only if it is not a product barcode do we
        # query lots/serials. This avoids unnecessary queries on every scan.
        product = self.env['product.product'].sudo().search([
            ('barcode', '=', barcode),
            ('active', '=', True),
        ], limit=1)

        if product:
            self.write({
                'current_scanning_product_id': product.id,
                'current_scanning_lot_id': False,
                'mobile_count_qty': 1.0,
            })
            if product.tracking == 'none':
                return self.messege_return(
                    "Información",
                    "%s identificado. Ingrese la cantidad física y confirme." % product.display_name
                )
            if product.tracking == 'lot':
                return self.messege_return(
                    "Información",
                    "%s identificado. Escanee el lote." % product.display_name
                )
            return self.messege_return(
                "Información",
                "%s identificado. Escanee cada número de serie." % product.display_name
            )

        lot_domain = [('name', '=', barcode)]
        if self.current_scanning_product_id and self.current_scanning_product_id.tracking in ('lot', 'serial'):
            lot_domain.append(('product_id', '=', self.current_scanning_product_id.id))
        lots = self.env['stock.lot'].sudo().search(lot_domain, limit=2)
        if len(lots) > 1:
            return self.messege_return(
                "Advertencia",
                "El código de lote/serie es ambiguo. Escanee primero el producto."
            )
        lot = lots[:1]

        if lot:
            product = lot.product_id
            if not product:
                return self.messege_return("Advertencia", "El lote o serie no tiene un producto asociado.")

            if product.tracking == 'serial':
                all_active_lines = self.inventory_count_id.session_ids.filtered(
                    lambda s: s.state != 'Cancel'
                ).mapped('session_line_ids')
                duplicate = all_active_lines.filtered(
                    lambda l: lot in l.serial_number_ids and l.session_id != self
                )
                own_duplicate = self.session_line_ids.filtered(lambda l: lot in l.serial_number_ids)
                if duplicate or own_duplicate:
                    return self.messege_return("Advertencia", "La serie %s ya fue contada." % lot.name)

                line = self.session_line_ids.filtered(
                    lambda l: l.location_id == self.current_scanning_location_id
                    and l.product_id == product
                )[:1]
                if not line:
                    line = self.env['setu.inventory.count.session.line'].create({
                        'session_id': self.id,
                        'inventory_count_id': self.inventory_count_id.id,
                        'location_id': self.current_scanning_location_id.id,
                        'product_id': product.id,
                        'scanned_qty': 0,
                        'is_expected_snapshot': False,
                        'pda_status': 'counted',
                    })

                new_serials = line.serial_number_ids | lot
                line.write({
                    'serial_number_ids': [(6, 0, new_serials.ids)],
                    'scanned_qty': len(new_serials),
                    'product_scanned': True,
                    'date_of_scanning': fields.Datetime.now(),
                    'user_ids': [(4, self.env.user.id)],
                })
                self.write({
                    'current_scanning_product_id': product.id,
                    'current_scanning_lot_id': False,
                })
                return self.messege_return(
                    "Correcto",
                    "Serie %s registrada. Escanee la siguiente serie." % lot.name
                )

            if product.tracking == 'lot':
                if self.current_scanning_product_id and self.current_scanning_product_id != product:
                    return self.messege_return(
                        "Advertencia",
                        "El lote %s no pertenece al producto seleccionado." % lot.name
                    )

                if (
                    self.current_scanning_product_id == product
                    and self.current_scanning_lot_id == lot
                ):
                    return self.messege_return(
                        "Advertencia",
                        "El producto %s con lote %s ya fue escaneado y está pendiente de confirmar."
                        % (product.display_name, lot.name),
                    )

                existing_line = self._find_scanned_product_lot_line(product, lot)
                if existing_line:
                    return self.messege_return(
                        "Advertencia",
                        "El producto %s con lote %s ya fue escaneado en esta sesión. Cantidad registrada: %s."
                        % (product.display_name, lot.name, existing_line.scanned_qty),
                    )

                self.write({
                    'current_scanning_product_id': product.id,
                    'current_scanning_lot_id': lot.id,
                    'mobile_count_qty': 1.0,
                    'mobile_qr_payload': False,
                    'mobile_qr_quantity': 0.0,
                    'mobile_qr_detected': False,
                })
                return self.messege_return(
                    "Información",
                    "Lote %s identificado. Ingrese la cantidad física y confirme." % lot.name
                )

        return self.messege_return(
            "Advertencia",
            "Código no reconocido. Debe corresponder a un producto, lote, serie o ubicación."
        )

    pda_counted_lines = fields.Integer(compute="_compute_pda_stats", string="Contados")
    pda_zero_lines = fields.Integer(compute="_compute_pda_stats", string="Cantidad cero")

    pda_expected_lines = fields.Integer(
        compute="_compute_pda_stats",
        string="Esperados",
    )
    pda_pending_lines = fields.Integer(
        compute="_compute_pda_stats",
        string="Pendientes",
    )
    pda_unexpected_lines = fields.Integer(
        compute="_compute_pda_stats",
        string="No esperados",
    )

    @api.depends('session_line_ids.pda_status')
    def _compute_pda_stats(self):
        for session in self:
            counted = 0
            zero = 0
            pending = 0
            unexpected = 0
            for line in session.session_line_ids:
                if line.pda_status == 'zero':
                    zero += 1
                    counted += 1
                elif line.pda_status == 'counted':
                    counted += 1
                elif line.pda_status == 'pending':
                    pending += 1
                elif line.pda_status == 'unexpected':
                    unexpected += 1
            session.pda_counted_lines = counted
            session.pda_zero_lines = zero
            session.pda_expected_lines = 0
            session.pda_pending_lines = pending
            session.pda_unexpected_lines = unexpected

    @api.depends(
        'current_scanning_location_id', 'current_scanning_product_id',
        'current_scanning_lot_id', 'current_state', 'state',
        'session_line_ids.scanned_qty', 'session_line_ids.product_id',
        'session_line_ids.pda_status',
    )
    def _compute_mobile_status(self):
        super()._compute_mobile_status()
        for session in self:
            completed = len(session.session_line_ids.filtered(
                lambda line: line.pda_status in ('counted', 'zero')
            ))
            session.mobile_counted_products = completed
            # Without preloading there is no artificial "expected total".
            # Keep progress as 0 until items are counted; the UI shows the live count.
            session.mobile_progress_percent = 0.0

            if session.current_state in ('Start', 'Resume'):
                if not session.current_scanning_location_id:
                    session.mobile_instruction = _(
                        "Escanee primero el QR o código de barras de la ubicación."
                    )
                elif not session.current_scanning_product_id:
                    session.mobile_instruction = _(
                        "Ubicación validada. Escanee el lote, serie o producto."
                    )
