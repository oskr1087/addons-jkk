# Reacondicionamiento de Fabricación - Odoo 19

Módulo para gestionar reacondicionamientos de productos terminados que fueron entregados a un cliente y posteriormente devueltos.

## Principios del proceso

- Todo reacondicionamiento debe estar vinculado obligatoriamente a una devolución de cliente validada.
- No se permite producir un reacondicionamiento desde una recepción manual o una devolución sin relación con una entrega original.
- El producto devuelto se agrega como componente de la nueva orden de reacondicionamiento.
- El producto terminado conserva exactamente el mismo lote o número de serie devuelto por el cliente.
- Si una devolución contiene varios lotes del mismo producto, se crea una orden de reacondicionamiento independiente por cada lote.
- Si el producto tiene seguimiento por número de serie, se crea una orden independiente por cada número de serie.
- Los componentes y lotes utilizados en la fabricación original se conservan como trazabilidad histórica y no se vuelven a consumir automáticamente.
- Los materiales adicionales del reacondicionamiento pueden agregarse como componentes normales de la orden.

## Flujo recomendado

1. Registrar la entrega al cliente.
2. Crear y validar la devolución desde la entrega original.
3. En la devolución validada, pulsar **Reacondicionar**.
4. El sistema crea automáticamente la orden `REAC/xxxxx` con producto, cantidad, lote/número de serie, pedido de venta, devolución y orden de fabricación original cuando puede identificarla de forma unívoca.
5. Agregar los componentes adicionales necesarios: caja, etiqueta, film, repuestos, etc.
6. Confirmar y procesar el reacondicionamiento.
7. El sistema impide finalizar si el lote consumido o producido no coincide con el lote devuelto.

## Menú

**Manufactura > Reacondicionamientos**

Incluye órdenes de reacondicionamiento y configuración de motivos.


## Versión 19.0.1.3.0
- Sincroniza el lote/serie devuelto en `lot_producing_ids`, `move_finished_ids.lot_ids` y las líneas del producto terminado antes de cerrar la orden.
- Evita validaciones falsas de “orden sin lotes” al usar **Producir todo**.
- Agrega un formulario exclusivo de Reacondicionamiento, totalmente en español y separado de las vistas de fabricación normales.


## Integración con Distribución de múltiples lotes

El módulo depende de `mrp_multi_lot_distribution`. Cuando el producto devuelto está controlado por lote, el reacondicionamiento crea automáticamente la distribución de lotes con el mismo lote de la devolución y la cantidad a reacondicionar. La pestaña **Lotes** es informativa en el formulario de reacondicionamiento y no permite sustituir el lote devuelto.


## Compatibilidad con mrp_multi_lot_distribution

Para productos controlados por lote, la devolución es la fuente de verdad. Al crear una REAC el módulo crea inmediatamente `mrp.production.lot.distribution` y una única línea con el lote devuelto y la cantidad a producir. Antes de finalizar se ejecutan las mismas validaciones del módulo de distribución: lote del producto correcto, sin duplicados, cantidad positiva y suma distribuida igual a `qty_producing`. La creación de líneas terminadas por lote queda a cargo de `mrp_multi_lot_distribution` para evitar duplicidad o conflictos.


## Compatibilidad qty_producing (19.0.1.6.0)

Antes de confirmar, iniciar o finalizar un reacondicionamiento, el módulo sincroniza `qty_producing` con la cantidad pendiente del REAC y luego actualiza la distribución de lotes. Esto evita diferencias como `A producir: 0.0 / Distribuido: 1.0` y mantiene intactas las validaciones de `mrp_multi_lot_distribution`.


## Integración de vistas

Las órdenes de reacondicionamiento tienen menú, lista y búsqueda independientes, pero utilizan
el formulario estándar de `mrp.production`. Esto permite conservar automáticamente todas las
herencias de otros módulos instalados sobre Manufactura, incluyendo Tarimas, Empaquetado,
Etiquetas, Taller y otras personalizaciones. Los campos específicos se muestran en la pestaña
**Reacondicionamiento** únicamente cuando `is_reconditioning = True`.
