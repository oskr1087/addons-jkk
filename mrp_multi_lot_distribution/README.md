# MRP Multi Lot Distribution — Odoo 19

## Objetivo

Permitir que una Orden de Fabricación de un producto con tracking por lote produzca la cantidad total en varios lotes, manteniendo la cantidad de cada lote en un objeto separado.

Ejemplo:

- MO: 1.000 unidades
- LOTE-001: 300
- LOTE-002: 250
- LOTE-003: 450

Al validar la fabricación, se crean líneas `stock.move.line` del producto terminado:

- LOTE-001 → 300
- LOTE-002 → 250
- LOTE-003 → 450

## Diseño

Modelos:

- `mrp.production.lot.distribution`
- `mrp.production.lot.distribution.line`

La MO mantiene:

- `lot_producing_ids`: lista de lotes.
- `lot_distribution_id`: distribución principal.
- `lot_distribution_line_ids`: líneas de distribución.

## Métodos heredados

El módulo interviene principalmente en:

- `mrp.production._check_lot_producing_ids`
- `mrp.production.pre_button_mark_done`
- `mrp.production.action_generate_serial`
- `mrp.production._post_inventory`

La lógica de materias primas y el resto del flujo de `button_mark_done()` se conserva mediante `super()`.

## Flujo

1. Crear/seleccionar la MO.
2. Producto terminado con tracking = Lots.
3. Agregar varios lotes en "Lot Distribution".
4. Indicar cantidad para cada lote.
5. La suma debe ser exactamente igual a `qty_producing`.
6. Al marcar como hecho, Odoo crea una línea de movimiento por lote.
7. `stock.move._action_done()` registra las cantidades en inventario.

## Backorders

El comportamiento estándar de backorder se conserva. La distribución corresponde a la cantidad que se está produciendo en la MO actual (`qty_producing`). El backorder queda sin distribución y puede recibir una nueva distribución cuando se vaya a producir.

## Instalación

Copiar la carpeta `mrp_multi_lot_distribution` a los addons de Odoo 19, actualizar la lista de aplicaciones e instalar el módulo.

## Nota técnica

El módulo está diseñado para Odoo 19 basándose en el código estándar de `mrp.production` proporcionado para esta implementación. Debe probarse primero en una base de datos de desarrollo, especialmente con:

- productos tracked by lot;
- work orders;
- backorders;
- by-products;
- múltiples MOs en una misma operación;
- productos con valoración FIFO/AVCO;
- fabricación desde ventas/MTO.


## Validación de disponibilidad antes de lotes y producción

- Solo se validan movimientos de componentes vinculados a la OF mediante `raw_material_production_id`.
- Antes de generar lotes se intenta reservar los componentes y se bloquea la generación si alguno no está totalmente disponible.
- La disponibilidad se vuelve a validar al confirmar la generación de lotes para evitar inconsistencias si el stock cambió mientras el asistente estaba abierto.
- Antes de marcar una OF como hecha se exige nuevamente disponibilidad completa de los componentes.
- Para productos terminados controlados por lote se mantiene además la obligación de tener una distribución de lotes válida antes de producir.
- No se modifica el comportamiento de movimientos de ventas, compras, transferencias ni ajustes de inventario.
