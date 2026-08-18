# Stock Accounting by Warehouse — Odoo 19.0

Módulo exclusivo para Odoo 19.0.

## Nueva pestaña

En Inventario > Configuración > Almacenes se agrega la pestaña:

**Contabilidad de Inventario**

## Interruptor

**Usar contabilidad de inventario del almacén**

- Desactivado: Odoo conserva la configuración estándar.
- Activado: se utilizan las cuentas y diario definidos en el almacén.

## Campos

- Cuenta de valoración de inventario
- Cuenta de variación de inventario (derivada de la cuenta de valoración)
- Diario de inventario
- Cuenta contrapartida de entrada
- Cuenta contrapartida de salida

## Validaciones

Al activar la funcionalidad son obligatorios:
- Cuenta de valoración
- Diario de inventario
- Contrapartida de entrada
- Contrapartida de salida

Las cuentas no pueden ser de tipo:
- Por cobrar
- Por pagar
- Banco/Efectivo
- Tarjeta de crédito

El diario debe ser de tipo General/Misceláneo.

## Compatibilidad con Odoo 19

Odoo 19 obtiene la cuenta de valoración desde la categoría/compañía y el diario
de stock desde categoría/compañía. Para determinados movimientos, las
contrapartidas se apoyan en la cuenta de valoración de las ubicaciones.

Este módulo mantiene intactos:
- FIFO
- AVCO
- costo estándar
- cálculo del valor del movimiento
- reservas
- cantidades
- valoración física

Solo cambia la determinación contable cuando el interruptor del almacén está activo.


## Unit / integration tests

The module contains a `post_install` test suite based on Odoo 19's official
`TestStockValuationCommon`.

Covered scenarios:

1. Feature disabled by default.
2. Complete configuration required before activation.
3. Invalid account types rejected.
4. Disabled mode preserves Odoo standard behavior.
5. Incoming accounting uses warehouse valuation/input accounts and journal.
6. Outgoing accounting uses warehouse output/valuation accounts and journal.
7. Destination warehouse is correctly detected in multi-warehouse.
8. Internal transfers do not generate extra valuation journal entries.
9. Variation account follows the selected valuation account.

Example execution:

    ./odoo-bin -d TEST_DB -i stock_account_by_warehouse         --test-enable         --test-tags /stock_account_by_warehouse         --stop-after-init


## 19.0.5.0.0

- Corregido `_create_account_move()` para la API real de Odoo 19.
- Eliminada la llamada inexistente a `_get_partner_id_for_valuation_lines()`.
- Los asientos se agrupan por compañía + diario efectivo.
- Agregado test de regresión para este error.

## 19.0.6.0.0

Ajustes de compatibilidad de tests con la API real de Odoo 19:

- `account.move.amount_total` no se usa para comprobar el balance de un asiento.
  El test ahora compara la suma de débitos contra la suma de créditos.
- `stock.move.name` ya no es un campo válido en Odoo 19.
  El test de transferencia interna usa `description_picking`.
