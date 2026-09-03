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
    count_id = fields.Many2one(
        comodel_name="setu.stock.inventory.count",
        readonly=True,
        copy=False,
        string="Conteo origen",
        index=True,
    )
    is_recount = fields.Boolean(
        string="Es reconteo",
        compute="_compute_recount_traceability",
        store=True,
        index=True,
    )
    root_count_id = fields.Many2one(
        comodel_name="setu.stock.inventory.count",
        string="Conteo principal",
        compute="_compute_recount_traceability",
        store=True,
        readonly=True,
        index=True,
    )
    recount_level = fields.Integer(
        string="Nivel de reconteo",
        compute="_compute_recount_traceability",
        store=True,
        readonly=True,
    )


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

    @api.depends("count_id", "count_id.root_count_id", "count_id.recount_level")
    def _compute_recount_traceability(self):
        for rec in self:
            rec.is_recount = bool(rec.count_id)
            if not rec.count_id:
                rec.root_count_id = rec
                rec.recount_level = 0
            else:
                rec.root_count_id = rec.count_id.root_count_id or rec.count_id
                rec.recount_level = rec.count_id.recount_level + 1

    def action_open_parent_count(self):
        self.ensure_one()
        if not self.count_id:
            return {"type": "ir.actions.act_window_close"}
        return {
            "type": "ir.actions.act_window",
            "name": _("Conteo origen"),
            "res_model": "setu.stock.inventory.count",
            "res_id": self.count_id.id,
            "view_mode": "form",
            "target": "current",
        }

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
            and manager_group in current.group_ids
            and (not company or company in current.company_ids)
        ):
            users |= current
        # Preserve the explicitly selected controller even when group membership
        # was changed in the same transaction (common during imports/tests).
        explicit = self.mapped('approver_id').filtered(
            lambda u: u.active and not u.share
        ) if self else self.env['res.users']
        users |= explicit
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
        self.ensure_one()
        if self.count_id:
            raise ValidationError(
                _("Un reconteo no puede generar otro reconteo. Regrese al conteo principal.")
            )
        rejected_lines = self.line_ids.filtered(lambda line: line.state == 'Reject')
        if not rejected_lines:
            raise ValidationError(_("No existen líneas rechazadas para crear un reconteo."))

        new_count = self.env['setu.stock.inventory.count'].with_context(
            setu_creating_recount=True,
        ).create({
            'approver_id': self.approver_id.id,
            'count_id': self.id,
            'location_id': self.location_id.id,
            'warehouse_id': self.warehouse_id.id,
            'use_barcode_scanner': self.use_barcode_scanner,
            'type': 'Multi Session',
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

        source_map = {
            (
                snap.product_id.id,
                snap.location_id.id,
                snap.lot_id.id if snap.lot_id else False,
            ): snap
            for snap in self.snapshot_line_ids
        }
        grouped = {}
        for line in rejected_lines:
            product=line.product_id
            location=line.location_id
            tracking=product.tracking

            if tracking == 'serial':
                serials=line.serial_number_ids | line.not_found_serial_number_ids
                for serial in serials:
                    key=('serial',product.id,location.id,serial.id)
                    source=source_map.get((product.id,location.id,serial.id))
                    grouped.setdefault(key,{
                        'product':product,
                        'location':location,
                        'lot':serial,
                        'tracking':tracking,
                        'expected_qty':source.expected_qty if source else 1.0,
                        'unit_cost':source.unit_cost if source else product.with_company(self.company_id).standard_price,
                    })
                continue

            lot=line.lot_id if tracking == 'lot' else self.env['stock.lot']
            key=(tracking,product.id,location.id,lot.id if lot else False)
            if key not in grouped:
                source=source_map.get((product.id,location.id,lot.id if lot else False))
                grouped[key]={
                    'product':product,
                    'location':location,
                    'lot':lot,
                    'tracking':tracking,
                    'expected_qty':source.expected_qty if source else line.theoretical_qty,
                    'unit_cost':source.unit_cost if source else product.with_company(self.company_id).standard_price,
                }

        header=new_count._get_snapshot_header(create=True)
        snapshot_vals=[{
            'snapshot_id':header.id,
            'product_id':data['product'].id,
            'lot_id':data['lot'].id if data['lot'] else False,
            'location_id':data['location'].id,
            'expected_qty':data['expected_qty'],
            'unit_cost':data['unit_cost'],
            'counted_qty':0.0,
            'difference_qty':-data['expected_qty'],
            'scan_count':0,
            'status':'pending',
            'unexpected':False,
            'duplicate':False,
        } for data in grouped.values()]
        if snapshot_vals:
            self.env['setu.inventory.count.snapshot.line'].sudo().create(snapshot_vals)
        header.write({
            'ready':True,
            'snapshot_date':fields.Datetime.now(),
        })
        new_count._refresh_persistent_kpis()

        vals_list=[]
        for data in grouped.values():
            vals={
                'product_id':data['product'].id,
                'location_id':data['location'].id,
                'date_of_scanning':fields.Datetime.now(),
                'session_id':new_session.id,
                'inventory_count_id':new_count.id,
                'is_multi_session':new_session.is_multi_session,
                'theoretical_qty':data['expected_qty'],
                'scanned_qty':0.0,
                'product_scanned':False,
            }
            if data['tracking']=='lot':
                vals['lot_id']=data['lot'].id if data['lot'] else False
            elif data['tracking']=='serial':
                vals['serial_number_ids']=[(6,0,data['lot'].ids)]
                vals['theoretical_qty']=1.0
            vals_list.append(vals)

        if vals_list:
            self.env['setu.inventory.count.session.line'].with_context(
                setu_bulk_count=True,
            ).create(vals_list)

        self.message_post(
            body=_(
                "Se creó el reconteo %(recount)s con %(items)s posiciones. "
                "El reconteo no aparecerá en las vistas operativas generales."
            ) % {"recount": new_count.display_name, "items": len(vals_list)}
        )
        new_count.message_post(
            body=_(
                "Reconteo creado desde %(origin)s. Al aprobarlo, sus resultados regresarán "
                "al conteo principal y este documento no generará ajuste de inventario."
            ) % {"origin": self.display_name}
        )
        return {
            'type':'ir.actions.act_window',
            'name':_('Reconteo'),
            'res_model':'setu.stock.inventory.count',
            'res_id':new_count.id,
            'view_mode':'form',
            'target':'current',
        }

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
            manager_group = self.env.ref(
                'setu_inventory_count_management.group_setu_inventory_count_manager'
            )
            approver_is_valid = bool(
                approver
                and approver.active
                and not approver.share
                and manager_group in approver.group_ids
            )
            if not approver_is_valid:
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
        if not self.env.context.get('setu_creating_recount'):
            records.filtered(
                lambda count: count.warehouse_id and count.location_id
            )._prepare_inventory_snapshot()
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

        return {'name': 'Crear sesión',
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
        return {'name': 'Crear reconteo',
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
        self.ensure_one()
        sessions = self.session_ids.filtered(lambda s: s.state != 'Cancel')
        if sessions.filtered(lambda s: s.state != 'Done'):
            raise ValidationError(
                _("Aún existen sesiones abiertas. Finalice las sesiones antes de aprobar.")
            )

        if self.count_id:
            self._consolidate_recount_into_parent()
            self.state = 'Approved'
            self.message_post(
                body=_("Reconteo aprobado. Los resultados fueron consolidados en %s.") % self.count_id.display_name
            )
            return True

        rejected_lines = self.line_ids.filtered(lambda p: p.state == 'Reject')
        if rejected_lines:
            raise ValidationError(
                _("Existen líneas enviadas a reconteo. Apruebe primero el reconteo correspondiente.")
            )

        # El snapshot persistente es la fuente de verdad del flujo moderno.
        # Las líneas legacy se conservan para compatibilidad y para generar el
        # ajuste, pero NO deben decidir por sí solas si el conteo está bloqueado.
        self._refresh_persistent_kpis()
        snapshot_pending_decision = self.snapshot_line_ids.filtered(
            lambda line: line.status in ("difference", "zero", "unexpected")
        )

        accept_all = self.env.context.get("setu_accept_all_differences")

        # Si el usuario aceptó explícitamente las diferencias, o si el snapshot
        # ya no tiene ninguna diferencia por decidir, cualquier Pending Review
        # legacy es residual y debe normalizarse automáticamente.
        if accept_all or not snapshot_pending_decision:
            pending_lines = self.line_ids.filtered(
                lambda line: line.state == 'Pending Review'
            )
            if pending_lines:
                pending_lines.write({"state": "Approve"})

            pending_session_lines = self.session_ids.mapped(
                "session_line_ids"
            ).filtered(
                lambda line: line.state == 'Pending Review'
            )
            if pending_session_lines:
                pending_session_lines.write({"state": "Approve"})

            self.flush_recordset()
            self.line_ids.flush_recordset(["state"])
            self.invalidate_recordset()
            self.line_ids.invalidate_recordset(["state"])

        # Solo el snapshot puede bloquear por diferencias pendientes.
        if snapshot_pending_decision and not accept_all:
            raise ValidationError(
                _("Existen diferencias pendientes de decisión. Use «Aceptar diferencias y aprobar» o «Recontar diferencias».")
            )

        # Protección adicional: si después de normalizar quedara una línea
        # legacy pendiente pero el snapshot está limpio, se corrige en silencio.
        stale_pending = self.line_ids.filtered(
            lambda line: line.state == 'Pending Review'
        )
        if stale_pending and not snapshot_pending_decision:
            stale_pending.write({"state": "Approve"})

        self.state = 'Approved'
        self.create_inventory_adj()
        return True

    def unlink(self):
        for count in self:
            if count.state != 'Draft':
                raise ValidationError(_(f'No puede eliminar el conteo de inventario cuando está en estado {count.state}.'))
        if self.session_ids:
            self.session_ids.with_context(from_count=True).unlink()
        return super(StockInvCount, self).unlink()

    def _consolidate_recount_into_parent(self):
        self.ensure_one()
        parent = self.count_id
        if not parent:
            return True

        Snapshot = self.env["setu.inventory.count.snapshot.line"].sudo()
        updated = 0
        unresolved = 0

        for child in self.snapshot_line_ids:
            parent_line = Snapshot.search([
                ("count_id", "=", parent.id),
                ("product_id", "=", child.product_id.id),
                ("location_id", "=", child.location_id.id),
                ("lot_id", "=", child.lot_id.id if child.lot_id else False),
            ], limit=1)
            if not parent_line:
                continue

            parent_line.write({
                "counted_qty": child.counted_qty,
                "difference_qty": child.counted_qty - parent_line.expected_qty,
                "scan_count": max(child.scan_count, 1 if child.status != "pending" else 0),
                "status": child.status,
                "duplicate": child.duplicate,
                "recount_required": False,
            })
            updated += 1

            count_line = parent._find_count_line_for_snapshot(parent_line)
            if child.status == "matched":
                if count_line:
                    count_line.write({
                        "counted_qty": child.counted_qty,
                        "state": "Approve",
                    })
            elif child.status in ("difference", "zero", "unexpected"):
                count_line = parent._ensure_count_line_for_snapshot_adjustment(parent_line)
                count_line.write({"state": "Pending Review"})
                unresolved += 1

        parent._refresh_persistent_kpis()
        parent.message_post(
            body=_(
                "Reconteo %(recount)s aprobado: %(updated)s posiciones consolidadas; "
                "%(unresolved)s continúan con divergencia."
            ) % {
                "recount": self.display_name,
                "updated": updated,
                "unresolved": unresolved,
            }
        )
        return True

    def create_inventory_adj(self):
        self.ensure_one()

        # El snapshot persistente es la fuente de verdad. Materializamos antes
        # cualquier divergencia aceptada que aún no tenga línea de control.
        snapshot_candidates = self.snapshot_line_ids.filtered(
            lambda line: (
                line.status in ("difference", "zero", "unexpected")
                and not line.relocation_resolved
            )
        )
        for snapshot_line in snapshot_candidates:
            self._ensure_count_line_for_snapshot_adjustment(snapshot_line)

        # Solo diferencias aprobadas; nunca líneas rechazadas para reconteo.
        lines_to_adjust = self.line_ids.filtered(
            lambda line: (
                line.state == 'Approve'
                and (
                    line.is_discrepancy_found
                    or line.counted_qty != line.qty_in_stock
                    or (
                        line.product_id.tracking == 'serial'
                        and (line.serial_number_ids or line.not_found_serial_number_ids)
                    )
                )
            )
        )
        if lines_to_adjust:
            self._create_inventory_adj(lines_to_adjust)
            try:
                self.message_post(
                    body=Markup("<div style='color:red; margin:10px 30px;;'>&bull; %s <strong>%s</strong>%s</div>") % (
                        _('Se encontró una discrepancia.'),
                        _('Ajuste de inventario'),
                        _(' fue creado.')
                    ))
            except Exception as e:
                pass
        else:
            try:
                self.message_post(
                    body=Markup(
                        "<div style='color:green; margin:10px 30px;;'>&bull; %s <strong>%s</strong> %s</div>") % (
                             _('No se encontraron discrepancias.'),
                             _('Ajuste de inventario'),
                             _('no fue creado.')
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

            auto_apply = self.env['ir.config_parameter'].sudo().get_param(
                'setu_inventory_count_management.auto_inventory_adjustment'
            )
            if str(auto_apply).lower() in ('true', '1', 'yes'):
                adj.action_validate()

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
                    [('warehouse_id', '=', warehouse_id.id), ('usage', '=', 'internal')])
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

    @api.depends('warehouse_id', 'company_id', 'approver_id')
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
