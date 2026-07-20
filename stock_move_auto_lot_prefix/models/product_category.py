from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ProductCategory(models.Model):
    _inherit = 'product.category'

    lot_sequence_prefix = fields.Char(
        string='Prefijo Secuencia Lote',
        help='Prefijo para generar secuencias de lotes. Ej: PROD, ALMACÉN, etc.'
    )
    
    lot_sequence_id = fields.Many2one(
        'ir.sequence',
        string='Secuencia de Lote',
        help='Secuencia automática generada para los lotes de esta categoría'
    )
    
    lot_sequence_next_number = fields.Integer(
        string='Próximo Número',
        default=1,
        help='Próximo número en la secuencia'
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('lot_sequence_prefix'):
                # Crear secuencia automáticamente
                sequence = self.env['ir.sequence'].create({
                    'name': f"Secuencia Lote - {vals.get('name', 'Categoría')}",
                    'prefix': vals.get('lot_sequence_prefix'),
                    'padding': 5,
                    'implementation': 'standard',
                })
                vals['lot_sequence_id'] = sequence.id
        
        return super().create(vals_list)

    def write(self, vals):
        # Si cambia el prefijo, actualizar la secuencia
        if 'lot_sequence_prefix' in vals and vals['lot_sequence_prefix']:
            for category in self:
                if category.lot_sequence_id:
                    category.lot_sequence_id.write({
                        'prefix': vals['lot_sequence_prefix'],
                        'name': f"Secuencia Lote - {category.name}",
                    })
                else:
                    # Crear secuencia si no existe
                    sequence = self.env['ir.sequence'].create({
                        'name': f"Secuencia Lote - {category.name}",
                        'prefix': vals['lot_sequence_prefix'],
                        'padding': 5,
                        'implementation': 'standard',
                    })
                    vals['lot_sequence_id'] = sequence.id
        
        return super().write(vals)

    def get_next_lot_name(self):
        """
        Obtener el próximo nombre de lote basado en la secuencia
        """
        self.ensure_one()
        
        if not self.lot_sequence_id:
            raise ValidationError(
                f'La categoría {self.name} no tiene una secuencia de lote configurada'
            )
        
        # Usar la secuencia de Odoo para generar el próximo número
        next_lot_name = self.lot_sequence_id.next_by_id()
        
        return next_lot_name

    def unlink(self):
        """
        Eliminar secuencia asociada cuando se elimina la categoría
        """
        for category in self:
            if category.lot_sequence_id:
                category.lot_sequence_id.unlink()
        
        return super().unlink()
