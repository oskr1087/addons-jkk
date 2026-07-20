# Stock Move Auto Lot Prefix

Módulo de Odoo que automatiza la generación de secuencias de lotes basadas en prefijos configurados en la categoría de productos.

## Características

### 1. Prefijo en Categoría de Producto
- Agrega un campo `lot_sequence_prefix` en `product.category`
- Permite configurar un prefijo personalizado (ej: PROD-, ALM-, TEX-, etc.)
- Se puede cambiar dinámicamente sin afectar lotes anteriores

### 2. Creación Automática de Secuencias
- Al guardar un prefijo en la categoría, crea automáticamente una secuencia de Odoo
- La secuencia se vincula a la categoría para un control centralizado
- Si cambia el prefijo, actualiza la secuencia asociada
- Al eliminar la categoría, elimina la secuencia correspondiente

### 3. Carga Automática de Lot Name en stock.move.line
- Cuando se selecciona un producto en `stock.move.line` (via `@onchange` en `product_id`):
  - Obtiene la categoría del producto
  - Verifica si tiene secuencia configurada
  - Genera automáticamente el próximo número de lote
  - Carga el número en el campo `lot_name`

### 4. Generación en Creación
- Al crear un `stock.move.line` con producto:
  - Si `lot_name` está vacío, genera automáticamente el número
  - Respeta si el usuario ya escribió un valor

### 5. Actualización en Cambio de Producto
- Al cambiar el producto en un movimiento:
  - Si no hay `lot_name`, genera uno nuevo basado en la nueva categoría
  - Permite mantener el número si ya existe

## Instalación

1. Copia el módulo `stock_move_auto_lot_prefix` a tu directorio de addons
2. Ve a Aplicaciones > Actualizar lista de aplicaciones
3. Busca "Stock Move Auto Lot Prefix" e instálalo
4. ¡Listo!

## Uso Básico

### Paso 1: Configurar Categoría

1. Ve a Inventario > Productos > Categorías de Producto
2. Abre o crea una categoría
3. En la sección "Configuración de Secuencia de Lotes", ingresa un prefijo
   - Ejemplos: `PROD-`, `ALM-`, `TEX-`, `ELEC-`
4. Guarda

Resultado:
- Se crea automáticamente una secuencia: `PROD-00001`, `PROD-00002`, etc.

### Paso 2: Usar en Movimiento de Stock

1. Ve a Inventario > Operaciones > Movimientos de Stock
2. Crea un nuevo movimiento o edita uno existente
3. Selecciona un producto que tenga categoría con prefijo configurado
4. El campo `lot_name` se llena automáticamente con el próximo número

Ejemplo:
- Categoría: "Textiles"
- Prefijo: `TEX-`
- Al seleccionar un producto de Textiles → `lot_name = TEX-00001`
- En el siguiente movimiento → `lot_name = TEX-00002`

## Arquitectura

### Modelos

#### ProductCategory (product.category)
- **lot_sequence_prefix**: Campo char para el prefijo
- **lot_sequence_id**: Vínculo Many2one a ir.sequence
- **lot_sequence_next_number**: Campo de solo lectura del próximo número
- **Métodos**:
  - `create()`: Crea secuencia automáticamente
  - `write()`: Actualiza secuencia si cambia prefijo
  - `get_next_lot_name()`: Retorna el próximo nombre usando la secuencia
  - `unlink()`: Elimina la secuencia asociada

#### StockMoveLine (stock.move.line)
- **Métodos**:
  - `_onchange_product_id_load_lot_sequence()`: Carga lot_name al seleccionar producto
  - `create()`: Genera lot_name automáticamente en creación
  - `write()`: Genera lot_name si cambia producto y está vacío

### Vistas

- **product_category_views.xml**: Extiende vista de categoría con campos de secuencia
- **stock_move_line_views.xml**: Configuración de visualización en movimientos

### Seguridad

- **ir.model.access.csv**: Acceso de usuarios normales a configuración de categorías

## Casos de Uso

### 1. Industria Textil

- Categoría: Textiles
- Prefijo: TEX-
- Números generados: TEX-00001, TEX-00002, TEX-00003, ...

### 2. Almacén Multi-Zona

- Zona A: ZONA_A-00001, ZONA_A-00002, ...
- Zona B: ZONA_B-00001, ZONA_B-00002, ...

### 3. Control por Lote de Producción

- Producción 2024: PROD2024-00001, PROD2024-00002, ...
- Materia Prima: MP-00001, MP-00002, ...

## Flujo Técnico

1. Usuario configura prefijo en categoría
2. Sistema crea secuencia de Odoo automáticamente
3. Usuario crea stock.move.line
4. Usuario selecciona producto
5. @onchange dispara _onchange_product_id_load_lot_sequence()
6. Sistema obtiene categoría del producto
7. Si tiene secuencia, llama get_next_lot_name()
8. Retorna el próximo número (PREFIJO-NÚMERO)
9. lot_name se carga automáticamente

## Consideraciones

- Si cambia manualmente el `lot_name`, el módulo respeta tu valor
- Las secuencias se incrementan automáticamente cada vez que se generan
- Si no hay prefijo en la categoría, el campo `lot_name` se limpia
- Compatible con Odoo 16 (ver versión en __manifest__.py)

## Solución de Problemas

### "La categoría no tiene secuencia configurada"
- Verifica que la categoría tenga un prefijo ingresado
- Ve a la categoría y guarda de nuevo para forzar la creación de secuencia

### El lot_name no se carga automáticamente
- Confirma que el producto tiene asignada una categoría
- Verifica que la categoría tenga un prefijo configurado
- Recarga el formulario (F5 o Ctrl+R)

### Los números no son secuenciales
- Verifica el campo "Prefijo" en la secuencia
- Comprueba el "Padding" de la secuencia (debe ser 5 o más)

## Extensiones Futuras

- Soporte para múltiples secuencias por categoría
- Historial de lotes generados
- Reportes de uso de secuencias
- Validación de secuencias en transferencias
