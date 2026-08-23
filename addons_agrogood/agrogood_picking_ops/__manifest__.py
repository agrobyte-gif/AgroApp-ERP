{
    'name': 'Agrogood - Preparacion de pedidos',
    'summary': 'Asignacion a Pickers, tiempos, resultado por linea y peso real',
    'description': """
Agrogood - Preparacion de pedidos
=================================

Convierte la preparacion en trabajo medible.

`stock.picking` sabe QUE hay que preparar, pero no QUIEN lo prepara, CUANDO
empezo ni CUANTO tardo. Eso es lo que aporta la sesion de preparacion, y es lo
que el Jefe de Logistica necesita para repartir carga y ver donde se atasca el
dia.

El resultado de cada linea -confirmado, faltante, sustituido, cancelado, no
encontrado- vive en `stock.move`, no en un modelo paralelo. Duplicar las lineas
obligaria a mantener dos verdades en sincronia, y acabarian discrepando.

Implementa ademas la regla de ADR-003 sobre peso variable: preparar 19,4 kg de
los 20 pedidos NO genera pedido en espera, porque esos 0,6 kg no son una
entrega pendiente sino lo que peso la caja.
""",
    'author': 'Agrogood',
    'website': 'https://www.agrogood.cl',
    'category': 'Agrogood',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'depends': [
        'agrogood_sales',
        'stock_picking_batch',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/agrogood_picking_session_views.xml',
        'views/stock_picking_views.xml',
        'wizard/agrogood_assign_picker_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
}
