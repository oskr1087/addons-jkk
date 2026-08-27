from odoo import models, fields

class InventoryCountPivotWizard(models.TransientModel):
    _name = "setu.inventory.count.pivot.wizard"
    _description = "Inventory Count Pivot Wizard"

    start_date = fields.Date("Start Date")
    end_date = fields.Date("End Date")
    location_ids = fields.Many2many("stock.location", string="Ubicaciones")
    approver_ids = fields.Many2many("res.users", string="Approvers")

    def action_generate_report(self):
        domain = []
        if self.start_date:
            domain.append(('date', '>=', self.start_date))
        if self.end_date:
            domain.append(('date', '<=', self.end_date))
        if self.location_ids:
            domain.append(('location_id', 'in', self.location_ids.ids))
        if self.approver_ids:
            domain.append(('approver_id', 'in', self.approver_ids.ids))

        return {
            'type': 'ir.actions.act_window',
            'name': 'Inventory Discrepancy Pivot Report',
            'res_model': 'setu.inventory.count.pivot.report',
            'view_mode': 'pivot',
            'target': 'current',
            'domain': domain,
        }
