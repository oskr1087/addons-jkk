# -*- coding: utf-8 -*-
from datetime import datetime
from markupsafe import Markup
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
from odoo.fields import Date


class StockInvCount(models.Model):
    _name = 'setu.stock.inventory.count'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _description = 'Stock Inventory Count'

    use_barcode_scanner = fields.Boolean(default=False, string="Usar escáner de códigos")
    non_cancelled_session = fields.Boolean(compute="_compute_non_cancelled_session", string="Sesión no cancelada")
    start_inventory_bool = fields.Boolean(compute="_compute_start_inventory_bool", string="Inventario iniciado")
    create_count_bool = fields.Boolean(compute="_compute_create_count_bool", string="Crear conteo")
    create_session_bool = fields.Boolean(compute="_compute_create_session_bool", string="Crear sesión")

    name = fields.Char(string="Nombre")

    inventory_count_date = fields.Date(default=fields.Datetime.now, string="Fecha")

    count_session_ids = fields.Integer(compute="_compute_count_session_ids", string="Cantidad de sesiones")
    re_count_ids = fields.Integer(compute="_compute_count_ids", string="Reconteo")
    rejected_lines_count = fields.Integer(compute="_compute_rejected_lines_count", string="Cantidad de líneas rechazadas")

    discrepancy_ratio = fields.Float(compute="_compute_discrepancy_ratio", string="Porcentaje de discrepancia",store=True)
    user_mistake_ratio = fields.Float(compute="_compute_user_mistake_ratio", string="Porcentaje de errores del usuario",store=True)

    state = fields.Selection(selection=[('Rejected', 'Rechazado'), ('Draft', 'Borrador'),
                                        ('In Progress', 'En progreso'), ('To Be Approved', 'Por aprobar'),
                                        ('Approved', 'Aprobado'), ('Inventory Adjusted', 'Inventario ajustado'),
                                        ('Cancel', 'Cancelado')], default="Draft", string="Estado")
    type = fields.Selection([('Single Session', 'Sesión única'), ('Multi Session', 'Múltiples sesiones')],
                            default='Single Session', required=True, string="Tipo")

    location_id = fields.Many2one(comodel_name="stock.location", string="Ubicación")
    warehouse_id = fields.Many2one(comodel_name="stock.warehouse", string="Almacén")
    approver_id = fields.Many2one(comodel_name="res.users", string="Controlador", default=lambda self: self._default_approver())
    user_id = fields.Many2one(comodel_name="res.users", default=lambda self: self.env.user.id, string="Usuario")
    planner_id = fields.Many2one(comodel_name="setu.stock.inventory.count.planner", string='Planificador', readonly=True)
    count_id = fields.Many2one(comodel_name="setu.stock.inventory.count", readonly=True, copy=False, string="Conteo")


    line_ids = fields.One2many('setu.stock.inventory.count.line', 'inventory_count_id', string="Líneas de conteo de inventario")
    session_ids = fields.One2many('setu.inventory.count.session', 'inventory_count_id', string="Detalles de sesiones")
    inventory_adj_ids = fields.One2many('setu.stock.inventory', 'inventory_count_id',
                                        string="Detalles del ajuste de inventario")
    count_ids = fields.One2many('setu.stock.inventory.count', 'count_id', copy=False, string='Conteos')
    stock_move_line_ids = fields.One2many('stock.move.line', 'count_id', string="Línea de movimiento")

    locations_ids = fields.Many2many('stock.location', string='Ubicaciones', compute='_compute_warehouse_id', store=True)
    product_ids = fields.Many2many(comodel_name="product.product", string="Productos")
    approver_ids = fields.Many2many(comodel_name="res.users", compute='_compute_approver_id', string="Controladores")
    company_id = fields.Many2one(comodel_name="res.company", related="warehouse_id.company_id", string="Compañía",
                                 store=True)

    def _get_approver_candidates(self, company=None):
        """Return active inventory controllers visible for the count company.

        sudo() is intentional here: record rules on res.users must not make the
        controller selector intermittently empty for warehouse users.
        """
        manager_group = self.env.ref(
            'setu_inventory_count_management.group_setu_inventory_count_manager'
        )
        company = company or self.env.company
        domain = [
            ('active', '=', True),
            ('share', '=', False),
            ('group_ids', 'in', manager_group.id),
        ]
        if company:
            domain.append(('company_ids', 'in', company.id))

        users = self.env['res.users'].sudo().search(domain, order='name, id')

        # The user creating the count must remain selectable when they are a
        # controller and have access to the selected company.
        current = self.env.user
        if (
            current.active
            and not current.share
            and current.has_group(
                'setu_inventory_count_management.group_setu_inventory_count_manager'
            )
            and (not company or company in current.company_ids)
        ):
            users |= current
        return users.sorted(key=lambda user: (user.name or '', user.id))

    def _default_approver(self):
        candidates = self._get_approver_candidates(self.env.company)
        if self.env.user in candidates:
            return self.env.user.id
        return candidates[:1].id if candidates else False

    @api.constrains('inventory_count_date')
    def _check_inventory_count_date(self):
        today = Date.today()
        for rec in self:
            if rec.inventory_count_date and rec.inventory_count_date < today:
                raise ValidationError(_('No puede seleccionar una fecha anterior.'))

    def _compute_non_cancelled_session(self):
        for rec in self:
            if rec.session_ids and rec.session_ids.filtered(lambda s: s.state != 'Cancel'):
                rec.non_cancelled_session = True
            else:
                rec.non_cancelled_session = False

    def complete_counting(self):
        if self.session_ids.filtered(lambda s: s.state not in ('Cancel', 'Done')):
            raise ValidationError(_(
                "Envíe y valide todas las sesiones incompletas antes de completar el conteo."))
        self.state = 'To Be Approved'

    def _compute_discrepancy_ratio(self):
        for rec in self:
            if rec.line_ids:
                product_discrepancy_dict = dict()
                for line in rec.line_ids:
                    product_id = line.product_id.id
                    if product_id in product_discrepancy_dict:
                        if line.is_discrepancy_found:
                            product_discrepancy_dict.update({product_id: True})
                    else:
                        product_discrepancy_dict.update({product_id: line.is_discrepancy_found})
                number_of_products = len(product_discrepancy_dict.keys())
                discrepancy_products = 0
                for product, discrepancy_bool in product_discrepancy_dict.items():
                    if discrepancy_bool:
                        discrepancy_products += 1
                ratio = discrepancy_products * 100 / number_of_products
                rec.discrepancy_ratio = ratio
            else:
                rec.discrepancy_ratio = 0

    def action_open_discrepancy_lines(self):
        discrepancy_lines = self.line_ids.filtered(lambda l: l.is_discrepancy_found)
        ids = discrepancy_lines.ids if discrepancy_lines else []
        view_id = self.sudo().env.ref('setu_inventory_count_management.setu_stock_inventory_count_line_tree_view')
        return {'name': 'Discrepancy Lines',
                'view_mode': 'list',
                'view_id': view_id.id,
                'res_model': 'setu.stock.inventory.count.line',
                'type': 'ir.actions.act_window',
                'domain': [('id', 'in', ids)]}

    def _compute_user_mistake_ratio(self):
        for rec in self:
            rec.user_mistake_ratio = 0
            if not rec.line_ids:
                continue

            product_user_mistake_dict = {}
            for line in rec.line_ids:
                product_id = line.product_id.id
                if product_id in product_user_mistake_dict:
                    if line.user_calculation_mistake:
                        product_user_mistake_dict[product_id] = True
                else:
                    product_user_mistake_dict[product_id] = line.user_calculation_mistake

            number_of_products = len(product_user_mistake_dict)
            if number_of_products:
                user_mistake_products = sum(
                    1 for mistake in product_user_mistake_dict.values() if mistake
                )
                rec.user_mistake_ratio = (
                    user_mistake_products * 100 / number_of_products
                )

    def approve_all_lines(self):
        message = "Are you sure that you want to Approve all session lines? (Even rejected lines will also be approved)"
        wiz = self.env['setu.inventory.warning.message.wizard'].create({'message': message})
        view_id = self.sudo().env.ref(
            'setu_inventory_count_management.setu_inventory_warning_approve_message_wizard_form_view')

        return {'name': 'Warning!!!',
                'view_mode': 'form',
                'view_id': view_id.id,
                'res_model': 'setu.inventory.warning.message.wizard',
                'type': 'ir.actions.act_window',
                'res_id': wiz.id,
                'target': 'new'}

    def reject_all_lines(self):
        message = "Are you sure that you want to Reject all session lines? (Even approved lines will also be rejected)"
        wiz = self.env['setu.inventory.warning.message.wizard'].create({'message': message})
        view_id = self.sudo().env.ref(
            'setu_inventory_count_management.setu_inventory_count_warning_reject_message_wizard_form_view')

        return {'name': 'Warning!!!',
                'view_mode': 'form',
                'view_id': view_id.id,
                'res_model': 'setu.inventory.warning.message.wizard',
                'type': 'ir.actions.act_window',
                'res_id': wiz.id,
                'target': 'new'}

    def open_new_count(self, users):
        rejected_lines = self.line_ids.filtered(lambda s: s.state == 'Reject')
        new_count = self.env['setu.stock.inventory.count'].create({
            'approver_id': self.approver_id.id,
            'count_id': self.id,
            'location_id': self.location_id.id,
            'warehouse_id': self.warehouse_id.id,
            'use_barcode_scanner': self.use_barcode_scanner,
            'type': 'Multi Session'
        })
        new_session = self.env['setu.inventory.count.session'].create({
            'is_multi_session': True,
            'user_ids': [(6, 0, users.ids)],
            'inventory_count_id': new_count.id,
            'location_id': new_count.location_id.id,
            'warehouse_id': new_count.warehouse_id.id,
            'use_barcode_scanner': new_count.use_barcode_scanner,
            'type': 'Multi Session',
        })
        for line in rejected_lines:
            tracking = line.product_id.tracking
            vals = {
                'product_id': line.product_id.id,
                'location_id': line.location_id.id,
                'date_of_scanning': datetime.now(),
                'session_id': new_session.id,
                'inventory_count_id': new_count.id,
                'is_multi_session': new_session.is_multi_session,
            }
            domain = [('location_id', '=', line.location_id.id),
                      ('product_id', '=', line.product_id.id)]
            if tracking == 'none':
                quants = self.env['stock.quant'].sudo().search(domain)
                qty_available = sum([x.quantity for x in quants])
                vals.update({'theoretical_qty': qty_available})
            elif tracking == 'lot':
                domain.append(('lot_id', '=', line.lot_id.id))
                quants = self.env['stock.quant'].sudo().search(domain)
                qty_available = sum([x.quantity for x in quants])
                vals.update({'theoretical_qty': qty_available, 'lot_id': line.lot_id.id})

            self.env['setu.inventory.count.session.line'].create(vals)
        self.state = 'Approved'
        self.create_inventory_adj()

    def action_open_user_mistake_lines(self):
        user_mistake_lines = self.line_ids.filtered(lambda l: l.user_calculation_mistake)
        ids = user_mistake_lines.ids if user_mistake_lines else []
        view_id = self.sudo().env.ref('setu_inventory_count_management.setu_stock_inventory_count_line_tree_view')
        return {'name': 'User Calculation Mistake Lines',
                'view_mode': 'list',
                'view_id': view_id.id,
                'res_model': 'setu.stock.inventory.count.line',
                'type': 'ir.actions.act_window',
                'domain': [('id', 'in', ids)]}

    def reset_to_draft(self):
        self.state = 'Draft'
        if not self.count_id:
            self.line_ids.unlink()
        else:
            self.line_ids.state = 'Pending Review'
            self.line_ids.counted_qty = 0

    def cancel(self):
        sessions = self.session_ids.filtered(lambda s: s.state != 'Cancel')
        if sessions:
            sessions_str = "\n".join(set(sessions.mapped('name')))
            raise ValidationError(
                _("This Inventory Count cannot be cancelled because few of the sessions are already running, "
                  "\n%s" % sessions_str))
        if self.state == 'Draft':
            self.state = 'Cancel'
            for session in self.session_ids:
                session.state = 'Cancel'
            for line in self.line_ids:
                line.qty_in_stock = line.theoretical_qty

    def _compute_rejected_lines_count(self):
        for rec in self:
            rejected_lines = rec.line_ids.filtered(lambda l: l.state == 'Reject')
            rec.rejected_lines_count = len(rejected_lines) if rejected_lines else 0

    def _compute_create_count_bool(self):
        for rec in self:
            rec.create_count_bool = bool(
                rec.state in ('To Be Approved', 'Done')
                and rec.rejected_lines_count > 0
            )

    def _compute_create_session_bool(self):
        for rec in self:
            if rec.state not in ('Draft', 'In Progress'):
                rec.create_session_bool = False
                continue

            if rec.type == 'Single Session':
                active_sessions = rec.session_ids.filtered(
                    lambda session: session.state != 'Cancel'
                )
                rec.create_session_bool = not bool(active_sessions)
            else:
                rec.create_session_bool = True

    def _compute_start_inventory_bool(self):
        for rec in self:
            rec.start_inventory_bool = True
            if rec.inventory_adj_ids and rec.inventory_adj_ids.filtered(lambda a: a.state not in ('cancel')):
                rec.start_inventory_bool = False
                continue
            adj_lines = rec.line_ids.filtered(lambda l: l.is_discrepancy_found and l.state == 'Approve')
            if not adj_lines:
                rec.start_inventory_bool = False

    def _compute_count_session_ids(self):
        for rec in self:
            session = rec.session_ids.filtered(lambda l: l.state not in ('Cancel'))
            rec.count_session_ids = len(session)

    def _compute_count_ids(self):
        for rec in self:
            rec.re_count_ids = len(rec.count_ids)

    def get_products_from_setu_reports(self):
        action = \
            self.sudo().env.ref('setu_inventory_count_management.get_products_from_setu_reports_act_window').read()[0]
        wizard = self.env['get.products.from.adv.inv.rep.wizard'].create({})
        wizard.warehouse_ids = self.warehouse_id
        action.update({'res_id': wizard.id})
        return action

    def action_open_sessions(self):
        """Always open count sessions in Kanban, even when there is only one."""
        sessions_to_open = self.session_ids
        if not sessions_to_open:
            return {'type': 'ir.actions.act_window_close'}

        action = self.sudo().env.ref(
            'setu_inventory_count_management.inventory_count_session_act_window'
        ).read()[0]
        action['domain'] = [('id', 'in', sessions_to_open.ids)]
        action['view_mode'] = 'kanban,list,form'
        action['views'] = [
            (self.sudo().env.ref(
                'setu_inventory_count_management.setu_inventory_count_session_kanban_view'
            ).id, 'kanban'),
            (self.sudo().env.ref(
                'setu_inventory_count_management.inventory_count_session_tree_view'
            ).id, 'list'),
            (self.sudo().env.ref(
                'setu_inventory_count_management.inventory_count_session_form_view'
            ).id, 'form'),
        ]
        action.pop('res_id', None)
        return action

    def action_open_counts(self):
        count_to_open = self.count_ids
        action = self.sudo().env.ref('setu_inventory_count_management.new_inventory_count_act_window').read()[0]
        if len(count_to_open) > 1:
            action['domain'] = [('id', 'in', count_to_open.ids)]
        elif len(count_to_open) == 1:
            action['views'] = [(self.sudo().env.ref(
                'setu_inventory_count_management.setu_stock_inventory_count_form_view').id, 'form')]
            action['res_id'] = count_to_open.ids[0]
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['name'] = self.env['ir.sequence'].next_by_code('setu.inventory.count.seq')
            warehouse = self.env['stock.warehouse'].browse(vals.get('warehouse_id'))
            company = warehouse.company_id or self.env.company
            candidates = self._get_approver_candidates(company)

            approver = self.env['res.users'].browse(vals.get('approver_id')).exists()
            if not approver or approver not in candidates:
                preferred = self.env.user if self.env.user in candidates else candidates[:1]
                if preferred:
                    vals['approver_id'] = preferred.id

        records = super(StockInvCount, self).create(vals_list)
        for record in records.filtered(lambda count: not count.approver_id):
            raise ValidationError(_(
                "No existe un usuario controlador activo para la compañía %s. "
                "Asigne al menos un usuario al grupo Responsable de Conteo de Inventario."
            ) % (record.company_id.display_name or self.env.company.display_name))

        # 6.8.0: cada conteo conserva su propia fotografía persistente del stock.
        # Se prepara una sola vez al crear el documento; las sesiones solo
        # alimentan este universo y el panel deja de consultar stock.quant.
        records.filtered(lambda count: count.warehouse_id and count.location_id)._prepare_inventory_snapshot()
        return records

    def create_session(self):
        if self.type == 'Multi Session':
            is_multi_session = True
        else:
            is_multi_session = False
        session_creator_wiz = self.env['setu.inventory.session.creator'].create({'inventory_count_id': self.id,
                                                                                 'is_multi_session': is_multi_session})
        products = self.product_ids.ids
        session_creator_wiz.write({'product_ids': [(6, 0, products)]})

        return {'name': 'Create Session',
                'view_type': 'form',
                'view_mode': 'form',
                'context': {'products': products},
                'res_model': 'setu.inventory.session.creator',
                'type': 'ir.actions.act_window',
                'view_id': self.sudo().env.ref(
                    'setu_inventory_count_management.setu_inventory_session_creator_form_view').id,
                'res_id': session_creator_wiz.id,
                'target': 'new'}

    def create_re_count(self):
        session_creator_wiz = self.env['setu.inventory.session.validate.wizard'].create({})
        return {'name': 'Create Inventory Count',
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'setu.inventory.session.validate.wizard',
                'type': 'ir.actions.act_window',
                'view_id': self.sudo().env.ref(
                    'setu_inventory_count_management.setu_inventory_session_reject_recount_validate_form_view').id,
                'res_id': session_creator_wiz.id,
                'target': 'new'}

    def reject_inventory_count(self):
        self.state = 'Rejected'
        for session in self.session_ids:
            session.state = 'Cancel'

    def action_open_inventory_adj(self):
        inventory_adjs = self.inventory_adj_ids
        action = self.sudo().env.ref('setu_inventory_count_management.setu_stock_inventory_act_window').read()[0]
        if len(inventory_adjs) > 1:
            action['domain'] = [('id', 'in', inventory_adjs.ids)]
        elif len(inventory_adjs) == 1:
            action['views'] = [
                (self.sudo().env.ref('setu_inventory_count_management.setu_stock_inventory_form_view').id, 'form')]
            action['res_id'] = inventory_adjs.ids[0]
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

    def approve_inventory_count(self):
        session_ids = self.session_ids.filtered(lambda s: s.state != 'Cancel')
        session_states = session_ids.mapped('state')
        if any(state in session_states for state in ('Draft', 'In Progress', 'Submitted')):
            raise ValidationError(
                _("Valide todas las sesiones antes de aprobar el conteo.")
            )

        # Check count lines for pending review or rejection
        rejected_lines = self.line_ids.filtered(lambda p: p.state == 'Reject')
        pending_lines = self.line_ids.filtered(lambda p: p.state == 'Pending Review')
        if pending_lines:
            raise ValidationError(
                _('Please check and set the state in all count lines of this count to open this count again.'))
        if rejected_lines:
            return {
                'name': 'Rejected Lines Found!!!',
                'view_mode': 'form',
                'view_id': self.sudo().env.ref(
                    'setu_inventory_count_management.setu_inventory_session_reject_recount_validate_form_view').id,
                'res_model': 'setu.inventory.session.validate.wizard',
                'type': 'ir.actions.act_window',
                'target': 'new'
            }
        self.state = 'Approved'
        self.create_inventory_adj()

    def unlink(self):
        for count in self:
            if count.state != 'Draft':
                raise ValidationError(_(f'You cannot delete the Inventory Count once it is in {count.state} state.'))
        if self.session_ids:
            self.session_ids.with_context(from_count=True).unlink()
        return super(StockInvCount, self).unlink()

    def create_inventory_adj(self):
        if self.type == 'Single Session':
            lines_to_adjust = self.line_ids.filtered(lambda l: l.is_discrepancy_found)
        else:
            lines_to_adjust = self.line_ids.filtered(lambda l: l.is_discrepancy_found and l.state == 'Approve')
        if lines_to_adjust:
            self._create_inventory_adj(lines_to_adjust)
            try:
                self.message_post(
                    body=Markup("<div style='color:red; margin:10px 30px;;'>&bull; %s <strong>%s</strong>%s</div>") % (
                        _('Se encontró una discrepancia.'),
                        _('Inventory Adjustment'),
                        _(' is created.')
                    ))
            except Exception as e:
                pass
        else:
            try:
                self.message_post(
                    body=Markup(
                        "<div style='color:green; margin:10px 30px;;'>&bull; %s <strong>%s</strong> %s</div>") % (
                             _('No se encontraron discrepancias.'),
                             _('Inventory Adjustment'),
                             _('is not created.')
                         ))
            except Exception as e:
                pass

    def get_all_counts(self):
        list = [self.id]
        while True:
            if self.count_id:
                list.append(self.count_id.id)
                list_2 = self.count_id.get_all_counts()
                if list_2:
                    list.extend(list_2)
            break
        return set(list)

    def _create_inventory_adj(self, count_lines):
        if count_lines:
            lines = []
            for l in count_lines:
                if l.product_id.tracking != 'serial':
                    lines.append((
                        0, 0, {'product_id': l.product_id.id, 'product_uom_id': l.product_id.uom_id.id,
                               'location_id': l.location_id.id, 'product_qty': l.counted_qty,
                               'prod_lot_id': l.lot_id.id if l.lot_id else False,
                               'theoretical_qty': l.qty_in_stock}))
                else:
                    if l.serial_number_ids:
                        existing_serial_numbers = self.env['stock.quant'].sudo().search(
                            [('location_id', '=', l.location_id.id),
                             ('lot_id', 'in', l.serial_number_ids.ids),
                             ('product_id', '=', l.product_id.id)])
                        settlement_serial_ids = l.serial_number_ids - existing_serial_numbers.lot_id
                        for s in settlement_serial_ids:
                            lot_exists = self.env['stock.quant'].sudo().search(
                                [('location_id', '=', l.location_id.id),
                                 ('lot_id', '=', s.id),
                                 ('product_id', '=', l.product_id.id)]).mapped('lot_id')
                            lines.append((
                                0, 0, {'product_id': l.product_id.id, 'product_uom_id': l.product_id.uom_id.id,
                                       'location_id': l.location_id.id, 'product_qty': 1,
                                       'prod_lot_id': l.lot_id.id if l.lot_id else False,
                                       'serial_number_ids': [(6, 0, s.ids)],
                                       'theoretical_qty': s.product_qty if lot_exists else 0}))
                    if l.not_found_serial_number_ids:
                        for m in l.not_found_serial_number_ids:
                            lot_exists = self.env['stock.quant'].sudo().search(
                                [('location_id', '=', l.location_id.id),
                                 ('lot_id', '=', m.id),
                                 ('quantity', '>', 0),
                                 ('product_id', '=', l.product_id.id)]).mapped('lot_id')
                            lines.append((
                                0, 0, {'product_id': l.product_id.id, 'product_uom_id': l.product_id.uom_id.id,
                                       'location_id': l.location_id.id, 'product_qty': 0,
                                       'prod_lot_id': l.lot_id.id if l.lot_id else False,
                                       'serial_number_ids': [(6, 0, m.ids)],
                                       'theoretical_qty': m.product_qty if lot_exists else 0}))

            adj = self.env['setu.stock.inventory'].create({
                'location_id': self.location_id.id,
                'name': 'ADJ - ' + self.name,
                'inventory_count_id': self.id,
                'partner_id': self.approver_id.id,
                'date': self.inventory_count_date,
                'line_ids': lines
            })
            adj.inventory_count_id = self
            adj.action_start()
            adj.product_ids = count_lines.mapped('product_id')

    def _create_inventory_adj_old(self, count_lines):
        if count_lines:
            lines = []
            for l in count_lines:
                if l.product_id.tracking == 'serial':
                    lot_ids = self.env['stock.quant'].sudo().search(
                        [('location_id', '=', l.location_id.id),
                         ('quantity', '=', 1),
                         ('product_id', '=', l.product_id.id)]).mapped('lot_id')
                    new_serial = (l.serial_number_ids) - (lot_ids - l.not_found_serial_number_ids)
                lines.append((
                    0, 0, {'product_id': l.product_id.id, 'product_uom_id': l.product_id.uom_id.id,
                           'location_id': l.location_id.id, 'product_qty': l.counted_qty,
                           'prod_lot_id': l.lot_id.id if l.lot_id else False,
                           'not_found_serial_number_ids': [(6, 0, l.not_found_serial_number_ids.ids)],
                           'new_serial_number_ids': [(6, 0, new_serial.ids)],
                           # 'new_serial_count': new_serial_count,
                           'serial_number_ids': [(6, 0, l.serial_number_ids.ids)],
                           'theoretical_qty': l.qty_in_stock}))
            adj = self.env['setu.stock.inventory'].create({
                'location_id': self.location_id.id,
                'name': 'ADJ - ' + self.name,
                'inventory_count_id': self.id,
                'partner_id': self.approver_id.id,
                'date': self.inventory_count_date,
                'line_ids': lines
            })
            adj.inventory_count_id = self
            adj.action_start()
            adj.product_ids = count_lines.mapped('product_id')

    @api.depends('warehouse_id')
    def _compute_warehouse_id(self):
        for record in self:
            if record.warehouse_id:
                warehouse_id = record.warehouse_id
                view_location_id = record.warehouse_id.view_location_id
                locations = self.env['stock.location'].sudo().search(
                    [('warehouse_id', '=', warehouse_id), ('usage', '=', 'internal')])
                record.locations_ids = locations if locations else False
            else:
                locations = record.env['stock.location'].sudo().search(
                    [('usage', '=', 'internal'), ('company_id', 'in', self.env.companies.ids)])
                record.locations_ids = locations

    @api.onchange('location_id')
    def onchange_location_id(self):
        if self.location_id:
            domain = [('view_location_id', 'parent_of', self.location_id.id)]
            wh = self.env['stock.warehouse'].search(domain)
            return {'value': {
                'warehouse_id': wh.id}}

    @api.onchange('warehouse_id')
    def onchange_warehouse_id(self):
        if self.warehouse_id:
            candidates = self._get_approver_candidates(self.warehouse_id.company_id)
            if self.approver_id not in candidates:
                self.approver_id = self.env.user if self.env.user in candidates else candidates[:1]
            self.location_id = self.warehouse_id.lot_stock_id

    @api.depends('warehouse_id', 'company_id')
    def _compute_approver_id(self):
        for record in self:
            company = record.company_id or record.warehouse_id.company_id or self.env.company
            record.approver_ids = record._get_approver_candidates(company)

    @api.model
    def get_counted_products(self, domain, user_ids=None):
        domain = domain + [('state', 'in', ['Approved', 'Inventory Adjusted'])]
        counts = self.search(domain)
        line_domain = [('inventory_count_id', 'in', counts.ids)]
        if user_ids:
            line_domain.append(('user_ids', 'in', user_ids))
        count_lines = self.env['setu.stock.inventory.count.line'].search(line_domain)
        product_ids = count_lines.mapped('product_id.id')
        return list(set(product_ids)) or []
