{
    'name': 'Planificador Simple de Fabricación',
    'version': '19.0.7.3.0',
    'category': 'Fabricación/Fabricación',
    'summary': 'Planificación rápida de fabricación basada en ventas pendientes hasta una fecha',
    'author': 'Planificador APS',
    'license': 'LGPL-3',
    'depends': ['base', 'stock', 'sale_management', 'purchase', 'mrp', 'resource'],
    'data': [
        'security/planner_security.xml',
        'security/ir.model.access.csv',
        'data/planner_data.xml',
        'data/planner_menu_root.xml',
        'wizard/planning_approval_wizard_views.xml',
        'views/sale_order_views.xml',
        'views/mrp_production_views.xml',
        'views/planning_plan_views.xml',
        'views/planning_dashboard_views.xml',
        'views/planning_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mrp_advanced_planner/static/src/js/planning_dashboard.js',
            'mrp_advanced_planner/static/src/xml/planning_dashboard.xml',
            'mrp_advanced_planner/static/src/scss/planning_dashboard.scss',
        ],
    },
    'installable': True, 'application': True,
}
