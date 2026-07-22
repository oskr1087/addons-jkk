# -*- coding: utf-8 -*-
{
    "name"          : "Product Label & ZPL Report Direct Print",
    "description"   : """This module allows you to directly send ZPL reports for printing without downloading or manual intervention. 
    It enables fast and reliable printing of ZPL based labels and reports from Odoo.
    """,
    "version"       : "19.0.1.0.0",
    "author"        : "Oscar Morocho<oscar.morocho@gateway-resources.com>",
    "company"       : "Gateway Resources",
    "license"       : "OPL-1",
    "website"       : "https://gateway-resources.com",
    "sequence"      : 8,
    "category"      : "Extra Tools",
    "depends"       : ['qz_tray_base'],
    "data"          : [],
    "assets"        : {
                    "web.assets_backend":[
                        "qz_tray_report/static/src/js/*",
                    ],
    },
    "application"   : True,
    "installable"   : True,
    "auto_install"  : False,
}
