{
    'name': 'Agrogood - Pizarra de compras',
    'summary': 'Solicitudes de compra entre Logistica y Compras, con estados y conversacion',
    'description': """
Agrogood - Pizarra de compras
=============================

El tablero de trabajo del Encargado de Compras. Recoge lo que hay que
conseguir -venga de un faltante de pedido o de una peticion directa de
Logistica-, lo pasea por sus estados y termina en una orden de compra.

**Por que un modelo propio y no `purchase.requisition`.** El modulo estandar
resuelve *acuerdos de compra*: ordenes abiertas y plantillas ligadas a un
proveedor y a un periodo de validez. Aqui el problema es otro: "Felipe
necesita 70 kg de tomate hoy para tal cliente, a ver donde se consiguen".
Distinto ciclo, distintos estados y distinta conversacion.

**La conversacion no se inventa.** Logistica y Compras hablan por el chatter de
`mail.thread`, con historial, menciones y actividades. Construir un sistema de
mensajes propio seria reimplementar peor algo que Odoo ya hace bien.
""",
    'author': 'Agrogood',
    'website': 'https://www.agrogood.cl',
    'category': 'Agrogood',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'depends': [
        'agrogood_sales',
        'purchase_stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'views/agrogood_purchase_request_views.xml',
        'views/sale_order_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
}
