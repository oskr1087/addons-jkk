# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import ValidationError


class SessionCreatorPDA(models.TransientModel):
    _inherit = 'setu.inventory.session.creator'

    def confirm(self, users=False):
        self.ensure_one()
        assigned_users = self.user_ids or users or self.env.user

        count = self.inventory_count_id
        if count.count_id:
            return super().confirm(users=users)

        session = self.env['setu.inventory.count.session'].create({
            'is_multi_session': count.type == 'Multi Session',
            'inventory_count_id': count.id,
            'location_id': count.location_id.id,
            'warehouse_id': count.warehouse_id.id,
            'use_barcode_scanner': True,
            'user_ids': [(6, 0, assigned_users.ids)],
        })

        return session.action_open_mobile_count()

