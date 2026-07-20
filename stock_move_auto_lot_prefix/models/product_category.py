from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ProductCategory(models.Model):
    _inherit = 'product.category'

    lot_sequence_prefix = fields.Char(
        string='Prefijo Secuencia Lote',
        help='Prefijo para generar secuencias de lotes. Ej: PROD-|100, ALMACÉN-|1, etc. Formato: PREFIX|NUMERO_INICIAL (si no especifica número inicial, comienza en 1)'
    )
    
    lot_sequence_id = fields.Many2one(
        'ir.sequence',
        string='Secuencia de Lote',
        help='Secuencia automática generada para los lotes de esta categoría'
    )
    
    lot_sequence_next_number = fields.Integer(
        string='Próximo Número',
        default=1,
        help='Próximo número en la secuencia. Editable para cambiar el número inicial cuando se está creando la categoría',
        compute='_compute_lot_sequence_next_number',
        inverse='_inverse_lot_sequence_next_number',
        store=False
    )

    def _parse_prefix_and_start_number(self, prefix_value):
        """
        Parsear el valor del prefijo para extraer el prefijo y el número inicial.
        Formato: "PREFIX-|100" o "PREFIX-" (si no tiene |, comienza en 1)
        Retorna: (prefix, start_number)
        """
        if not prefix_value:
            return None, 1
        
        if '|' in prefix_value:
            prefix_part, start_part = prefix_value.rsplit('|', 1)
            try:
                start_number = int(start_part)
                return prefix_part, start_number
            except ValueError:
                return prefix_value, 1
        
        return prefix_value, 1

    def _compute_lot_sequence_next_number(self):
        """
        Calcular el próximo número de secuencia desde la secuencia de Odoo
        """
        for category in self:
            if category.lot_sequence_id:
                category.lot_sequence_next_number = category.lot_sequence_id.number_next_actual
            else:
                category.lot_sequence_next_number = 1

    def _inverse_lot_sequence_next_number(self):
        """
        Cuando el usuario edita el próximo número, actualizar la secuencia de Odoo
        """
        for category in self:
            if category.lot_sequence_id and category.lot_sequence_next_number > 0:
                category.lot_sequence_id.write({
                    'number_next_actual': category.lot_sequence_next_number
                })

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('lot_sequence_prefix'):
                # Parsear prefijo y número inicial
                prefix_value = vals.get('lot_sequence_prefix')
                prefix, start_number = self._parse_prefix_and_start_number(prefix_value)
                
                # Actualizar con el prefijo limpio
                vals['lot_sequence_prefix'] = prefix_value
                
                # Crear secuencia automáticamente
                sequence_vals = {
                    'name': f"Secuencia Lote - {vals.get('name', 'Categoría')}",
                    'prefix': prefix,
                    'padding': 5,
                    'implementation': 'standard',
                }
                
                # Si el número inicial es mayor a 1, ajustar la secuencia
                if start_number > 1:
                    sequence_vals['number_next_actual'] = start_number
                
                sequence = self.env['ir.sequence'].create(sequence_vals)
                vals['lot_sequence_id'] = sequence.id
        
        return super().create(vals_list)

    def write(self, vals):
        # Si cambia el prefijo, actualizar la secuencia
        if 'lot_sequence_prefix' in vals and vals['lot_sequence_prefix']:
            prefix_value = vals.get('lot_sequence_prefix')
            prefix, start_number = self._parse_prefix_and_start_number(prefix_value)
            
            for category in self:
                if category.lot_sequence_id:
                    # Actualizar la secuencia existente
                    category.lot_sequence_id.write({
                        'prefix': prefix,
                        'name': f"Secuencia Lote - {category.name}",
                    })
                    
                    # Si el número inicial cambió, actualizar
                    if start_number > 1:
                        category.lot_sequence_id.write({
                            'number_next_actual': start_number,
                        })
                else:
                    # Crear secuencia si no existe
                    sequence_vals = {
                        'name': f"Secuencia Lote - {category.name}",
                        'prefix': prefix,
                        'padding': 5,
                        'implementation': 'standard',
                    }
                    
                    if start_number > 1:
                        sequence_vals['number_next_actual'] = start_number
                    
                    sequence = self.env['ir.sequence'].create(sequence_vals)
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
