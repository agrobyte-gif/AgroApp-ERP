{
    'name': 'Agrogood - Precios',
    'summary': 'Carga semanal de precios por linea comercial, con vigencias e historial',
    'description': """
Agrogood - Precios
==================

Ventas cambia precios cada semana. Este modulo hace que ese cambio sea una
operacion revisable y reversible en lugar de una edicion masiva a mano.

Se apoya en las tarifas estandar de Odoo: `product.pricelist.item` ya soporta
`date_start` y `date_end`, de modo que el versionado no necesita un modelo
paralelo de precios. Lo que se aporta es el proceso:

* Preparar una version en borrador, comparandola con la vigente.
* Ver la variacion producto a producto antes de publicar.
* Publicar en bloque, abriendo los items nuevos y cerrando los anteriores.

Los precios anteriores nunca se modifican: se cierra su vigencia. Los pedidos
historicos conservan su precio porque `sale.order.line` almacena el precio
unitario como dato propio.
""",
    'author': 'Agrogood',
    'website': 'https://www.agrogood.cl',
    'category': 'Agrogood',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'depends': [
        'agrogood_base',
        'product',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/agrogood_price_version_views.xml',
        'views/agrogood_pricing_menus.xml',
    ],
    'installable': True,
}
