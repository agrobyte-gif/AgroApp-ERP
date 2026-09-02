"""Prueba de cambiar una orden y de dar de alta un cliente desde el telefono.

    odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/prueba_ventas_editar.py

Termina con rollback: no deja nada.

Se prueban los endpoints de verdad, no una copia de su logica. Para eso se
sustituye `request` por un objeto que solo lleva el `env`, que es lo unico que
usan: probar una reimplementacion de las reglas deja pasar justo los fallos que
importan, porque la reimplementacion siempre esta bien.

En orden de lo que cuesta si falla:

 1. Que NO se pueda cambiar un pedido que ya esta preparando alguien. Cambiar
    las lineas por debajo de un Picker le hace preparar lo que no se pide.
 2. Que no se cuele un producto sin precio, que saldria a cero.
 3. Que un RUT invalido no entre. Un RUT malo es un problema tributario, y se
    arregla mientras el cliente esta delante o no se arregla.
"""

from odoo.addons.agrogood_pwa.controllers import main as controlador
from odoo.addons.agrogood_pwa.controllers.main import AgrogoodVentas

R = []


def paso(t, ok, det=""):
    R.append(ok)
    print("  [%s] %s" % ("OK " if ok else "FALLA", t))
    if det:
        print("        %s" % det)


class PeticionFalsa(object):
    """Lo unico que los endpoints de datos usan de `request` es el env."""

    def __init__(self, entorno):
        self.env = entorno


print("=" * 74)
print("CAMBIAR UNA ORDEN Y CREAR UN CLIENTE")
print("=" * 74)

victor = env['res.users'].search([('login', '=', 'victor@agrogood.cl')], limit=1)
entorno = env(user=victor)
linea = env.ref('agrogood_base.business_line_horeca')
alm = env['stock.warehouse'].search([], limit=1)

ventas = AgrogoodVentas()
# Se sustituye el nombre `request` DENTRO del modulo del controlador. No sirve
# tocar odoo.http.request: el controlador hizo `from odoo.http import request`
# y lo que resuelve en cada llamada es su propia variable de modulo.
controlador.request = PeticionFalsa(entorno)

cliente = entorno['res.partner'].create({
    'name': 'CLIENTE PRUEBA EDITAR', 'is_company': True, 'customer_rank': 1,
    'agrogood_business_line_id': linea.id,
    'property_product_pricelist': linea.pricelist_id.id,
})
tomate, acelga, sinprecio = entorno['product.template'].create([
    {'name': 'TOMATE PRUEBA EDITAR', 'is_storable': True, 'list_price': 1000.0},
    {'name': 'ACELGA PRUEBA EDITAR', 'is_storable': True, 'list_price': 800.0},
    {'name': 'SIN PRECIO PRUEBA EDITAR', 'is_storable': True, 'list_price': 0.0},
]).mapped('product_variant_id')
env['stock.quant'].with_context(inventory_mode=True).create([
    {'product_id': p.id, 'location_id': alm.lot_stock_id.id,
     'inventory_quantity': 200} for p in (tomate, acelga, sinprecio)
])._apply_inventory()

# La tarifa de la linea comercial tiene que dar precio a los dos primeros.
for p, precio in ((tomate, 1000.0), (acelga, 800.0)):
    entorno['product.pricelist.item'].create({
        'pricelist_id': linea.pricelist_id.id,
        'applied_on': '0_product_variant', 'product_id': p.id,
        'compute_price': 'fixed', 'fixed_price': precio,
    })

# ------------------------------------------------------------ 1. cambiar
print()
print("CAMBIAR LA ORDEN")

creado = ventas.api_crear(cliente.id, [{'id': tomate.id, 'qty': 10}])
pedido = entorno['sale.order'].browse(creado['id'])
paso("Se toma la orden", creado.get('ok') and pedido.agrogood_editable,
     "%s, %s" % (pedido.name, pedido.agrogood_state))

r = ventas.api_modificar(pedido.id, [{'id': tomate.id, 'qty': 14},
                                     {'id': acelga.id, 'qty': 5}])
pedido.invalidate_recordset()
productos = {l.product_id.id: l.product_uom_qty for l in pedido.order_line}
paso("Se cambia la cantidad y se agrega un producto",
     r.get('ok') and productos.get(tomate.id) == 14
     and productos.get(acelga.id) == 5,
     "tomate %s, acelga %s" % (productos.get(tomate.id),
                               productos.get(acelga.id)))

r = ventas.api_modificar(pedido.id, [{'id': tomate.id, 'qty': 14},
                                     {'id': acelga.id, 'qty': 0}])
pedido.invalidate_recordset()
# Odoo no deja BORRAR una linea de un pedido confirmado -puede tener
# movimientos de stock detras-, asi que quitarla es dejarla en cero. La
# pantalla no pinta las lineas en cero, de modo que para Ventas desaparece; el
# registro conserva que estuvo, que es lo que hace falta si despues alguien
# pregunta por que se preparo distinto de lo que se pidio.
quitada = pedido.order_line.filtered(lambda l: l.product_id == acelga)
paso("Cantidad cero quita la linea del pedido",
     r.get('ok') and quitada.product_uom_qty == 0,
     "la linea queda en cero y no se pinta, en vez de borrarse")

r = ventas.api_modificar(pedido.id, [])
paso("Una orden no puede quedarse sin ninguna linea",
     not r.get('ok') and 'Anular' in r.get('mensaje', ''),
     "manda a Anular, que deja constancia")

r = ventas.api_modificar(pedido.id, [{'id': tomate.id, 'qty': 5},
                                     {'id': sinprecio.id, 'qty': 2}])
pedido.invalidate_recordset()
paso("No se cuela un producto sin precio en la tarifa",
     not r.get('ok') and 'SIN PRECIO' in r.get('mensaje', ''))
paso("Y la orden no queda a medias por el intento",
     pedido.order_line.mapped('product_uom_qty') == [14.0, 0.0],
     "sigue con lo que tenia: %s"
     % pedido.order_line.mapped('product_uom_qty'))

# ------------------------------------------- 2. cuando ya es tarde
print()
print("CUANDO YA ES TARDE")

salida = pedido.picking_ids.filtered(
    lambda p: p.picking_type_id.code == 'outgoing' and p.state != 'cancel')
sesion = entorno['agrogood.picking.session'].create({
    'picking_id': salida.id, 'picker_id': victor.id})
sesion.action_start()
pedido.invalidate_recordset()
paso("Con un Picker preparando, la orden ya no es editable",
     not pedido.agrogood_editable, pedido.agrogood_state)

r = ventas.api_modificar(pedido.id, [{'id': tomate.id, 'qty': 30}])
pedido.invalidate_recordset()
paso("Y el servidor lo impide, no solo la pantalla",
     not r.get('ok') and 'Logistica' in r.get('mensaje', ''),
     "dice a quien hablarle en vez de solo negarse")
paso("La cantidad no se toco",
     pedido.order_line[0].product_uom_qty == 14.0)

r = ventas.api_anular(pedido.id, motivo="prueba")
paso("Tampoco se puede anular a esas alturas", not r.get('ok'))

# --------------------------------------------------------- 3. anular
print()
print("ANULAR")

otro = ventas.api_crear(cliente.id, [{'id': tomate.id, 'qty': 3}])
pedido2 = entorno['sale.order'].browse(otro['id'])

r = ventas.api_anular(pedido2.id, motivo="   ")
paso("Anular sin motivo no se acepta", not r.get('ok'))

antes = len(pedido2.message_ids)
r = ventas.api_anular(pedido2.id, motivo="El cliente cancelo la reserva")
pedido2.invalidate_recordset()
paso("Con motivo, se anula", r.get('ok') and pedido2.state == 'cancel',
     pedido2.state)
paso("Y el motivo queda en la conversacion de la orden",
     len(pedido2.message_ids) > antes
     and 'cancelo la reserva' in (pedido2.message_ids[0].body or ''),
     "sin motivo, el CRM lo lee como un cliente que dejo de comprar")

# -------------------------------------------------- 4. cliente nuevo
print()
print("CLIENTE NUEVO")

r = ventas.api_cliente_nuevo("EL", linea.id)
paso("Un nombre de dos letras no pasa", not r.get('ok'))

r = ventas.api_cliente_nuevo("RESTORAN PRUEBA ALTA", None)
paso("Sin linea comercial no pasa, porque no tendria precios",
     not r.get('ok') and 'precio' in r.get('mensaje', '').lower())

r = ventas.api_cliente_nuevo("RESTORAN PRUEBA ALTA", linea.id,
                             vat="76593894-9")
paso("Un RUT con el digito cambiado se rechaza",
     not r.get('ok') and 'verificador' in r.get('mensaje', ''),
     "76593894-9 no es valido; el digito correcto es 5")

r = ventas.api_cliente_nuevo("RESTORAN PRUEBA ALTA", linea.id,
                             vat="76.593.894-5", mobile="912345678",
                             city="CONCEPCION")
nuevo = entorno['res.partner'].browse(r.get('id')) if r.get('ok') else None
paso("Con el RUT bien, se crea",
     r.get('ok') and nuevo.vat == '76593894-5' and not r.get('sin_rut'),
     "%s, RUT %s" % (nuevo.display_name if nuevo else '-',
                     nuevo.vat if nuevo else '-'))
paso("Queda listo para venderle: con linea comercial y tarifa",
     bool(nuevo and nuevo.agrogood_business_line_id
          and nuevo.property_product_pricelist))

r = ventas.api_cliente_nuevo("restoran prueba alta", linea.id)
paso("No se crea dos veces el mismo cliente",
     not r.get('ok') and 'Ya existe' in r.get('mensaje', ''),
     "aunque se escriba en minusculas")

r = ventas.api_cliente_nuevo("OTRO PRUEBA ALTA", linea.id, vat="76593894-5")
paso("Ese RUT ya es de otro cliente y se dice de quien",
     not r.get('ok') and 'RESTORAN PRUEBA ALTA' in r.get('mensaje', ''))

r = ventas.api_cliente_nuevo("SIN RUT PRUEBA ALTA", linea.id)
paso("Sin RUT se crea igual, y se avisa de que no se le podra facturar",
     r.get('ok') and r.get('sin_rut'),
     "se le puede vender y repartir, no facturar")

print()
print("=" * 74)
print("%d de %d comprobaciones" % (sum(1 for x in R if x), len(R)))
print("=" * 74)
print("Ventas ya no necesita el escritorio." if all(R)
      else "HAY FALLOS. Revisar arriba.")

env.cr.rollback()
