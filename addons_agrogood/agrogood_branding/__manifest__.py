{
    'name': 'Agroapp - Marca',
    'summary': 'La aplicacion se presenta como Agroapp en todo lo que ve el usuario',
    'description': """
Agroapp - Marca
===============

Cambia la marca visible: titulo de la pestana, favicon, icono de la
aplicacion, pie de pagina y pantalla de acceso pasan a decir Agroapp.

**No se renombra el codigo, y es deliberado.** El paquete Python sigue
llamandose `odoo`, las tablas siguen siendo `ir_*` y `res_*`, y los
identificadores internos no cambian. Renombrarlos afectaria a 3.799 archivos y,
sobre todo, impediria aplicar cualquier actualizacion futura de Odoo: cada
parche oficial dejaria de encajar. Lo que se cambia es la capa que el equipo
lee, que es de lo que se trata.

La licencia LGPL-3 de Odoo Community permite exactamente esto: modificar el
software y presentarlo con marca propia. Lo que no seria legitimo es lo
contrario, usar la marca Odoo para un producto que ya no lo es.
""",
    'author': 'Agrogood',
    'website': 'https://www.agrogood.cl',
    'category': 'Agrogood',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['web'],
    'data': [
        'views/branding_templates.xml',
        'data/agroapp_data.xml',
    ],
    'assets': {
        # Las variables van ANTES que todo lo demas: definen el color que el
        # resto de hojas de estilo compila encima.
        'web._assets_primary_variables': [
            ('prepend', 'agrogood_branding/static/src/scss/primary_variables.scss'),
        ],
        'web.assets_backend': [
            'agrogood_branding/static/src/js/branding.js',
        ],
    },
    'installable': True,
    'auto_install': False,
}
