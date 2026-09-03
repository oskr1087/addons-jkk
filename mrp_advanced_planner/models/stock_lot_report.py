from urllib.parse import quote

from odoo import fields, models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    aps_pda_qr_value = fields.Char(
        string='QR PDA',
        compute='_compute_aps_pda_qr_value',
    )

    def _compute_aps_pda_qr_value(self):
        for lot in self:
            lot.aps_pda_qr_value = lot._aps_pda_qr_payload()

    def _aps_pda_qty(self):
        """Physical quantity of this lot in internal locations.

        The QR is intended for inventory counting, so the quantity encoded is
        the current physical on-hand quantity of the lot in internal stock
        locations of the lot/company context.
        """
        self.ensure_one()
        Quant = self.env['stock.quant'].sudo()

        company = self.company_id or self.env.company
        quants = Quant.search([
            ('product_id', '=', self.product_id.id),
            ('lot_id', '=', self.id),
            ('location_id.usage', '=', 'internal'),
            ('company_id', '=', company.id),
        ])
        return sum(quants.mapped('quantity'))

    def _aps_pda_qr_payload(self):
        """Payload expected by the PDA count flow.

        Format:
            LOT/CODE/QUANTITY

        Example:
            10000/1090EV18IT/140.00
        """
        self.ensure_one()
        lot_name = self.name or ''
        product_code = self.product_id.default_code or ''
        quantity = self._aps_pda_qty()
        return '%s/%s/%.2f' % (
            lot_name,
            product_code,
            quantity,
        )

    def _aps_pda_qr_url(self, width=220, height=220):
        self.ensure_one()
        payload = quote(self._aps_pda_qr_payload(), safe='')
        return (
            '/report/barcode/?barcode_type=QR'
            '&value=%s&width=%s&height=%s&humanreadable=0'
            % (payload, int(width), int(height))
        )
