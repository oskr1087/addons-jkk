# -*- coding: utf-8 -*-

{
    "name"          : "QZ Tray Base",
    "summary"       : "Base module for QZ Tray integration",
    "description"   : """QZ Tray Base is a foundational module required to support printing related features using QZ Tray. 
    It enables seamless communication between Odoo and local printers when used together with our utility modules.
    """,
    "version"       : "19.0.1.0.0",
    "author"        : "Oscar Morocho<oscar.morocho@gateway-resources.com>",
    "company"       : "Gateway Resources",
    "license"       : "OPL-1",
    "website"       : "https://gateway-resources.com",
    "sequence"      : 6,
    "category"      : "Extra Tools",
    "depends"       : ['web'],
    "data"          : [],
    "assets"        : {
                    "web.assets_backend":[
                        "qz_tray_base/static/src/js/qz_tray_lib.js",
                        "qz_tray_base/static/src/js/qz.js",
                    ],
    },
    "application"   : True,
    "installable"   : True,
    "auto_install"  : False,
}
