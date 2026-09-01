{
    'name': 'Agrogood - Rutas y reparto',
    'summary': 'Rutas con paradas secuenciadas, conductores, capacidad y evidencia de entrega',
    'description': """
Agrogood - Rutas y reparto
==========================

Odoo sabe que hay albaranes listos para salir, pero no en que camion van, con
quien ni en que orden. Este modulo aporta esa capa.

**La parada apunta al albaran, nunca lo reemplaza.** El movimiento de stock lo
sigue haciendo Odoo al validar; lo que la parada anade es el orden, la ventana
horaria y lo que ocurrio de verdad al llegar.

**El optimizador geografico no se implementa, se deja enganchado.** Calcular
rutas optimas exige un servicio de mapas externo con su coste y su clave, y esa
decision no esta tomada. Lo que si esta hecho es todo lo que ese optimizador
necesitaria: las paradas ya llevan secuencia, coordenadas y ventana horaria, de
modo que conectarlo sera escribir el cuerpo de un metodo y no rediseniar nada.
""",
    'author': 'Agrogood',
    'website': 'https://www.agrogood.cl',
    'category': 'Agrogood',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'depends': [
        'agrogood_picking_ops',
        'fleet',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'views/agrogood_route_views.xml',
        'views/fleet_vehicle_views.xml',
        'views/agrogood_vehicle_check_views.xml',
        'wizard/agrogood_route_add_pickings_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
}
