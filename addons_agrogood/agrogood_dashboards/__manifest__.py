{
    'name': 'Agrogood - Paneles por rol',
    'summary': 'Un panel para Ventas, Logistica, Compras y Direccion',
    'description': """
Agrogood - Paneles por rol
==========================

Cuatro paneles, uno por rol administrativo. Los de Picker y Conductor no estan
aqui: son la PWA, que ya es su pantalla completa.

Cada panel se arma con vistas del propio dato -lista, kanban, pivote, grafico-
en lugar de con un modelo de indicadores aparte. La razon es practica: un
numero sobre el que no se puede hacer clic obliga a abrir otra pantalla para
actuar, y entonces nadie lo mira dos veces. Aqui cada cifra ES la lista de
trabajo: se ve y se resuelve en el mismo sitio.

Se anade la linea comercial al informe de ventas, porque sin ella no se puede
responder a la pregunta mas basica de Direccion: cuanto vende cada linea.
""",
    'author': 'Agrogood',
    'website': 'https://www.agrogood.cl',
    'category': 'Agrogood',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'depends': [
        'agrogood_crm_reactivation',
        'agrogood_logistics',
        'agrogood_procurement_board',
    ],
    'data': [
        'views/dashboard_views.xml',
        'views/completar_rut_views.xml',
    ],
    'installable': True,
}
