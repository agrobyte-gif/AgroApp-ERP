{
    'name': 'Agrogood - Conciliacion de cobros',
    'summary': 'Lee la cartola del banco y dice quien pago',
    'description': """
Agrogood - Conciliacion de cobros
=================================

Hoy alguien abre la cartola del banco y busca a mano que factura corresponde a
cada abono. Con 153 clientes y varios miles de movimientos al mes eso es media
jornada, y se equivoca.

Este modulo lee el archivo que exporta el banco -sin tocar la contabilidad- y
para cada abono dice de que cliente viene. Lo que no reconoce se enlaza una
vez, y a partir de entonces se reconoce solo: es la unica forma de cruce que
mejora con el uso.

**El cruce es por RUT en los tres bancos.** Scotiabank lo publica en una
columna propia. Santander no: lo mete al principio de la descripcion, relleno
de ceros -`00763341712` es `76334171-2`-, y por eso parecia que no lo traia. Se
midio sobre una cartola real: **el 95% de los abonos de Santander lo llevan
ahi**. El alias del banco queda como recurso para el 5% restante.

**Un RUT no siempre es un solo cliente.** En la misma cartola, 108 de 523 RUT
pagaron facturas de mas de un negocio: la sociedad que paga por dos locales, el
dueno que paga por el suyo y por el de un socio. Cuando pasa, el abono queda
marcado como dudoso y espera a una persona. Repartir ese cobro solo seria dar
por pagada la factura del otro.

La cobranza se lleva sobre la **orden de compra** y no sobre facturas: Agrogood
emite sus documentos en el portal del SII, de modo que en Odoo no hay ni una
factura de venta (ADR-006). Se debe **lo entregado**, no lo pedido, que es la
misma regla que aplica la facturacion.

Un abono se reparte entre las ordenes pendientes de la mas antigua a la mas
nueva, porque una transferencia suele cubrir varias entregas. Lo que sobra se
ve sobrar: forzarlo a cuadrar seria inventar la deuda que falta.
""",
    'author': 'Agrogood',
    'website': 'https://www.agrogood.cl',
    'category': 'Agrogood',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'depends': [
        'agrogood_crm_reactivation',
        'account',
        'sale_management',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/agrogood_bank_movement_views.xml',
        'views/cuenta_corriente_views.xml',
        'wizard/agrogood_bank_import_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
}
