{
    'name': 'Agrogood - Aplicacion movil',
    'summary': 'PWA para Pickers y Conductores, con sus reglas de acceso',
    'description': """
Agrogood - Aplicacion movil
===========================

La pantalla desde la que trabajan Pickers y Conductores. Ninguno de los dos
entra al backend de Odoo: no lo necesitan y no deben.

**Por que no se usa el cliente web de Odoo.** Su bundle pesa varios megabytes y
esta pensado para escritorio. Aqui se sirven paginas QWeb autonomas con
JavaScript minimo, de modo que una tablet de bodega o un telefono con datos
moviles abran la pantalla en un segundo.

**Aqui se cierran las reglas de registro** que la fase 2 dejo pendientes a
proposito: entonces no existian los modelos a los que aplicarse. Un Picker solo
ve sus preparaciones, un Conductor solo sus rutas, y ambos solo los clientes a
los que estan sirviendo. La restriccion vive en la regla, no en la interfaz:
esconder un menu no impide nada a quien construya una peticion a mano.
""",
    'author': 'Agrogood',
    'website': 'https://www.agrogood.cl',
    'category': 'Agrogood',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'depends': [
        'agrogood_logistics',
        'agrogood_bank',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/agrogood_pwa_security.xml',
        'views/templates.xml',
        'views/ventas_templates.xml',
        'views/bodega_templates.xml',
        'views/logistica_templates.xml',
        'views/compras_templates.xml',
        'views/direccion_templates.xml',
        'views/cobranza_templates.xml',
    ],
    'installable': True,
}
