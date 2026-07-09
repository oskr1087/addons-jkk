{
    "name": "Report JKKPAK Custom",
    "summary": "Report Purchase Sale",
    "description": """
Report Purchase Sale
    """,
    "author": "Oscar Morocho",
    "website": "https://www.gateway-resources.com",
    "category": "Tools",
    "version": "19.0.1",
    # any module necessary for this one to work correctly
    "depends": [
        "sale",
        "mrp",
    ],
    # always loaded
    "data": [
        # 'security/ir.model.access.csv',
        "views/mrp_production_views.xml",
        "views/report_mrporder_inherit.xml",
        "views/report_mrp_components.xml",
        "views/purchase_order_views.xml",
        "views/purchase_order_report.xml"
    ],
    "license": "OPL-1",
}
