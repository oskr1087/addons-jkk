# -*- coding: utf-8 -*-
from datetime import datetime
from datetime import timedelta

from odoo import fields, models, api
from odoo.exceptions import ValidationError


class StockInvCountPlanner(models.Model):
    _name = 'setu.stock.inventory.count.planner'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _description = 'Stock Inventory Count Planner'

    use_barcode_scanner = fields.Boolean(default=False, string="Usar escáner de códigos")
    active = fields.Boolean(default=True, string="Activo")

    name = fields.Char(string="Nombre")

    planing_frequency = fields.Integer(string="Frecuencia de planificación (días)")
    past_history_days = fields.Integer(string="Días de historial previo", default="365")

    inventory_count_date = fields.Date(default=fields.Datetime.now, string="Fecha")
    next_execution_date = fields.Date(string="Próxima fecha de ejecución", default=fields.Date.today)
    previous_execution_date = fields.Date(string="Fecha de ejecución anterior", default=fields.Date.today)

    type = fields.Selection([('Single Session', 'Sesión única'), ('Multi Session', 'Múltiples sesiones')],
                            default='Single Session', required=True, string="Tipo")

    state = fields.Selection([('draft', 'Borrador'), ('verified', 'Verificado')],
                             default="draft", string="Estado", help="Indica el estado actual del proceso.")

    approver_id = fields.Many2one(comodel_name="res.users", string="Controlador", default=lambda self: self._default_approver())
    warehouse_id = fields.Many2one(comodel_name="stock.warehouse", string="Almacén")
    location_id = fields.Many2one(comodel_name="stock.location", string="Ubicación")

    locations_ids = fields.Many2many('stock.location', string='Ubicaciones', compute='_compute_warehouse_id', store=True)
    product_ids = fields.Many2many(comodel_name="product.product", string="Productos")
    approver_ids = fields.Many2many(comodel_name="res.users", compute='_compute_approver_id', string="Controladores")
    company_id = fields.Many2one(comodel_name="res.company", related="warehouse_id.company_id", string="Compañía",
                                 store=True)
    
    def _get_approver_candidates(self, company=None):
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

    def reset_to_draft(self):
        self.state = 'draft'

    @api.depends('warehouse_id')
    def _compute_warehouse_id(self):
        for record in self:
            warehouse_id= record.warehouse_id
            if warehouse_id:
                locations = self.env['stock.location'].search(
                    [('warehouse_id', '=', warehouse_id),
                     ('usage', '=', 'internal')])
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

    @api.depends('warehouse_id', 'company_id')
    def _compute_approver_id(self):
        for record in self:
            company = record.company_id or record.warehouse_id.company_id or self.env.company
            record.approver_ids = record._get_approver_candidates(company)

    @api.onchange('warehouse_id')
    def _onchange_warehouse_controller(self):
        for record in self:
            if not record.warehouse_id:
                continue
            candidates = record._get_approver_candidates(record.warehouse_id.company_id)
            if record.approver_id not in candidates:
                record.approver_id = self.env.user if self.env.user in candidates else candidates[:1]

    def auto_create_inventory_count_record(self):
        records = self.search([('next_execution_date', '<=', datetime.today().date()), ('state', '=', 'verified')])
        for record in records:
            record.create_inventory_count_record()
        return True

    def verify_inventory_count_planing(self):
        if self.planing_frequency <= 0:
            raise ValidationError('Ingrese una frecuencia de días válida.')
        self.write({'state': 'verified'})
        return True

    def set_products_in_inventory_count(self, product_ids):
        count = self.env['setu.stock.inventory.count'].browse(self.env.context.get('active_id', False))
        product_ids = self.env['product.product'].browse(product_ids)
        count.product_ids |= product_ids

    def create_inventory_count(self):
        self.create_inventory_count_record()
        return True

    def create_inventory_count_record(self):
        inventory_count_obj = self.env['setu.stock.inventory.count']
        vendor_product_dict = self.get_approver_product_mapping_dict()
        for approver_id, product_ids in vendor_product_dict.items():
            vals = self.prepare_vales_for_inventory_count(approver_id, product_ids)
            rec = inventory_count_obj.search([('planner_id', '=', self.id), ('state', '=', 'draft')])
            if rec:
                rec.product_ids and rec.product_ids.unlink()
                rec.write(vals)
            else:
                mail_obj = self.env['mail.mail']
                data = {'planner_id': self.id}
                rec = inventory_count_obj.create(vals)
                if rec.approver_id.partner_id not in rec.message_follower_ids.mapped('partner_id'):
                    data.update({'message_follower_ids': [(4, rec.approver_id.partner_id.id)]})
                rec.write(data)
                email_template = self.sudo().sudo().env.ref(
                    'setu_inventory_count_management.`mail_template_request_for_inventory_count`', False)
                rec.message_follower_ids.mapped('partner_id')
                mail_mail = email_template and email_template.send_mail(rec.id) or False
                mail_mail = mail_mail and mail_obj.sudo().browse(mail_mail)
                if mail_mail:
                    mail_mail.recipient_ids = [(6, 0, [rec.approver_id.partner_id.id])]
                    mail_mail.send()
            self.write({'previous_execution_date': datetime.today().date(),
                        'next_execution_date': datetime.today().date() + timedelta(days=self.planing_frequency)
                        })
            if product_ids:
                self.set_products_in_inventory_count(product_ids)

    def get_approver_product_mapping_dict(self):
        approver_product_dict = {}
        if self.approver_id:
            approver_product_dict.update({self.approver_id.id: self.product_ids.ids})
        return approver_product_dict

    def prepare_vales_for_inventory_count(self, approver, product_list):
        approver_id = self.env['res.users'].browse(approver)
        vals = {'planner_id': self.id,
                'approver_id': approver_id.id,
                'warehouse_id': self.warehouse_id.id,
                'type': self.type,
                'location_id': self.location_id.id,
                'product_ids': [(6, 0, product_list)],
                'use_barcode_scanner': self.use_barcode_scanner}

        return vals
