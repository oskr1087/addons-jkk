from odoo import fields, models


class MrpReconditioningTrace(models.Model):
    _name = "mrp.reconditioning.trace"
    _description = "Trazabilidad de origen del reacondicionamiento"
    _order = "id"

    reconditioning_id = fields.Many2one(
        "mrp.production",
        string="Reacondicionamiento",
        required=True,
        ondelete="cascade",
        index=True,
        domain="[('is_reconditioning', '=', True)]",
    )
    source_production_id = fields.Many2one(
        "mrp.production",
        string="Orden de fabricación original",
        required=True,
        ondelete="restrict",
        index=True,
    )
    product_id = fields.Many2one(
        "product.product", string="Producto", required=True, ondelete="restrict", index=True
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lote/Número de serie",
        ondelete="restrict",
        domain="[('product_id', '=', product_id)]",
    )
    quantity = fields.Float(string="Cantidad", digits="Product Unit")
    product_uom_id = fields.Many2one("uom.uom", string="Unidad de medida")
    state = fields.Selection(
        [
            ("inherited", "Heredado"),
            ("replaced", "Reemplazado"),
            ("new", "Nuevo"),
        ],
        string="Estado",
        required=True,
        default="inherited",
    )
    note = fields.Char(string="Nota")
