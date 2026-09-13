# v142 - Materiales de subcontratación con abastecimiento y lotes

- Un nodo subcontratado sigue comprándose como producto/servicio subcontratado.
- Sus materiales directos ya no se fuerzan a necesidad efectiva 0.
- APS evalúa stock, faltantes, fabricación/compra y lotes para la cantidad realmente subcontratada.
- Los materiales directos se marcan como `is_subcontract_material`.
- La interfaz muestra acciones específicas: Enviar/Fabricar/Comprar para subcontratista.
- Si el padre ya está totalmente cubierto por stock, sus materiales no generan demanda adicional.
