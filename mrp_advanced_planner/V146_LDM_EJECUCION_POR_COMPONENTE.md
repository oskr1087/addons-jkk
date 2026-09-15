# v146 - LdM a ejecutar por componente APS

- Selección editable de LdM directamente en el árbol de Componentes de la OF.
- La selección es por nodo APS, no por producto.
- Admite LdM normal, kit/phantom y subcontratación.
- Al cambiar la LdM se reconstruye únicamente la rama del componente y se refresca sourcing.
- La LdM elegida gobierna fabricación/subcontratación y se fuerza en procurement nativo de sub-OF.
- Recalcular conserva la selección existente; no se reemplaza por find_bom durante sourcing.
- La ingeniería queda bloqueada una vez generada la OF correspondiente.
