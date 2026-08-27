# -*- coding: utf-8 -*-
from odoo import fields, models, api


class StockMove(models.Model):
    _inherit = 'stock.move'

    inventory_adj_id = fields.Many2one(comodel_name="setu.stock.inventory", string="Inventory Adjustment")
    inventory_count_id = fields.Many2one(comodel_name="setu.stock.inventory.count", string="Inventory Count")

    @api.model_create_multi
    def create(self, vals_list):
        inventory_adj_id = self._context.get('adj_context', False)
        if inventory_adj_id:
            inventory_adj_id = self.env['setu.stock.inventory'].sudo().browse(inventory_adj_id)
            for vals in vals_list:
                vals.update({'inventory_adj_id': inventory_adj_id.id,
                             'inventory_count_id': inventory_adj_id.inventory_count_id.id,
                             'origin': inventory_adj_id.name})
        return super().create(vals_list)

    # def _prepare_account_move_vals(self, credit_account_id, debit_account_id, journal_id, qty, description, svl_id,
    #                                cost):
    #     self.ensure_one()
    #     inventory_count_id = self.sudo().inventory_adj_id and self.sudo().inventory_adj_id.inventory_count_id or False
    #     if inventory_count_id and inventory_count_id.name:
    #         svl = self.env['stock.valuation.layer'].sudo().browse(svl_id)
    #         description = 'Inventory Adjustment - ' + inventory_count_id.name + ' - ' + svl.product_id.name
    #     res = super()._prepare_account_move_vals(credit_account_id=credit_account_id, debit_account_id=debit_account_id,
    #                                              journal_id=journal_id, qty=qty,
    #                                              description=description, svl_id=svl_id, cost=cost)
    #
    #     return res
    def _check_inventory_count_warehouse_lock(self):
        Count = self.env['setu.stock.inventory.count']
        for move in self:
            locations = move.location_id | move.location_dest_id
            locked_count = Count._get_locked_count_for_locations(
                locations,
                company=move.company_id,
            )
            if locked_count:
                from odoo.exceptions import UserError
                from odoo import _
                raise UserError(_(
                    'El almacén %(warehouse)s está bloqueado por el conteo %(count)s. '
                    'No se permiten reservas ni movimientos hacia o desde este almacén '
                    'hasta que el conteo sea aprobado.'
                ) % {
                    'warehouse': locked_count.warehouse_id.display_name,
                    'count': locked_count.display_name,
                })
        return True

    def _action_assign(self, *args, **kwargs):
        self._check_inventory_count_warehouse_lock()
        return super()._action_assign(*args, **kwargs)

    def _action_done(self, *args, **kwargs):
        self._check_inventory_count_warehouse_lock()
        return super()._action_done(*args, **kwargs)

