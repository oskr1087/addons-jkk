{
    'name': 'Multi User Inventory Count / Stock Take',
    'version': '6.0',
    'category': 'Inventory',
    'license': 'OPL-1',
    'price': 419,
    'currency': 'EUR',

    # Author
    'author': 'Setu Consulting Services Pvt. Ltd.',
    'website': 'https://www.setuconsulting.com',
    'support': 'support@setuconsulting.com',

    'summary': """
        Inventory Count is the solution that helps to manage inventory that is to check and keep track record of physical inventory.
        inventory count, stock count, inventory management, stock management, stock analysis, inventory analysis, physical stock count, count inventories, employee performance, simultaneously inventory count, simultaneously stock count, approval, rejection, barcode scanning, track record, session management, work accuracy, discrepancy report, adjustment report, inventory adjustment report, statistic report,
        inventory, stock, warehouse, count, physical inventory, audit, adjustment, verification, management, reconciliation, setu, odoo19, automation, stocktake
        odoo ai, connector, integration, advance inventory management, stock in take, inventory automation module, Odoo inventory tools, how to manage physical inventory in Odoo 17
        automate stock count in Odoo ERP, best Odoo app for warehouse stock counting, physical stock vs system stock Odoo, Odoo stock difference adjustment module,
        Odoo warehouse inventory control app, simplify inventory verification in Odoo, inventory discrepancy correction Odoo, stocktake management app for Odoo,
        Odoo 17 physical inventory enhancement, Odoo inventory count management, Odoo physical inventory app, inventory adjustment Odoo 19,
        stock count automation Odoo, Odoo cycle count module, Odoo inventory audit tool, physical stock verification Odoo, inventory recount management Odoo,
        Odoo stock reconciliation module, Odoo warehouse stock counting,
    """,

    'description': """
        Inventory Count is the solution that helps to manage inventory that is to check and keep track record of physical inventory and the one with stock count in Inventory Management Software. Inventory Management is a crucial part of any business and so is maintaining the physical count of Inventory. Stock count in business helps you from avoiding stock out that is out of stock nightmares. For businesses of Warehouse management accurate stock present physically as the one in Inventory Software is most crucial. Inventory analysis by comparing physical Inventory with the one in software also allows you to check Employee Performance , Employee Activity Management , Manage Supervisor Activity on counting inventory , Employee overtime that is track time taken by employee in counting. This module will allow employee to check in/out within active work location time. Scanning products through a Barcode machine and entering the quantity counted physically can then be compared with one in the system.
    """,

    'images': ['static/description/banner.gif'],

    'depends': ['stock_account','purchase'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/base_setup_data.xml',
        'data/ir_cron.xml',
        'data/mail_template_data.xml',
        'views/setu_stock_inventory_count_views.xml',
        'views/setu_stock_inventory_count_planner_views.xml',
        'views/setu_inventory_count_session_views.xml',
        'views/setu_inventory_session_details_views.xml',
        'views/setu_stock_inventory_views.xml',
        'views/stock_location_views.xml',
        'views/stock_move_views.xml',
        'views/stock_move_line_views.xml',
        'views/res_config_settings_views.xml',
        'views/actions.xml',
        'views/inventory_dashboard_views.xml',
        'wizard_views/setu_inventory_session_creator_views.xml',
        'wizard_views/setu_inventory_session_validate_wizard_views.xml',
        'wizard_views/setu_inventory_warning_message_wizard_views.xml',
        'wizard_views/setu_extra_lot_found_wizard_views.xml',
        'report_views/setu_inventory_count_report_views.xml',
        'report_views/setu_inventory_adjustment_report_views.xml',
        'report_views/setu_inventory_session_user_report_views.xml',
        'report_views/setu_count_wise_discrepancy_report_views.xml',
        'report_views/setu_product_wise_discrepancy_report_views.xml',
        'report_views/setu_location_wise_discrepancy_report_views.xml',
        'report_views/setu_inventory_session_performance_report_views.xml',

    ],
    'assets': {
        'web.assets_backend': [
            "setu_inventory_count_management/static/src/js/setu_barcode_handler_field.js",
            "setu_inventory_count_management/static/src/js/setu_barcode_handler_field_view.xml",
            "setu_inventory_count_management/static/src/css/barcode.scss",
            "setu_inventory_count_management/static/src/js/inventory_dashboard.js",
            "setu_inventory_count_management/static/src/xml/inventory_dashboard_template.xml"
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': True,
}
