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
