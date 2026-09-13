from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MrpPlanningCalendarDayWizard(models.TransientModel):
    _name = 'mrp.planning.calendar.day.wizard'
    _description = 'Planificar entregas APS de un día'

    planning_date = fields.Date(
        string='Día a planificar',
        required=True,
        default=fields.Date.context_today,
    )
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
    )
    warehouse_ids = fields.Many2many(
        'stock.warehouse',
        string='Almacenes',
        required=True,
        domain="[('company_id', '=', company_id)]",
        default=lambda self: self.env['stock.warehouse'].search([
            ('company_id', '=', self.env.company.id),
        ]),
    )
    pending_line_count = fields.Integer(
        string='Líneas pendientes',
        compute='_compute_pending_line_count',
    )
    pending_sale_line_ids = fields.Many2many(
        'sale.order.line',
        string='Líneas pendientes del día',
        compute='_compute_pending_line_count',
    )

    def _pending_lines(self):
        self.ensure_one()
        lines = self.env['sale.order.line'].search([
            ('order_id.state', '=', 'sale'),
            ('order_id.company_id', '=', self.company_id.id),
            ('order_id.warehouse_id', 'in', self.warehouse_ids.ids),
            ('display_type', '=', False),
            ('product_id', '!=', False),
            ('product_uom_qty', '>', 0),
            ('planning_delivery_date', '<=', self.planning_date),
        ], order='planning_delivery_date asc, order_id asc, sequence asc, id asc')

        # Do not use aps_plan_count in the SQL/domain here: it is a non-stored
        # computed field with a custom search method.  For this operational
        # wizard the authoritative test is the real traceability of each line.
        # This also keeps the count consistent with what the calendar displays.
        lines._compute_aps_traceability()
        return lines.filtered(
            lambda line:
                line.product_uom_qty - line.qty_delivered > 0
                and not line.aps_plan_ids
        )

    @api.depends('planning_date', 'company_id', 'warehouse_ids')
    def _compute_pending_line_count(self):
        for wizard in self:
            lines = wizard._pending_lines() if (
                wizard.planning_date and wizard.company_id and wizard.warehouse_ids
            ) else self.env['sale.order.line']
            wizard.pending_sale_line_ids = lines
            wizard.pending_line_count = len(lines)

    def action_create_plan(self):
        self.ensure_one()
        lines = self._pending_lines()
        if not lines:
            raise UserError(_(
                'No existen líneas de venta pendientes de planificación hasta el día %s '
                'en los almacenes seleccionados.'
            ) % fields.Date.to_string(self.planning_date))

        # Revalidate immediately before create to avoid duplicate inclusion if
        # another planner was created while this wizard was open.
        lines._compute_aps_traceability()
        lines = lines.filtered(lambda line: not line.aps_plan_ids)
        if not lines:
            raise UserError(_('Las líneas de este día ya fueron incluidas en otra planificación.'))

        warehouses = lines.mapped('order_id.warehouse_id')

        # Pure date planning: no UTC bounds and no artificial 23:59:59.
        plan = self.env['mrp.planning.plan'].create({
            'plan_type': 'manufacturing',
            'company_id': self.company_id.id,
            'warehouse_ids': [(6, 0, warehouses.ids)],
            'date_end': self.planning_date,
            'source_sale_line_ids': [(6, 0, lines.ids)],
        })

        result = plan.action_calculate()
        # If calculation returns a notification because there is no net need,
        # still open the generated plan: it preserves the selected demand scope
        # and lets the planner inspect/recalculate it.
        return {
            'type': 'ir.actions.act_window',
            'name': _('Planificación APS'),
            'res_model': 'mrp.planning.plan',
            'res_id': plan.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }
