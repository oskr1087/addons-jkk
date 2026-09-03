from odoo import models


class StockRule(models.Model):
    _inherit = 'stock.rule'

    def _run_manufacture(self, procurements):
        """Hold only manufacturing launched directly from sale confirmation.

        Sale delivery/procurement remains standard. Purchase rules are not
        modified. Component manufacturing launched later by MRP is unaffected
        because it does not run with the sale-specific APS context.
        """
        if self.env.context.get('aps_hold_sale_mto_manufacturing'):
            return True
        return super()._run_manufacture(procurements)
