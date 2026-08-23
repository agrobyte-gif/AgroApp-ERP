{
    'name': 'Agrogood - Ventas',
    'summary': 'Captura rapida de pedidos, estado operativo y deteccion de faltantes',
    'description': """
Agrogood - Ventas
=================

Adapta el flujo de venta de Odoo a como trabaja Agrogood: pedidos que llegan
por WhatsApp, se preparan el mismo dia y se facturan por lo que realmente se
entrego.

Aporta tres cosas:

**Estado operativo derivado.** Las once etapas por las que pasa un pedido no se
guardan en un campo aparte que alguien deba mantener al dia: se calculan a
partir del estado real del pedido, de sus albaranes y de sus facturas. Un
estado paralelo que hay que sincronizar a mano acaba mintiendo, y el dia que
miente lo hace en el peor momento.

**Excepciones explicitas.** Lo que si es informacion nueva -cliente ausente,
direccion incorrecta, reprogramado- se registra aparte, porque no se deduce de
ningun dato del sistema.

**Faltantes.** Cada linea sabe cuanto falta para servirla completa. El modulo
solo detecta y expone; quien convierte eso en una solicitud de compra es
`agrogood_procurement_board`.
""",
    'author': 'Agrogood',
    'website': 'https://www.agrogood.cl',
    'category': 'Agrogood',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'depends': [
        'agrogood_base',
        'agrogood_security',
        'sale_stock',
        'l10n_cl',
    ],
    'data': [
        'views/sale_order_views.xml',
        'views/agrogood_business_line_views.xml',
    ],
    'installable': True,
}
