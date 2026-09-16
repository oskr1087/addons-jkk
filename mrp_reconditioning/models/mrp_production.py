from odoo import fields, models, _
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools.float_utils import float_compare


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    is_reconditioning = fields.Boolean(string="Es reacondicionamiento", default=False, copy=False, index=True)
    reconditioning_id = fields.Many2one("mrp.reconditioning", string="Reacondicionamiento", readonly=True, copy=False, index=True, check_company=True)

    # Compatibilidad de migración con vistas de versiones 19.0.1.x/19.0.3.x.
    # Se mantienen temporalmente estos nombres técnicos para que Odoo pueda
    # validar las vistas heredadas antiguas durante -u mrp_reconditioning.
    reconditioning_source_lot_id = fields.Many2one(
        "stock.lot",
        string="Lote/Número de serie a reacondicionar (compatibilidad)",
        related="reconditioning_id.lot_id",
        readonly=True,
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lote/Número de serie (compatibilidad)",
        related="reconditioning_id.lot_id",
        readonly=True,
        help="Alias temporal para vistas de mrp.production creadas por versiones anteriores del módulo.",
    )
    reconditioning_available_qty = fields.Float(
        string="Disponible (compatibilidad)",
        related="reconditioning_id.available_qty",
        readonly=True,
    )
    reconditioning_extra_component_count = fields.Integer(
        string="Componentes adicionales (compatibilidad)",
        compute="_compute_reconditioning_extra_component_count_compat",
    )

    def _compute_reconditioning_extra_component_count_compat(self):
        for mo in self:
            mo.reconditioning_extra_component_count = len(
                mo.reconditioning_id.component_line_ids
            ) if mo.reconditioning_id else 0


    def _check_reconditioning_mo(self):
        for mo in self.filtered("is_reconditioning"):
            if not mo.reconditioning_id:
                raise UserError(_("La OF debe estar vinculada a un reacondicionamiento."))
            base = mo.move_raw_ids.filtered("is_reconditioning_return_component")
            if len(base) != 1 or base.product_id != mo.product_id:
                raise UserError(_("La OF debe contener exactamente el producto terminado como producto base."))
            lot = mo.reconditioning_id.lot_id
            base.lot_ids = [Command.set([lot.id])]
            mo.lot_producing_ids = [Command.set([lot.id])]
        return True

    def action_confirm(self):
        reacs = self.filtered("is_reconditioning")
        reacs._check_reconditioning_mo()
        result = super().action_confirm()
        reacs._check_reconditioning_mo()
        return result

    def action_start(self):
        self.filtered("is_reconditioning")._check_reconditioning_mo()
        return super().action_start()

    def button_mark_done(self):
        reacs = self.filtered("is_reconditioning")
        reacs._check_reconditioning_mo()
        for mo in reacs.filtered(lambda x: x.product_tracking == "lot"):
            dist = mo.lot_distribution_id
            if not dist or len(dist.line_ids) != 1 or dist.line_ids.lot_id != mo.reconditioning_id.lot_id:
                raise UserError(_("El lote de salida debe ser el mismo lote del reacondicionamiento."))
            if float_compare(dist.total_quantity, mo.qty_producing,
                             precision_rounding=mo.product_uom_id.rounding or 0.01):
                raise UserError(_("La distribución de lotes no coincide con la cantidad a producir."))
        result = super().button_mark_done()
        for mo in reacs.filtered(lambda x: x.state == "done"):
            mo.reconditioning_id.state = "done"
        return result

    def action_open_reconditioning(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Reacondicionamiento"),
                "res_model": "mrp.reconditioning", "res_id": self.reconditioning_id.id,
                "view_mode": "form", "target": "current"}
