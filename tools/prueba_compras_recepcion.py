"""Prueba del cruce Compras <-> Bodega.

    odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/prueba_compras_recepcion.py

Termina con rollback: no deja nada.

Lo que se comprueba es el lazo que faltaba: cuando Bodega valida la recepcion
de una orden de compra, la solicitud que la origino se cierra sola. Antes se
quedaba en 'Comprado' aunque la mercaderia ya estuviera en la bodega, y alguien
tenia que acordarse de marcarla a mano.

Tres casos, que son los que pasan de verdad:

 1. Llega todo -> la solicitud queda 'Recibido'.
 2. Llega la mitad -> sigue 'Comprado', pero con una nota de cuanto llego.
 3. Llega el resto -> recien ahi queda 'Recibido'.
"""

from odoo import fields
from odoo.tools import float_compare

R = []


def paso(t, ok, det=""):
    R.append(ok)
    print("  [%s] %s" % ("OK " if ok else "FALLA", t))
    if det:
        print("        %s" % det)


def recibir(picking, cantidades):
    """Recibe un picking poniendo esas cantidades y lo valida.

    `cantidades` es {product_id: cantidad}. Se escribe en la linea y se valida
    como lo hace Bodega; si queda algo sin recibir, Odoo ofrece un backorder,
    que se crea -es justo el caso 'llego la mitad'-.
    """
    for mov in picking.move_ids:
        mov.quantity = cantidades.get(mov.product_id.id, 0.0)
        mov.picked = True
    res = picking.button_validate()
    if isinstance(res, dict) and res.get('res_model') == 'stock.backorder.confirmation':
        wiz = env[res['res_model']].with_context(res.get('context', {})).create({})
        # El asistente trae las lineas de backorder en su contexto.
        wiz.with_context(res.get('context', {})).process()
    return res


print("=" * 74)
print("CRUCE COMPRAS <-> BODEGA")
print("=" * 74)

prov = env['res.partner'].search([('supplier_rank', '>', 0)], limit=1) \
    or env['res.partner'].create({'name': 'FERIA PRUEBA', 'supplier_rank': 1})

# Un producto almacenable de verdad: uno solo servicio no genera recepcion.
prod = env['product.product'].search(
    [('purchase_ok', '=', True), ('is_storable', '=', True)], limit=1)
if not prod:
    prod = env['product.product'].create({
        'name': 'TOMATE PRUEBA', 'type': 'consu', 'is_storable': True,
        'purchase_ok': True})
paso("Hay un producto almacenable para probar", bool(prod), prod.name)

Req = env['agrogood.purchase.request']

# ---------------------------------------------------- 1. llega todo
print()
print("LLEGA TODO")
sol = Req.create({
    'product_id': prod.id, 'product_uom_id': prod.uom_id.id,
    'qty_requested': 20.0, 'date_needed': fields.Date.context_today(env.user),
    'supplier_id': prov.id, 'expected_price': 500.0,
})
sol.action_create_purchase_order()
po = sol.purchase_order_id
paso("La solicitud queda 'Comprado' al generar la orden",
     sol.state == 'purchased', po.name)
po.button_confirm()
picking = po.picking_ids[:1]
paso("La orden crea una recepcion en bodega", bool(picking),
     picking.name if picking else "no hay picking")

recibir(picking, {prod.id: 20.0})
sol.invalidate_recordset()
paso("Al recibir todo, la solicitud se cierra sola",
     sol.state == 'received',
     "estado: %s" % dict(sol._fields['state'].selection).get(sol.state))
nota = sol.message_ids.filtered(lambda m: 'Recibido en bodega' in (m.body or ''))
paso("Y queda dicho en su historial que se recibio", bool(nota),
     "para poder reconstruir por que se cerro")

# ---------------------------------------------- 2 y 3. llega en dos viajes
print()
print("LLEGA EN DOS VIAJES")
sol2 = Req.create({
    'product_id': prod.id, 'product_uom_id': prod.uom_id.id,
    'qty_requested': 30.0, 'date_needed': fields.Date.context_today(env.user),
    'supplier_id': prov.id, 'expected_price': 500.0,
})
sol2.action_create_purchase_order()
po2 = sol2.purchase_order_id
po2.button_confirm()
picking2 = po2.picking_ids[:1]

recibir(picking2, {prod.id: 10.0})
sol2.invalidate_recordset()
paso("Con solo una parte, la solicitud sigue abierta",
     sol2.state == 'purchased',
     "no se da por recibido lo que todavia no llego")
parcial = sol2.message_ids.filtered(
    lambda m: 'parcial' in (m.body or '').lower())
paso("Pero se anota cuanto llego", bool(parcial),
     "10 de 30, para que se vea lo que falta")

# El resto llega en el backorder.
resto = po2.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel'))
paso("Bodega tiene un segundo picking por el resto", bool(resto),
     resto[:1].name if resto else "no se creo backorder")
if resto:
    recibir(resto[:1], {prod.id: 20.0})
    sol2.invalidate_recordset()
paso("Cuando llega el resto, recien ahi se cierra",
     sol2.state == 'received',
     "estado: %s" % dict(sol2._fields['state'].selection).get(sol2.state))

# ---------------------------------------------- 4. no toca lo ajeno
print()
print("NO TOCA LO QUE NO ES SUYO")
sol3 = Req.create({
    'product_id': prod.id, 'product_uom_id': prod.uom_id.id,
    'qty_requested': 5.0, 'date_needed': fields.Date.context_today(env.user),
})
# Sin orden de compra, una recepcion cualquiera no debe cerrarla.
sol3._cerrar_por_recepcion()
paso("Una solicitud sin orden no se cierra por una recepcion ajena",
     sol3.state == 'pending')

print()
print("=" * 74)
print("%d de %d comprobaciones" % (sum(1 for x in R if x), len(R)))
print("=" * 74)
print("El cruce Compras-Bodega cierra el lazo." if all(R)
      else "HAY FALLOS. Revisar arriba.")

env.cr.rollback()
print("Revertido.")
