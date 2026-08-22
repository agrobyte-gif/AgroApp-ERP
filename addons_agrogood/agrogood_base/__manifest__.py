{
    'name': 'Agrogood - Base',
    'summary': 'Cimiento comun de la plataforma Agrogood: lineas comerciales y roles',
    'description': """
Agrogood - Base
===============

Modulo fundacional de la plataforma Agrogood. No modifica el nucleo de Odoo:
todo se extiende por herencia.

Aporta:

* Linea comercial (HORECA / Mayorista / Minorista) como dato maestro, asociada
  al cliente y a una tarifa por defecto.
* Los grupos de seguridad transversales sobre los que el resto de modulos
  ``agrogood_*`` declara sus permisos.
""",
    'author': 'Agrogood',
    'website': 'https://www.agrogood.cl',
    'category': 'Agrogood',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'contacts',
        'product',
    ],
    'data': [
        'security/agrogood_security.xml',
        'security/ir.model.access.csv',
        'views/agrogood_business_line_views.xml',
        'views/res_partner_views.xml',
        'views/agrogood_menus.xml',
        'data/agrogood_business_line_data.xml',
    ],
    'installable': True,
    'application': True,
}
