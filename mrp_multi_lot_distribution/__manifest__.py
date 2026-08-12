{
    "name": "Distribución de múltiples lotes MRP",
    "category": "Fabricación",
    "summary": "Produce una orden de fabricación en varios lotes con cantidades por lote",
    "description": """
Distribución de múltiples lotes MRP
===================================
Permite utilizar varios lotes de producción en una orden de fabricación
controlada por lotes. La cantidad asignada a cada lote se mantiene en una
 distribución independiente y, al validar, se convierte en líneas de movimiento
 de inventario.
""",
    "author": "Oscar Morocho<oscar.morocho@gateway-resources.com>",
    "license": "LGPL-3",
    "depends": ["mrp", "stock"],
    "data": [
        "data/ir_sequence_data.xml",
        "security/ir.model.access.csv",
        "views/mrp_production_lot_distribution_views.xml",
        "views/mrp_production_lot_wizard_views.xml",
        "views/mrp_production_views.xml",
        "views/mrp_workcenter_views.xml",
    ],
    "installable": True,
    "application": False,
}
