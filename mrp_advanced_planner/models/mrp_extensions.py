from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    advanced_plan_id = fields.Many2one('mrp.planning.plan', string='Planificación de origen', index=True, copy=False, readonly=True)
    planning_plan_line_id = fields.Many2one('mrp.planning.plan.line', string='Línea de planificación', index=True, copy=False, readonly=True)
    planning_sale_line_id = fields.Many2one('sale.order.line', string='Línea de venta origen', index=True, copy=False, readonly=True)
    planning_production_proposal_id = fields.Many2one('mrp.planning.production.proposal', string='Propuesta de planificación', index=True, copy=False, readonly=True)
    component_purchase_count = fields.Integer(
        string='Compras de componentes',
        compute='_compute_component_purchase_count',
    )

    def _compute_component_purchase_count(self):
        Purchase = self.env['purchase.order']
        for production in self:
            production.component_purchase_count = Purchase.search_count([
                ('mrp_production_id', '=', production.id)
            ])

    def action_open_component_purchases(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Compras de componentes - %s') % self.display_name,
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('mrp_production_id', '=', self.id)],
            'context': {'default_mrp_production_id': self.id},
        }

    def action_open_advanced_plan(self):
        self.ensure_one()
        if not self.advanced_plan_id:
            return False
        return {
            'type': 'ir.actions.act_window', 'name': _('Planificación de origen'),
            'res_model': 'mrp.planning.plan', 'view_mode': 'form', 'views': [(False, 'form')],
            'res_id': self.advanced_plan_id.id, 'target': 'current',
        }


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    advanced_plan_id = fields.Many2one('mrp.planning.plan', string='Planificación de origen', index=True, copy=False, readonly=True)
    mrp_production_id = fields.Many2one(
        'mrp.production',
        string='Orden de fabricación origen',
        index=True,
        copy=False,
        readonly=True,
    )

    def action_open_advanced_plan(self):
        self.ensure_one()
        if not self.advanced_plan_id:
            return False
        return {
            'type': 'ir.actions.act_window', 'name': _('Planificación de origen'),
            'res_model': 'mrp.planning.plan', 'res_id': self.advanced_plan_id.id,
            'view_mode': 'form', 'views': [(False, 'form')], 'target': 'current',
        }


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    planning_plan_line_id = fields.Many2one('mrp.planning.plan.line', string='Línea de planificación', index=True, copy=False, readonly=True)
    mrp_component_move_id = fields.Many2one(
        'stock.move',
        string='Componente de OF',
        index=True,
        copy=False,
        readonly=True,
    )


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    advanced_plan_id = fields.Many2one('mrp.planning.plan', string='Planificación de origen', index=True, copy=False, readonly=True)

    def action_open_advanced_plan(self):
        self.ensure_one()
        if not self.advanced_plan_id:
            return False
        return {
            'type': 'ir.actions.act_window', 'name': _('Planificación de origen'),
            'res_model': 'mrp.planning.plan', 'res_id': self.advanced_plan_id.id,
            'view_mode': 'form', 'views': [(False, 'form')], 'target': 'current',
        }


class StockMove(models.Model):
    _inherit = 'stock.move'

    planning_plan_line_id = fields.Many2one('mrp.planning.plan.line', string='Línea de planificación', index=True, copy=False, readonly=True)
    planning_purchase_vendor_id = fields.Many2one(
        'res.partner',
        string='Proveedor compra',
        domain="[('supplier_rank', '>', 0)]",
        help='Proveedor que se utilizará para comprar este componente. Puede ser cualquier proveedor activo de Odoo.',
    )
    planning_purchase_qty = fields.Float(
        string='Cantidad a comprar (legacy)',
        help='Campo conservado únicamente por compatibilidad con versiones anteriores.',
    )
    planning_can_purchase_component = fields.Boolean(
        string='Puede comprar componente',
        compute='_compute_planning_can_purchase_component',
    )
    planning_purchase_order_line_id = fields.Many2one(
        'purchase.order.line',
        string='Compra generada',
        copy=False,
        readonly=True,
    )

    def _planning_draft_purchase_supply(self, warehouse, to_date):
        """RFQ / to-approve supply is not yet represented by stock moves."""
        self.ensure_one()
        if not warehouse:
            return 0.0
        lines = self.env['purchase.order.line'].search([
            ('company_id', '=', self.company_id.id),
            ('product_id', '=', self.product_id.id),
            ('order_id.state', 'in', ('draft', 'sent', 'to approve')),
            ('order_id.picking_type_id.warehouse_id', '=', warehouse.id),
            '|',
            ('date_planned', '=', False),
            ('date_planned', '<=', to_date),
        ])
        total = 0.0
        for line in lines:
            pending = max((line.product_qty or 0.0) - (line.qty_received or 0.0), 0.0)
            total += line.product_uom_id._compute_quantity(
                pending, self.product_id.uom_id
            )
        return total

    def _planning_forecast_shortage(self):
        """Shortage after Odoo forecast + RFQs not yet represented as stock moves."""
        self.ensure_one()
        production = self.raw_material_production_id
        if not production or production.state in ('done', 'cancel'):
            return 0.0

        warehouse = production.picking_type_id.warehouse_id or self.location_id.warehouse_id
        if not warehouse:
            return 0.0

        to_date = self.date or production.date_start or production.date_deadline or fields.Datetime.now()
        values = self.product_id.with_context(
            warehouse_id=warehouse.id,
            to_date=to_date,
            allowed_company_ids=[production.company_id.id],
            company_owned=True,
            prefetch_fields=False,
        ).read(['virtual_available'])[0]
        forecast = values.get('virtual_available') or 0.0

        # Draft component moves are not part of product.virtual_available yet.
        # Simulate this move once so the same algorithm also works before MO confirm.
        if self.state == 'draft':
            required = self.product_uom._compute_quantity(
                self.product_uom_qty, self.product_id.uom_id
            )
            forecast -= required

        forecast += self._planning_draft_purchase_supply(warehouse, to_date)
        shortage_product_uom = max(-forecast, 0.0)
        return self.product_id.uom_id._compute_quantity(
            shortage_product_uom, self.product_uom
        )

    @api.depends(
        'raw_material_production_id',
        'raw_material_production_id.state',
        'product_uom_qty',
        'product_uom',
        'product_id',
        'date',
        'state',
        'planning_purchase_order_line_id',
    )
    def _compute_planning_can_purchase_component(self):
        for move in self:
            if move.planning_purchase_order_line_id:
                move.planning_can_purchase_component = False
                continue
            move.planning_can_purchase_component = move._planning_forecast_shortage() > 1e-6

    def action_create_component_purchase(self):
        self.ensure_one()
        production = self.raw_material_production_id
        if not production:
            raise UserError(_('Esta línea no pertenece a los componentes de una orden de fabricación.'))
        if production.state in ('done', 'cancel'):
            raise UserError(_('No puede generar una compra desde una orden de fabricación terminada o cancelada.'))
        if self.planning_purchase_order_line_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Compra del componente'),
                'res_model': 'purchase.order',
                'res_id': self.planning_purchase_order_line_id.order_id.id,
                'view_mode': 'form',
                'views': [(False, 'form')],
                'target': 'current',
            }
        if not self.planning_purchase_vendor_id:
            raise UserError(_('Seleccione un proveedor para el componente %s.') % self.product_id.display_name)

        vendor = self.planning_purchase_vendor_id
        if not self.planning_can_purchase_component:
            raise UserError(_(
                'El componente %s tiene disponibilidad suficiente o ya no requiere una compra desde la OF.'
            ) % self.product_id.display_name)

        # Recalcular en el momento de crear la RFQ para no comprar una cantidad
        # que otra compra/OF/transferencia ya vaya a cubrir.
        qty = self._planning_forecast_shortage()
        if qty <= 0:
            raise UserError(_(
                'El pronóstico ya cubre el componente %s; no es necesario comprar.'
            ) % self.product_id.display_name)

        warehouse = production.picking_type_id.warehouse_id
        picking_type = warehouse.in_type_id if warehouse else False
        Purchase = self.env['purchase.order']
        PurchaseLine = self.env['purchase.order.line']

        domain = [
            ('state', '=', 'draft'),
            ('mrp_production_id', '=', production.id),
            ('partner_id', '=', vendor.commercial_partner_id.id),
        ]
        if picking_type:
            domain.append(('picking_type_id', '=', picking_type.id))
        po = Purchase.search(domain, limit=1)
        if not po:
            vals = {
                'partner_id': vendor.commercial_partner_id.id,
                'company_id': production.company_id.id,
                'origin': production.name,
                'mrp_production_id': production.id,
                'advanced_plan_id': production.advanced_plan_id.id if production.advanced_plan_id else False,
            }
            if picking_type:
                vals['picking_type_id'] = picking_type.id
            po = Purchase.create(vals)

        vals = PurchaseLine._prepare_purchase_order_line(
            self.product_id,
            qty,
            self.product_uom,
            production.company_id,
            po.partner_id,
            po,
        )
        vals['mrp_component_move_id'] = self.id
        pol = PurchaseLine.create(vals)
        self.write({
            'planning_purchase_order_line_id': pol.id,
            'planning_purchase_qty': qty,
        })
        production.message_post(body=_(
            'Se creó la compra %s para el componente %s, cantidad %s, proveedor %s.'
        ) % (po.name, self.product_id.display_name, qty, vendor.display_name))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Compra de componente'),
            'res_model': 'purchase.order',
            'res_id': po.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    planning_operation_id = fields.Many2one('mrp.planning.operation', copy=False)
