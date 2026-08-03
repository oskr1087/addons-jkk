from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class StockMove(models.Model):
    _inherit = "stock.move"

    line_number = fields.Integer(
        compute="_compute_line_number",
        string="#",
    )

    location_internal_id = fields.Integer(
        compute="_compute_location_internal_id",
        string="Almacén",
    )

    @api.depends(
        "raw_material_production_id",
        "raw_material_production_id.move_raw_ids.sequence",
    )
    def _compute_line_number(self):
        for production in self.mapped("raw_material_production_id"):
            for i, move in enumerate(
                production.move_raw_ids.sorted("sequence"),
                start=1,
            ):
                move.line_number = i

    @api.depends("location_id")
    def _compute_location_internal_id(self):
        for move in self:
            move.location_internal_id = (
                move.location_id.id if move.location_id else False
            )

    def _is_inbound_receipt(self):
        """Determina si es una recepción normal (no devolución)"""
        # No es devolución si NO tiene referencia a devolución
        if 'Devolución' in (self.origin or ''):
            return False
        
        # Es recepción si viene de ubicación externa (proveedor) a interna (almacén)
        return (
            self.location_id.usage == 'supplier'
            and self.location_dest_id.usage == 'internal'
        )
    
    def _is_return_move(self):
        """Detecta si es una devolución/retorno"""
        # Es devolución si:
        # 1. Viene de almacén (interno) a proveedor (supplier)
        # 2. O tiene 'Devolución' en el origen
        is_return_location = (
            self.location_id.usage == 'internal'
            and self.location_dest_id.usage == 'supplier'
        )
        is_return_document = 'Devolución' in (self.origin or '')
        
        return is_return_location or is_return_document

    def _action_done(self, cancel_backorder=False):

        for move in self:
            # SOLO valida si es una recepción NORMAL (no es devolución)
            if (
                move.purchase_line_id
                and move.product_id
                and move.quantity
                and move._is_inbound_receipt()  # ✅ Recepciones normales: VALIDA
                and not move._is_return_move()  # ❌ Devoluciones: NO VALIDA
            ):

                purchase_line = move.purchase_line_id

                # Cantidad comprada
                ordered_qty = purchase_line.product_qty

                # Todo lo recibido anteriormente (solo recepciones normales, excluyendo devoluciones)
                previous_received = sum(
                    purchase_line.move_ids.filtered(
                        lambda m:
                        m.state == "done"
                        and m.id != move.id
                        and m._is_inbound_receipt()  # Solo cuenta recepciones normales
                        and not m._is_return_move()  # Excluye devoluciones
                    ).mapped("quantity")
                )

                total_received = previous_received + move.quantity

                if total_received > ordered_qty:

                    raise ValidationError(
                        _(
                            "No puede recibir más cantidad de la comprada.\n\n"
                            "Producto: %s\n"
                            "Cantidad solicitada: %s\n"
                            "Cantidad recibida anteriormente: %s\n"
                            "Cantidad que intenta recibir: %s\n"
                            "Total recibido: %s"
                        )
                        % (
                            move.product_id.display_name,
                            ordered_qty,
                            previous_received,
                            move.quantity,
                            total_received,
                        )
                    )

        return super()._action_done(cancel_backorder)
