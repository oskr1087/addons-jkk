from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare


class MrpProductionLotDistribution(models.Model):
    _name = "mrp.production.lot.distribution"
    _description = "Distribución de lotes de producción"
    _order = "id desc"

    production_id = fields.Many2one(
        "mrp.production",
        string="Orden de fabricación",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        related="production_id.company_id",
        store=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        related="production_id.product_id",
        store=True,
        readonly=True,
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="Unidad de medida",
        related="production_id.product_uom_id",
        store=True,
        readonly=True,
    )
    quantity_to_produce = fields.Float(
        string="Cantidad a producir",
        related="production_id.qty_producing",
        readonly=True,
    )
    line_ids = fields.One2many(
        "mrp.production.lot.distribution.line",
        "distribution_id",
        string="Líneas de lote",
        copy=True,
    )
    total_quantity = fields.Float(
        string="Cantidad distribuida",
        compute="_compute_total_quantity",
        store=True,
    )
    difference_quantity = fields.Float(
        string="Diferencia",
        compute="_compute_difference_quantity",
        store=True,
    )
    is_valid = fields.Boolean(
        string="Válida",
        compute="_compute_is_valid",
        store=True,
    )
    state = fields.Selection(
        related="production_id.state",
        readonly=True,
    )

    _sql_constraints = [
        (
            "production_unique",
            "unique(production_id)",
            "A manufacturing order can only have one lot distribution.",
        ),
    ]

    @api.depends("line_ids.quantity")
    def _compute_total_quantity(self):
        for record in self:
            record.total_quantity = sum(record.line_ids.mapped("quantity"))

    @api.depends("total_quantity", "quantity_to_produce")
    def _compute_difference_quantity(self):
        for record in self:
            record.difference_quantity = (
                record.quantity_to_produce - record.total_quantity
            )

    @api.depends(
        "line_ids.quantity",
        "line_ids.lot_id",
        "quantity_to_produce",
        "total_quantity",
        "production_id.product_uom_id",
    )
    def _compute_is_valid(self):
        for record in self:
            rounding = record.production_id.product_uom_id.rounding or 0.01
            record.is_valid = (
                bool(record.line_ids)
                and float_compare(
                    record.total_quantity,
                    record.quantity_to_produce,
                    precision_rounding=rounding,
                )
                == 0
            )

    @api.constrains("line_ids", "production_id")
    def _check_distribution(self):
        for record in self:
            record._validate_lines()

    def _validate_lines(self):
        self.ensure_one()
        production = self.production_id
        if production.product_tracking != "lot":
            raise ValidationError(
                _("Lot distribution is only available for products tracked by lot.")
            )

        seen_lots = set()
        total = 0.0
        rounding = production.product_uom_id.rounding or 0.01

        for line in self.line_ids:
            if line.lot_id.id in seen_lots:
                raise ValidationError(
                    _("Lot %s cannot appear more than once in the distribution.")
                    % line.lot_id.display_name
                )
            seen_lots.add(line.lot_id.id)

            if line.lot_id.product_id != production.product_id:
                raise ValidationError(
                    _("Lot %s does not belong to product %s.")
                    % (
                        line.lot_id.display_name,
                        production.product_id.display_name,
                    )
                )

            if line.quantity < 0:
                raise ValidationError(
                    _("The quantity for lot %s must be greater than zero.")
                    % line.lot_id.display_name
                )

            total += line.quantity

        if production.state in ("done", "cancel"):
            raise UserError(
                _(
                    "The lot distribution cannot be modified on a completed or cancelled MO."
                )
            )

        # Do not force equality here during every line edit because users
        # need to be able to enter the lines progressively. The final
        # validation is performed before marking the MO as done.
        return True

    def action_validate_distribution(self):
        self.ensure_one()
        self._validate_lines()

        production = self.production_id
        rounding = production.product_uom_id.rounding or 0.01
        if float_compare(
            self.total_quantity,
            production.qty_producing,
            precision_rounding=rounding,
        ):
            raise UserError(
                _(
                    "The lot distribution does not match the quantity to produce. "
                    "Quantity to produce: %(produce)s. Distributed: %(distributed)s."
                )
                % {
                    "produce": production.qty_producing,
                    "distributed": self.total_quantity,
                }
            )

        production._sync_lot_producing_ids_from_distribution()
        return True

    def action_open_distribution(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Lot Distribution"),
            "res_model": "mrp.production.lot.distribution",
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }


class MrpProductionLotDistributionLine(models.Model):
    _name = "mrp.production.lot.distribution.line"
    _description = "Línea de distribución de lotes de producción"
    _order = "id"

    distribution_id = fields.Many2one(
        "mrp.production.lot.distribution",
        string="Distribución",
        required=True,
        ondelete="cascade",
    )
    production_id = fields.Many2one(
        related="distribution_id.production_id",
        store=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        related="distribution_id.product_id",
        store=True,
        readonly=True,
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="Unidad de medida",
        related="distribution_id.product_uom_id",
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        related="distribution_id.company_id",
        store=True,
        readonly=True,
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lote",
        required=True,
        domain="[('product_id', '=', product_id), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        check_company=True,
    )
    quantity = fields.Float(
        string="Cantidad",
        required=True,
        digits="Product Unit",
    )

    _sql_constraints = [
        (
            "lot_positive",
            "CHECK(quantity > 0)",
            "The quantity assigned to a lot must be greater than zero.",
        ),
        (
            "distribution_lot_unique",
            "unique(distribution_id, lot_id)",
            "A lot can only appear once in the distribution.",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.mapped("distribution_id")._validate_lines()
        lines.mapped("production_id")._sync_lot_producing_ids_from_distribution()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if any(key in vals for key in ("lot_id", "quantity", "distribution_id")):
            distributions = self.mapped("distribution_id")
            distributions._validate_lines()
            distributions.mapped(
                "production_id"
            )._sync_lot_producing_ids_from_distribution()
        return res

    def unlink(self):
        distributions = self.mapped("distribution_id")
        res = super().unlink()
        for distribution in distributions.exists():
            production = distribution.production_id.exists()
            if production:
                production._sync_lot_producing_ids_from_distribution()
        return res

    @api.onchange("lot_id")
    def _onchange_lot_id(self):
        if (
            self.lot_id
            and self.product_id
            and self.lot_id.product_id != self.product_id
        ):
            self.lot_id = False
            return {
                "warning": {
                    "title": _("Invalid Lot"),
                    "message": _(
                        "The selected lot does not belong to the manufactured product."
                    ),
                }
            }
