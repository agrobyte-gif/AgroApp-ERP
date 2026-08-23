{
    'name': 'Agrogood - Roles operativos',
    'summary': 'Conecta los roles de Agrogood con los grupos estandar de Odoo',
    'description': """
Agrogood - Roles operativos
===========================

`agrogood_base` define QUIEN es cada rol. Este modulo define QUE puede hacer,
y lo hace apoyandose en los grupos que Odoo ya trae en lugar de inventar un
sistema de permisos paralelo.

La razon de que sea un modulo aparte es de dependencias: mapear roles contra
Ventas, Compras, Inventario y Contabilidad obliga a depender de esos modulos.
Ponerlo en `agrogood_base` arrastraria contabilidad hasta la PWA de los
Pickers, que solo necesita saber que existe el grupo.

Principio: si Odoo ya restringe algo correctamente, no se reescribe. Las
reglas propias se reservan para lo que el estandar no cubre.
""",
    'author': 'Agrogood',
    'website': 'https://www.agrogood.cl',
    'category': 'Agrogood',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'depends': [
        'agrogood_base',
        'sale_management',
        'sale_stock',
        'purchase_stock',
        'stock_account',
        'stock_picking_batch',
        'account',
        'crm',
    ],
    'data': [
        'security/agrogood_role_mapping.xml',
    ],
    'installable': True,
}
