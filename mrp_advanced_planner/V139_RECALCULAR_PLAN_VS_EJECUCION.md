# v139 - Recalcular: separar plan APS de ejecución

- `to_manufacture_qty` conserva la cantidad total decidida por APS.
- `pending_manufacture_qty` indica únicamente la cantidad aún no cubierta por OF activas del mismo nodo APS.
- Las OF del mismo plan ya no se consideran oferta genérica por producto durante Recalcular.
- La cobertura de OF se aplica por `aps_planning_component_id`, evitando cruces entre ramas con el mismo producto.
- Fabricar/procurement usa `pending_manufacture_qty`, haciendo la ejecución idempotente.
