"""Prueba del ajuste de inventario y de reprogramar una entrega.

    odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/prueba_bodega_reparto.py

Termina con rollback: no deja nada.

Son los dos huecos que quedaban fuera de la aplicacion. En orden de lo que
cuesta si falla:

 1. Que una entrega reprogramada VUELVA a la lista de Logistica del dia nuevo.
    Antes reprogramar solo ponia una etiqueta: la entrega desaparecia de la
    ruta de hoy y no aparecia en la de ningun otro dia.
 2. Que un albaran no pueda salir en dos rutas vivas a la vez, que es lo que
    impedia la restriccion que hubo que levantar para lo anterior.
 3. Que un ajuste de inventario no se pueda guardar sin explicacion. Es dinero
    que aparece o desaparece del balance sin que nadie compre ni venda.
"""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.addons.agrogood_pwa.controllers import main as controlador
from odoo.addons.agrogood_pwa.controllers.main import AgrogoodBodega

R = []


def paso(t, ok, det=""):
    R.append(ok)
    print("  [%s] %s" % ("OK " if ok else "FALLA", t))
    if det:
        print("        %s" % det)


class PeticionFalsa(object):
    def __init__(self, entorno):
        self.env = entorno


victor = env['res.users'].search([('login', '=', 'victor@agrogood.cl')], limit=1)
entorno = env(user=victor)
controlador.request = PeticionFalsa(entorno)
bodega = AgrogoodBodega()

linea = env.ref('agrogood_base.business_line_horeca')
alm = env['stock.warehouse'].search([], limit=1)
hoy = fields.Date.context_today(victor)

print("=" * 74)
print("INVENTARIO Y REPROGRAMACION")
print("=" * 74)

# ------------------------------------------------------- 1. inventario
print()
print("AJUSTAR INVENTARIO")

prod = entorno['product.template'].create({
    'name': 'PAPA PRUEBA INVENTARIO', 'is_storable': True,
    'list_price': 900.0,
}).product_variant_id
env['stock.quant'].with_context(inventory_mode=True).create({
    'product_id': prod.id, 'location_id': alm.lot_stock_id.id,
    'inventory_quantity': 100,
})._apply_inventory()

datos = bodega.api_existencias(prod.id)
paso("Se ve lo que dice el sistema antes de contar",
     datos['existencias'] == 100.0 and not datos['por_lote'],
     "%s %s" % (datos['existencias'], datos['uom']))

r = bodega.api_ajustar(prod.id, 88, motivo="  ")
paso("Sin motivo no se ajusta", not r.get('ok'),
     "una diferencia sin explicacion no se puede revisar despues")

r = bodega.api_ajustar(prod.id, -5, motivo="prueba")
paso("No se puede contar en negativo", not r.get('ok'))

antes_msgs = len(prod.product_tmpl_id.message_ids)
r = bodega.api_ajustar(prod.id, 88, motivo="Se paso de maduro un saco")
prod.invalidate_recordset()
paso("Contar menos baja las existencias",
     r.get('ok') and r['diferencia'] == -12.0
     and prod.qty_available == 88.0,
     "de 100 a %g" % prod.qty_available)
paso("Queda anotado en la ficha del producto, con quien y por que",
     len(prod.product_tmpl_id.message_ids) > antes_msgs
     and 'maduro' in (prod.product_tmpl_id.message_ids[0].body or ''),
     "es donde mira quien pregunta por que cuadra mal todos los meses")

r = bodega.api_ajustar(prod.id, 95, motivo="Aparecio una caja detras")
prod.invalidate_recordset()
paso("Contar mas tambien sube", r.get('ok') and prod.qty_available == 95.0,
     "de 88 a %g" % prod.qty_available)

# Un producto con lotes no se puede ajustar sin decir de cual.
con_lote = entorno['product.template'].create({
    'name': 'QUESO PRUEBA INVENTARIO', 'is_storable': True,
    'tracking': 'lot', 'list_price': 5000.0,
}).product_variant_id
r = bodega.api_ajustar(con_lote.id, 10, motivo="conteo")
paso("Un producto con lotes exige decir de que lote",
     not r.get('ok') and 'lote' in r.get('mensaje', '').lower(),
     "40 kg pueden ser de tres lotes con tres vencimientos")

# --------------------------------------------------- 2. reprogramacion
print()
print("REPROGRAMAR UNA ENTREGA")

cliente = entorno['res.partner'].create({
    'name': 'CLIENTE PRUEBA REPROGRAMAR', 'is_company': True,
    'customer_rank': 1, 'agrogood_business_line_id': linea.id,
    'property_product_pricelist': linea.pricelist_id.id,
    'street': 'Colo Colo 486', 'city': 'CONCEPCION',
})
pedido = entorno['sale.order'].create({
    'partner_id': cliente.id,
    'order_line': [(0, 0, {'product_id': prod.id, 'product_uom_qty': 5})],
})
pedido.action_confirm()
salida = pedido.picking_ids.filtered(
    lambda p: p.picking_type_id.code == 'outgoing' and p.state != 'cancel')

conductor = env['res.users'].search(
    [('login', 'like', 'chofer')], limit=1) or victor
modelo = env['fleet.vehicle.model'].search([], limit=1)
vehiculo = env['fleet.vehicle'].create({
    'model_id': modelo.id, 'license_plate': 'REP-01',
    'agrogood_capacity_kg': 600.0})
ruta = entorno['agrogood.route'].create({
    'driver_id': conductor.id, 'vehicle_id': vehiculo.id, 'date': hoy})
parada = entorno['agrogood.route.stop'].create({
    'route_id': ruta.id, 'picking_id': salida.id})
salida.invalidate_recordset()
paso("La entrega queda asignada a la ruta de hoy",
     salida.agrogood_route_id == ruta, ruta.name)

parada.failure_reason = 'customer_absent'
try:
    parada.action_rescheduled()
    paso("Reprogramar sin fecha no se acepta", False, "se acepto")
except UserError as e:
    paso("Reprogramar sin fecha no se acepta", True,
         "sin fecha se quedaria sin ruta y sin nadie esperandola")

parada.reschedule_date = hoy - timedelta(days=1)
try:
    parada.action_rescheduled()
    paso("Una fecha que ya paso no se acepta", False, "se acepto")
except UserError:
    paso("Una fecha que ya paso no se acepta", True)

nueva = hoy + timedelta(days=2)
parada.reschedule_date = nueva
antes_pedido = len(pedido.message_ids)
parada.action_rescheduled()
salida.invalidate_recordset()
pedido.invalidate_recordset()
paso("Con fecha, la parada queda reprogramada",
     parada.state == 'rescheduled', "para el %s" % nueva)
paso("El albaran se mueve al dia nuevo",
     salida.scheduled_date.date() == nueva,
     "asi deja de salir como atrasado todos los dias")
paso("Y VUELVE a la lista de Logistica: ya no tiene ruta viva",
     not salida.agrogood_route_id,
     "es lo que antes no pasaba, y por eso quedaba colgada")
paso("El pedido cuenta que se reprogramo y para cuando",
     pedido.agrogood_exception == 'rescheduled'
     and str(nueva) in (pedido.agrogood_exception_note or ''),
     pedido.agrogood_exception_note)
paso("Y queda en la conversacion del pedido",
     len(pedido.message_ids) > antes_pedido)

# La parada vieja sigue siendo historia, pero ya no retiene el albaran.
ruta2 = entorno['agrogood.route'].create({
    'driver_id': conductor.id, 'vehicle_id': vehiculo.id, 'date': nueva})
parada2 = entorno['agrogood.route.stop'].create({
    'route_id': ruta2.id, 'picking_id': salida.id})
salida.invalidate_recordset()
paso("Se puede armar una ruta nueva con esa misma entrega",
     salida.agrogood_route_id == ruta2,
     "antes lo impedia una restriccion de un albaran por parada")
paso("Y la parada de ayer sigue ahi como historia",
     parada.exists() and parada.state == 'rescheduled',
     "se intento ese dia y no se pudo; eso no se borra")

# Lo que sigue estando prohibido.
ruta3 = entorno['agrogood.route'].create({
    'driver_id': conductor.id, 'vehicle_id': vehiculo.id, 'date': nueva})
try:
    entorno['agrogood.route.stop'].create({
        'route_id': ruta3.id, 'picking_id': salida.id})
    env.cr.flush()
    paso("Una entrega no puede salir en dos rutas vivas a la vez", False,
         "se acepto")
except ValidationError:
    paso("Una entrega no puede salir en dos rutas vivas a la vez", True,
         "seria una entrega que sale dos veces")

print()
print("=" * 74)
print("%d de %d comprobaciones" % (sum(1 for x in R if x), len(R)))
print("=" * 74)
print("Bodega y Reparto ya no necesitan el escritorio." if all(R)
      else "HAY FALLOS. Revisar arriba.")

env.cr.rollback()
