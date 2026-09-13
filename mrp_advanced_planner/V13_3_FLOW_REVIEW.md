# APS v13.3 - flujo de fabricación revisado

## Regla operativa

1. Calcular:
   - detecta demanda;
   - explota LdM;
   - clasifica Disponible / Mover / Fabricar / Comprar;
   - reserva lotes físicos que ya existan;
   - crea/actualiza únicamente el PLAN APS de compras, no órdenes de compra.

2. Fabricar:
   - crea la OF raíz;
   - Odoo crea sub-OF nativas para componentes fabricables;
   - las OF pueden quedar confirmadas aun con abastecimiento futuro pendiente;
   - se reserva automáticamente todo stock físicamente disponible;
   - la creación de OF no se bloquea por un lote todavía pendiente.

3. Recepciones:
   - Odoo incrementa stock real;
   - APS sincroniza lotes pendientes con las OF consumidoras.

4. Iniciar / finalizar producción:
   - bloqueado si falta stock físico reservado;
   - bloqueado si un producto stockeable con seguimiento no tiene cobertura completa de lote.

5. Protección entre APS:
   - la misma APS puede utilizar sus propias reservas a través de OF padre/sub-OF;
   - otra APS no puede invadir la cantidad protegida.
