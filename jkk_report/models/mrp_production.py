from odoo import api, fields, models


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    # Diseño
    design_no = fields.Char(string="Diseño No")

    # Tipo (Especial / Estándar)
    production_type = fields.Selection(
        [
            ("standard", "Estándar"),
            ("special", "Especial"),
        ],
        string="Tipo",
        default="standard",
    )

    # Origen (Manual / Reproceso)
    origin_type = fields.Selection(
        [
            ("manual", "Manual"),
            ("reprocess", "Reproceso"),
        ],
        string="Origen",
        default="manual",
    )

    # Tipo de Orden
    order_type = fields.Selection(
        [
            ("normal", "Normal"),
            ("special", "Especial"),
        ],
        string="Tipo Orden",
        default="normal",
    )

    # Pedido de Venta
    sale_order_id = fields.Many2one(
        "sale.order", string="Pedido Cliente", compute="_compute_sale_order", store=True
    )

    # Código Cliente
    customer_code = fields.Char(
        related="sale_order_id.partner_id.ref", string="Código Cliente", store=True
    )

    # Nombre Cliente
    customer_name = fields.Char(
        related="sale_order_id.partner_id.name", string="Nombre Cliente", store=True
    )

    # Referencia SO
    sale_reference = fields.Char(
        related="sale_order_id.name", string="Referencia SO", store=True
    )

    # Lista de Materiales
    bom_reference = fields.Char(
        related="bom_id.display_name", string="Lista Materiales", store=True
    )

    @api.depends("origin")
    def _compute_sale_order(self):
        SaleOrder = self.env["sale.order"]

        for production in self:
            production.sale_order_id = False

            if production.origin:
                so = SaleOrder.search([("name", "=", production.origin)], limit=1)
                production.sale_order_id = so
