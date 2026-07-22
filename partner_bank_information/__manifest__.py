{
    "name": "Partner Bank Information",
    "version": "19.0.1.0.0",
    "category": "Contacts",
    "summary": "Bank information for Contacts",
    "description": """
Adds bank information to Contacts.

Features
--------
* Bank
* Bank Branch
* Account
* IBAN
* Payment Method
    """,
    "author": "Custom",
    "website": "",
    "license": "LGPL-3",
    "depends": [
        "contacts",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/payment_method_views.xml",
        "views/res_partner_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
}
