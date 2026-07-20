{
    'name': 'Stock Move Auto Lot Prefix',
    'version': '19.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Auto generate lot sequences per product category with prefix',
    'author': 'Oscar Morocho<oscar.morocho@gateway-resources.com>',
    'website': 'https://www.gateway-resources.com',
    'license': 'OPL-1',
    'depends': ['stock', 'product'],
    'data': [
        'security/ir.model.access.csv',
        'views/product_category_views.xml',
        #'views/stock_move_line_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}
