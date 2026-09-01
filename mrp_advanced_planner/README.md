# Planificador Simple de Fabricación - Odoo 19

## Versión 19.0.6.0.0

La demanda se planifica por **línea de pedido de venta** y no por pedido completo.

Cada `sale.order.line` dispone de `planning_delivery_date` (Fecha de entrega planificación):
- toma por defecto `sale.order.commitment_date`;
- conserva una fecha personalizada por línea;
- puede restablecerse a la fecha del pedido;
- el planner únicamente considera líneas confirmadas cuya fecha esté dentro del horizonte del plan.

El cálculo asigna cronológicamente, por producto:
1. cantidad pendiente de entregar;
2. inventario libre disponible;
3. órdenes de fabricación abiertas cuya fecha prevista permite cubrir la línea;
4. necesidad sugerida a fabricar.

La línea del planner mantiene trazabilidad con pedido, cliente, línea de venta y fecha de entrega. La cantidad `Fabricar` sigue siendo editable y la línea puede eliminarse antes de aprobar. Al aprobar se crea una OF por línea incluida, vinculada al plan y a la línea de venta origen.


## Validación de entregas antes de aprobar
- Solo se planifican líneas con cantidad pendiente de entrega (`product_uom_qty - qty_delivered > 0`).
- Antes de abrir la aprobación y nuevamente antes de crear las OF, se valida que la línea siga pendiente, que no haya cambiado su cantidad pendiente ni su fecha de entrega y que continúe dentro del horizonte.
- Si cambió la demanda, el usuario debe recalcular el plan.


## 19.0.7.0.0
- Dashboard de órdenes de fabricación con estado y progreso.
- Seguimiento de centros de trabajo y producto actualmente en fabricación.
- Planificación de origen visible y navegable desde mrp.production.


## Snapshot de ingeniería APS y optimización de componentes

- La explosión de Listas de Materiales precarga el grafo por niveles y realiza la recursión en memoria.
- La jerarquía se conserva mediante `parent_line_id`.
- Las planificaciones de fabricación congelan un snapshot editable de componentes.
- Solo las OF creadas por APS usan ese snapshot; las OF estándar conservan el comportamiento nativo.
- Los componentes pueden quedar como originales, modificados, sustituidos, agregados manualmente u omitidos.
- La consulta detallada por almacén usa modelos `TransientModel` y solo ubicaciones internas de la compañía.
- Compras calcula disponibilidad con stock libre (`On Hand - Reservado`) más PO confirmadas pendientes dentro del horizonte.


## Ajustes 19.0.20.0.0

- Las líneas de venta se filtran estrictamente por `planning_delivery_date <= date_end`.
- El árbol de componentes permite sustituir, cambiar cantidades, agregar hijos y eliminar nodos completos antes de generar OF.
- Cada cambio de ingeniería refresca la resolución de abastecimiento.
- Los componentes con una LdM de tipo `subcontract` se identifican como Subcontratación y su faltante entra al Plan de Compras.
- Los hijos de un componente subcontratado permanecen visibles para ingeniería, pero no se compran de forma separada desde APS.


## Trazabilidad bidireccional 19.0.21.0.0

La trazabilidad APS se mantiene mediante relaciones reales entre documentos:

`SO / línea SO → línea APS → Planificador → OF / PO / traslado`

y en sentido inverso:

`OF / PO / línea PO / traslado → línea APS → línea SO → SO`.

Las columnas de trazabilidad en listas son opcionales (`optional="hide"`) para
no sobrecargar la interfaz. Las SO, OF y PO disponen además de navegación
directa mediante smart buttons cuando existen documentos relacionados.

Las necesidades de compra provenientes de componentes de fabricación heredan
las líneas de venta del producto terminado, por lo que una PO de materia prima
puede rastrearse hasta las SO originales.


## Componentes APS modificados - 19.0.27.0.0

El snapshot APS es la fuente de ingeniería de las OF generadas por el
planificador.

- Línea original sin cambios: conserva `bom_line_id`.
- Cantidad modificada: movimiento manual APS sin `bom_line_id`.
- Producto sustituido: movimiento manual APS sin `bom_line_id`.
- Componente agregado manualmente: movimiento manual APS sin `bom_line_id`.
- Línea omitida: no se genera en la OF.

Esto evita que Odoo vuelva a comparar una modificación intencional del
planificador contra la cantidad de la LdM original al validar/finalizar la OF.
