from odoo import models, fields, api
from odoo.exceptions import ValidationError


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    @api.onchange('move_id')
    def _onchange_move_id_load_lot_sequence(self):
        """
        Cuando se selecciona un movimiento, cargar automáticamente
        el próximo número de lote de su categoría a través de move_id.product_id
        """
        if self.move_id and self.move_id.product_id:
            product = self.move_id.product_id
            category = product.categ_id
            
            # Verificar si la categoría tiene secuencia configurada
            if category and category.lot_sequence_id and category.lot_sequence_prefix:
                try:
                    # Obtener el próximo número de lote
                    next_lot_name = category.get_next_lot_name()
                    self.lot_name = next_lot_name
                except ValidationError as e:
                    # Si hay error, dejar el campo vacío pero mostrar advertencia
                    self.lot_name = False
            else:
                # Si no hay secuencia, limpiar el campo
                self.lot_name = False

    def _generate_lot_number_on_save(self):
        """
        Generar número de lote si no está presente al guardar
        Accede al producto a través de move_id.product_id
        """
        for move_line in self:
            if not move_line.lot_name and move_line.move_id and move_line.move_id.product_id:
                product = move_line.move_id.product_id
                category = product.categ_id
                
                if category and category.lot_sequence_id and category.lot_sequence_prefix:
                    try:
                        next_lot_name = category.get_next_lot_name()
                        move_line.lot_name = next_lot_name
                    except ValidationError:
                        pass

    @api.model_create_multi
    def create(self, vals_list):
        # Generar números de lote automáticos
        for vals in vals_list:
            # Acceder al producto a través de move_id.product_id
            if vals.get('move_id') and not vals.get('lot_name'):
                move = self.env['stock.move'].browse(vals['move_id'])
                if move and move.product_id:
                    product = move.product_id
                    category = product.categ_id
                    
                    if category and category.lot_sequence_id and category.lot_sequence_prefix:
                        try:
                            next_lot_name = category.get_next_lot_name()
                            vals['lot_name'] = next_lot_name
                        except ValidationError:
                            pass
        
        return super().create(vals_list)

    def write(self, vals):
        """
        Si se cambia el movimiento y no hay lot_name, generar uno nuevo
        Accede al producto a través de move_id.product_id
        """
        if 'move_id' in vals and 'lot_name' not in vals:
            for move_line in self:
                move = self.env['stock.move'].browse(vals['move_id'])
                if move and move.product_id:
                    product = move.product_id
                    category = product.categ_id
                    
                    if category and category.lot_sequence_id and category.lot_sequence_prefix:
                        if not move_line.lot_name:
                            try:
                                next_lot_name = category.get_next_lot_name()
                                vals['lot_name'] = next_lot_name
                            except ValidationError:
                                pass
        
        return super().write(vals)
