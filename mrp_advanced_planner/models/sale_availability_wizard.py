from odoo import api, fields, models, _


class MrpPlanningSaleAvailabilityWizard(models.TransientModel):
    _name = 'mrp.planning.sale.availability.wizard'
    _description = 'Disponibilidad y abastecimiento de línea de venta'

    sale_line_id = fields.Many2one('sale.order.line', string='Línea de venta', readonly=True)
    sale_order_id = fields.Many2one(related='sale_line_id.order_id', string='Pedido de venta', readonly=True)
    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Almacén', readonly=True)
    status = fields.Char(string='Estado de cobertura', readonly=True)
    status_key = fields.Selection([
        ('available', 'Disponible'),
        ('covered', 'Cubierto'),
        ('manufacturing', 'Por fabricación'),
        ('purchase', 'Por compra'),
        ('transfer', 'Por traslado'),
        ('mixed', 'Abastecimiento mixto'),
        ('partial', 'Cobertura parcial'),
        ('uncovered', 'Sin cubrir'),
    ], string='Estado', readonly=True)

    requested_qty = fields.Float(string='Pedido', readonly=True)
    delivered_qty = fields.Float(string='Entregado', readonly=True)
    pending_qty = fields.Float(string='Pendiente', readonly=True)
    coverage_qty = fields.Float(string='Cobertura', readonly=True)
    shortage_qty = fields.Float(string='Faltante', readonly=True)

    on_hand_qty = fields.Float(string='A mano', readonly=True)
    free_qty = fields.Float(string='Libre', readonly=True)
    incoming_qty = fields.Float(string='Entrante', readonly=True)
    outgoing_qty = fields.Float(string='Saliente', readonly=True)
    forecast_qty = fields.Float(string='Pronosticado', readonly=True)

    manufacturing_qty = fields.Float(string='En fabricación', readonly=True)
    purchase_qty = fields.Float(string='En compra', readonly=True)
    transfer_qty = fields.Float(string='En traslado APS', readonly=True)
    planned_qty = fields.Float(string='Planificado APS', readonly=True)
    supply_total_qty = fields.Float(
        string='Abastecimiento total', compute='_compute_summary', readonly=True
    )
    coverage_percent = fields.Float(
        string='% Cobertura', compute='_compute_summary', readonly=True
    )

    @api.depends(
        'requested_qty', 'delivered_qty', 'coverage_qty',
        'manufacturing_qty', 'purchase_qty', 'transfer_qty',
    )
    def _compute_summary(self):
        for wizard in self:
            wizard.supply_total_qty = (
                wizard.manufacturing_qty
                + wizard.purchase_qty
                + wizard.transfer_qty
            )
            pending = max(
                wizard.requested_qty - wizard.delivered_qty,
                0.0,
            )
            wizard.coverage_percent = (
                min((wizard.coverage_qty / pending) * 100.0, 100.0)
                if pending > 1e-6
                else 100.0
            )

    document_line_ids = fields.One2many(
        'mrp.planning.sale.availability.document', 'wizard_id',
        string='Documentos relacionados', readonly=True,
    )


class MrpPlanningSaleAvailabilityDocument(models.TransientModel):
    _name = 'mrp.planning.sale.availability.document'
    _description = 'Documento de abastecimiento relacionado con venta'
    _order = 'document_type, id'

    wizard_id = fields.Many2one(
        'mrp.planning.sale.availability.wizard', required=True, ondelete='cascade'
    )
    document_type = fields.Selection([
        ('plan', 'Planificación APS'),
        ('mo', 'Orden de fabricación'),
        ('po', 'Orden de compra'),
        ('transfer', 'Traslado'),
    ], string='Tipo', required=True, readonly=True)
    name = fields.Char(string='Documento', readonly=True)
    quantity = fields.Float(string='Cantidad', readonly=True)
    state_label = fields.Char(string='Estado', readonly=True)
    res_model = fields.Char(readonly=True)
    res_id = fields.Integer(readonly=True)

    def action_open_document(self):
        self.ensure_one()
        if not self.res_model or not self.res_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': self.name or _('Documento relacionado'),
            'res_model': self.res_model,
            'res_id': self.res_id,
            'views': [(False, 'form')],
            'view_mode': 'form',
            'target': 'current',
        }
