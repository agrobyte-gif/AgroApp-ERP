{
    'name': 'Agrogood - Seguimiento de conductores',
    'summary': 'Posicion del conductor durante la ruta y mapa para Logistica',
    'description': """
Agrogood - Seguimiento de conductores
=====================================

Recibe las posiciones que envia el telefono del conductor y las muestra en un
mapa para Logistica.

**El rastreo existe solo mientras la ruta esta en curso.** Es una decision
deliberada y esta impuesta en el endpoint, no solo en la app: si la ruta no
esta en marcha, el servidor rechaza la posicion y le dice al telefono que deje
de enviar. Una herramienta que sigue al trabajador fuera de su jornada deja de
ser una herramienta.

Un conductor solo ve su propio rastro. El dato existe para coordinar el
reparto, no para que se vigilen entre ellos.

Los rastros de rutas cerradas se borran a los 60 dias. Por volumen, y porque
guardar indefinidamente el recorrido de una persona no tiene justificacion una
vez pasado el plazo en que un cliente puede reclamar una entrega.

Leaflet va empaquetado en el modulo, no desde un CDN: la bodega puede quedarse
sin internet y el mapa debe seguir abriendo con lo ya guardado. Los mosaicos
vienen de OpenStreetMap, gratuito y sin clave.
""",
    'author': 'Agrogood',
    'website': 'https://www.agrogood.cl',
    'category': 'Agrogood',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'depends': [
        'agrogood_logistics',
        'agrogood_dashboards',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/tracking_security.xml',
        'views/templates.xml',
        'views/menus.xml',
        'data/ir_cron.xml',
    ],
    'installable': True,
}
