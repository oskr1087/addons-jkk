# v145 - Ejecución completa de subcontratación

- Fabricar crea la OF interna faltante para materiales directos de una LdM de subcontratación cuando APS los clasifica como `manufacture`.
- Esa OF queda enlazada al nodo APS exacto y usa los descendientes congelados del snapshot.
- Los descendientes fabricables de esa OF continúan por la cadena nativa de procurement de Odoo.
- El Plan de Compras prioriza `subcontract_bom_id.subcontractor_ids` como proveedor del producto subcontratado.
- Las compras normales siguen usando `supplierinfo`.
- Calcular/Recalcular continúan sin crear documentos de ejecución.
