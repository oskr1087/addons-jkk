from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tools.float_utils import float_compare


class MrpReconditioning(models.Model):
    _name = "mrp.reconditioning"
    _description = "Orden de reacondicionamiento"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="Número", default=lambda self: _("Nuevo"), readonly=True, copy=False, tracking=True)
    state = fields.Selection([
        ("draft", "Borrador"), ("reconditioning", "Reacondicionando"),
        ("done", "Reacondicionado"), ("cancel", "Cancelado"),
    ], default="draft", required=True, tracking=True, copy=False)
    product_id = fields.Many2one("product.product", string="Producto terminado", required=True, tracking=True,
        check_company=True, domain="[('is_storable', '=', True)]")
    product_uom_id = fields.Many2one("uom.uom", related="product_id.uom_id", string="Unidad", readonly=True)

    available_product_ids = fields.Many2many(
        "product.product",
        compute="_compute_available_component_stock",
        string="Componentes disponibles",
        compute_sudo=True,
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Ubicación",
        check_company=True,
        domain="[('id', 'in', available_location_ids)]",
    )
    available_location_ids = fields.Many2many(
        "stock.location",
        compute="_compute_available_component_stock",
        string="Ubicaciones disponibles",
        compute_sudo=True,
    )
    available_qty = fields.Float(
        string="Disponible",
        compute="_compute_available_component_stock",
        digits="Product Unit",
        compute_sudo=True,
    )

    @api.depends("company_id", "product_id", "location_id")
    def _compute_available_component_stock(self):
        Quant = self.env["stock.quant"]
        for line in self:
            quants = Quant.search([
                ("company_id", "=", line.company_id.id),
                ("location_id.usage", "=", "internal"),
                ("quantity", ">", 0),
            ]).filtered(lambda q: (q.quantity - q.reserved_quantity) > 0)
            line.available_product_ids = quants.product_id
            product_quants = quants.filtered(lambda q: q.product_id == line.product_id) if line.product_id else quants
            line.available_location_ids = product_quants.location_id
            if line.product_id and line.location_id:
                line.available_qty = sum(
                    q.quantity - q.reserved_quantity
                    for q in product_quants.filtered(lambda q: q.location_id == line.location_id)
                )
            else:
                line.available_qty = 0.0

    @api.onchange("product_id")
    def _onchange_component_product_id(self):
        self.location_id = False
        if self.product_id:
            quants = self.env["stock.quant"].search([
                ("company_id", "=", self.company_id.id),
                ("product_id", "=", self.product_id.id),
                ("location_id.usage", "=", "internal"),
                ("quantity", ">", 0),
            ]).filtered(lambda q: (q.quantity - q.reserved_quantity) > 0)
            if len(quants.location_id) == 1:
                self.location_id = quants.location_id

    lot_id = fields.Many2one("stock.lot", string="Lote/Número de serie", required=True, tracking=True,
        check_company=True, domain="[('product_id', '=', product_id), '|', ('company_id', '=', False), ('company_id', '=', company_id)]")
    quantity = fields.Float(string="Cantidad", required=True, default=1.0, digits="Product Unit", tracking=True)
    location_id = fields.Many2one("stock.location", string="Ubicación", required=True, tracking=True, check_company=True,
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [False, company_id])]",
        default=lambda self: self.env.ref("stock.stock_location_stock", raise_if_not_found=False))
    available_qty = fields.Float(string="Disponible", compute="_compute_available_qty", digits="Product Unit", compute_sudo=True)
    component_line_ids = fields.One2many("mrp.reconditioning.component", "reconditioning_id", string="Componentes adicionales", copy=True)
    production_id = fields.Many2one("mrp.production", string="Orden de fabricación", readonly=True, copy=False, tracking=True, check_company=True)
    company_id = fields.Many2one("res.company", string="Compañía", required=True, default=lambda self: self.env.company)

    available_finished_stock_ids = fields.Many2many(
        "stock.quant",
        compute="_compute_available_stock_selectors",
        string="Stock terminado disponible",
        compute_sudo=True,
    )
    available_product_ids = fields.Many2many(
        "product.product",
        compute="_compute_available_stock_selectors",
        string="Productos terminados disponibles",
        compute_sudo=True,
    )
    available_lot_ids = fields.Many2many(
        "stock.lot",
        compute="_compute_available_stock_selectors",
        string="Lotes disponibles",
        compute_sudo=True,
    )
    available_location_ids = fields.Many2many(
        "stock.location",
        compute="_compute_available_stock_selectors",
        string="Ubicaciones disponibles",
        compute_sudo=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") in (_("Nuevo"), _("New")):
                vals["name"] = self.env["ir.sequence"].next_by_code("mrp.reconditioning") or _("Nuevo")
        return super().create(vals_list)

    @api.depends("company_id", "product_id", "lot_id")
    def _compute_available_stock_selectors(self):
        Quant = self.env["stock.quant"]
        for rec in self:
            base_domain = [
                ("company_id", "=", rec.company_id.id),
                ("location_id.usage", "=", "internal"),
                ("quantity", ">", 0),
                ("lot_id", "!=", False),
            ]
            quants = Quant.search(base_domain).filtered(
                lambda q: (q.quantity - q.reserved_quantity) > 0
            )
            # Producto terminado: solo productos fabricables con seguimiento y
            # existencia real por lote/serie.
            finished = quants.filtered(
                lambda q: q.product_id.tracking in ("lot", "serial")
                and q.product_id.route_ids.filtered(
                    lambda route: "manufact" in (route.name or "").lower()
                    or "fabric" in (route.name or "").lower()
                )
            )
            # Si las rutas no permiten identificar fabricables en una base
            # personalizada, usar productos que tengan al menos una LdM de fabricación.
            products = finished.product_id
            bom_products = self.env["mrp.bom"].search([
                ("company_id", "in", [False, rec.company_id.id]),
                ("type", "=", "normal"),
            ]).mapped("product_tmpl_id.product_variant_ids")
            products |= quants.product_id & bom_products
            rec.available_finished_stock_ids = quants.filtered(lambda q: q.product_id in products)
            rec.available_product_ids = products

            product_quants = quants.filtered(lambda q: q.product_id == rec.product_id) if rec.product_id else quants
            rec.available_lot_ids = product_quants.lot_id

            location_quants = product_quants
            if rec.lot_id:
                location_quants = location_quants.filtered(lambda q: q.lot_id == rec.lot_id)
            rec.available_location_ids = location_quants.location_id

    @api.depends("product_id", "lot_id", "location_id")
    def _compute_available_qty(self):
        for rec in self:
            rec.available_qty = 0.0
            if rec.product_id and rec.lot_id and rec.location_id:
                rec.available_qty = self.env["stock.quant"]._get_available_quantity(
                    rec.product_id, rec.location_id, lot_id=rec.lot_id, strict=False)

    @api.onchange("product_id")
    def _onchange_product_id(self):
        self.lot_id = False
        self.location_id = False
        if self.product_id and self.product_id.tracking == "serial":
            self.quantity = 1.0

    @api.onchange("lot_id")
    def _onchange_lot_id(self):
        self.location_id = False
        if self.product_id and self.lot_id:
            quants = self.env["stock.quant"].search([
                ("company_id", "=", self.company_id.id),
                ("product_id", "=", self.product_id.id),
                ("lot_id", "=", self.lot_id.id),
                ("location_id.usage", "=", "internal"),
                ("quantity", ">", 0),
            ]).filtered(lambda q: (q.quantity - q.reserved_quantity) > 0)
            locations = quants.location_id
            if len(locations) == 1:
                self.location_id = locations

    @api.constrains("quantity")
    def _check_quantity(self):
        for rec in self:
            if rec.quantity <= 0:
                raise ValidationError(_("La cantidad debe ser mayor que cero."))

    def _check_ready(self):
        self.ensure_one()
        if self.state != "draft" or self.production_id:
            raise UserError(_("El reacondicionamiento ya fue procesado."))
        if self.product_id.tracking == "none":
            raise UserError(_("El producto terminado debe manejar lote o número de serie."))
        if self.product_id.tracking == "serial" and float_compare(
            self.quantity, 1.0, precision_rounding=self.product_uom_id.rounding or 0.01):
            raise UserError(_("Los números de serie se reacondicionan de uno en uno."))
        if float_compare(self.available_qty, self.quantity,
                         precision_rounding=self.product_uom_id.rounding or 0.01) < 0:
            raise UserError(_("No existe stock suficiente del lote seleccionado. Disponible: %s") % self.available_qty)
        if any(line.product_id == self.product_id for line in self.component_line_ids):
            raise UserError(_("El producto terminado ya se agrega automáticamente como producto base."))
        return True

    def action_generate_production(self):
        self.ensure_one()
        self._check_ready()
        production_location = self.product_id.with_company(self.company_id).property_stock_production
        commands = [Command.create({
            "description_picking": _("Producto base para reacondicionamiento - %s") % self.product_id.display_name,
            "product_id": self.product_id.id, "product_uom_qty": self.quantity,
            "product_uom": self.product_uom_id.id, "location_id": self.location_id.id,
            "location_dest_id": production_location.id, "company_id": self.company_id.id,
            "is_reconditioning_return_component": True,
            "lot_ids": [Command.set([self.lot_id.id])],
        })]
        for line in self.component_line_ids:
            commands.append(Command.create({
                "description_picking": line.product_id.display_name,
                "product_id": line.product_id.id, "product_uom_qty": line.quantity,
                "product_uom": line.product_uom_id.id, "location_id": (line.location_id or self.location_id).id,
                "location_dest_id": production_location.id, "company_id": self.company_id.id,
            }))
        mo = self.env["mrp.production"].create({
            "is_reconditioning": True, "reconditioning_id": self.id,
            "product_id": self.product_id.id, "product_qty": self.quantity,
            "qty_producing": self.quantity, "product_uom_id": self.product_uom_id.id,
            "bom_id": False, "location_src_id": self.location_id.id,
            "location_dest_id": self.location_id.id, "origin": self.name,
            "lot_producing_ids": [Command.set([self.lot_id.id])],
            "move_raw_ids": commands, "company_id": self.company_id.id,
        })
        if self.product_id.tracking == "lot":
            distribution = mo._get_or_create_lot_distribution()
            distribution.line_ids = [Command.clear(), Command.create({"lot_id": self.lot_id.id, "quantity": self.quantity})]
            distribution._validate_lines()
            mo._sync_lot_producing_ids_from_distribution()
        mo.action_confirm()
        mo.action_assign()
        self.write({"production_id": mo.id, "state": "reconditioning"})
        return self.action_open_production()

    def action_open_production(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Orden de fabricación"),
                "res_model": "mrp.production", "res_id": self.production_id.id,
                "view_mode": "form", "target": "current"}

    def action_cancel(self):
        for rec in self:
            if rec.production_id and rec.production_id.state not in ("done", "cancel"):
                rec.production_id.action_cancel()
            rec.state = "cancel"
        return True


class MrpReconditioningComponent(models.Model):
    _name = "mrp.reconditioning.component"
    _description = "Componente adicional de reacondicionamiento"

    reconditioning_id = fields.Many2one("mrp.reconditioning", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="reconditioning_id.company_id", store=True)
    product_id = fields.Many2one("product.product", string="Componente", required=True, check_company=True,
        domain="[('is_storable', '=', True)]")
    quantity = fields.Float(string="Cantidad", required=True, default=1.0, digits="Product Unit")
    product_uom_id = fields.Many2one("uom.uom", related="product_id.uom_id", string="Unidad", readonly=True)

    available_product_ids = fields.Many2many(
        "product.product",
        compute="_compute_available_component_stock",
        string="Componentes disponibles",
        compute_sudo=True,
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Ubicación",
        check_company=True,
        domain="[('id', 'in', available_location_ids)]",
    )
    available_location_ids = fields.Many2many(
        "stock.location",
        compute="_compute_available_component_stock",
        string="Ubicaciones disponibles",
        compute_sudo=True,
    )
    available_qty = fields.Float(
        string="Disponible",
        compute="_compute_available_component_stock",
        digits="Product Unit",
        compute_sudo=True,
    )

    @api.depends("company_id", "product_id", "location_id")
    def _compute_available_component_stock(self):
        Quant = self.env["stock.quant"]
        for line in self:
            quants = Quant.search([
                ("company_id", "=", line.company_id.id),
                ("location_id.usage", "=", "internal"),
                ("quantity", ">", 0),
            ]).filtered(lambda q: (q.quantity - q.reserved_quantity) > 0)
            line.available_product_ids = quants.product_id
            product_quants = quants.filtered(lambda q: q.product_id == line.product_id) if line.product_id else quants
            line.available_location_ids = product_quants.location_id
            if line.product_id and line.location_id:
                line.available_qty = sum(
                    q.quantity - q.reserved_quantity
                    for q in product_quants.filtered(lambda q: q.location_id == line.location_id)
                )
            else:
                line.available_qty = 0.0

    @api.onchange("product_id")
    def _onchange_component_product_id(self):
        self.location_id = False
        if self.product_id:
            quants = self.env["stock.quant"].search([
                ("company_id", "=", self.company_id.id),
                ("product_id", "=", self.product_id.id),
                ("location_id.usage", "=", "internal"),
                ("quantity", ">", 0),
            ]).filtered(lambda q: (q.quantity - q.reserved_quantity) > 0)
            if len(quants.location_id) == 1:
                self.location_id = quants.location_id


    @api.constrains("quantity")
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_("La cantidad del componente debe ser mayor que cero."))
