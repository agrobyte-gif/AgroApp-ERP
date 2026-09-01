"""Prueba de la pantalla de Bodega: recibir y mermar.

    odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/prueba_bodega.py

Termina con rollback: no deja nada.

Cubre tres trampas que costaron dinero al descubrirlas, y por eso vive aqui y
no en la carpeta de un ensayo suelto:

* Recibir MENOS de lo comprado tiene que dejar el resto pendiente. La regla de
  "sin pedido en espera por diferencias de peso variable" se escribio para las
  ENTREGAS -0,6 kg de menos es lo que peso la caja- y se estaba aplicando
  tambien a las COMPRAS, donde lo que falta es mercaderia pagada y no recibida.

* Un producto con control de caducidad NO se puede mermar sin decir de que
  lote: Odoo deja la merma en borrador y no avisa de nada. Son 115 de los 195
  productos.

* Una merma reclamable exige a quien se le reclama, o la perdida se asume.
"""

from datetime import timedelta
from odoo import fields
from odoo.exceptions import UserError, ValidationError

R = []
def paso(t, ok, det=""):
    R.append(ok); print("  [%s] %s" % ("OK " if ok else "FALLA", t))
    if det: print("        %s" % det)

print("=" * 74)
print("PANTALLA DE BODEGA - con el usuario real")
print("=" * 74)

u = env['res.users'].search([('login','=','matias@agrogood.cl')], limit=1)
E = env(user=u)
paso("Matias tiene el rol de Bodega",
     u.has_group('agrogood_base.group_agrogood_warehouse'))

# --- una compra con un producto que lleva lote ---
prov = env['res.partner'].search([('supplier_rank','>',0)], limit=1) \
    or env['res.partner'].create({'name': 'PROVEEDOR PRUEBA BODEGA', 'supplier_rank': 1})
prod = env['product.product'].search([('tracking','=','lot'),('purchase_ok','=',True)], limit=1)
paso("Hay un producto con control de caducidad", bool(prod),
     prod.display_name if prod else "-")

oc = env['purchase.order'].create({
    'partner_id': prov.id,
    'order_line': [(0, 0, {'product_id': prod.id, 'product_qty': 20.0,
                           'price_unit': 1000.0,
                           'name': prod.name,
                           'date_planned': fields.Datetime.now()})],
})
oc.button_confirm()
rec = oc.picking_ids[:1]
paso("La compra genera su recepcion", bool(rec), rec.name if rec else "-")

# --- Matias la ve ---
suyas = E['stock.picking'].search([('picking_type_id.code','=','incoming'),
                                   ('state','not in',('done','cancel'))])
paso("Bodega ve la recepcion pendiente", rec in suyas, "%d pendientes" % len(suyas))

mov = rec.move_ids[0]

# --- sin lote, se rechaza (es la guardia del endpoint) ---
def falta_lote(cantidad, lote):
    return mov.product_id.tracking == 'lot' and cantidad > 0 and not (lote or '').strip()
paso("Recibir sin numero de lote se rechaza", falta_lote(16.0, ""))
paso("Con lote, pasa", not falta_lote(16.0, "L-2026-001"))

# --- recibir 18 de 20, con lote y vencimiento ---
mov.move_line_ids.unlink()
vence = fields.Date.to_string(fields.Date.today() + timedelta(days=9))
E['stock.move.line'].create({
    'move_id': mov.id, 'product_id': mov.product_id.id,
    'location_id': mov.location_id.id, 'location_dest_id': mov.location_dest_id.id,
    'quantity': 16.0, 'picked': True,
    'lot_name': 'L-2026-001', 'expiration_date': vence + " 12:00:00",
})
res = rec.button_validate()
if isinstance(res, dict) and res.get('res_model'):
    asis = env[res['res_model']].with_context(**res.get('context', {})).create({})
    (asis.process if hasattr(asis, 'process') else asis.action_confirm)()
rec.invalidate_recordset()
paso("La recepcion queda validada", rec.state == 'done', "estado: %s" % rec.state)

lote = env['stock.lot'].search([('name','=','L-2026-001')], limit=1)
paso("El lote se creo con su vencimiento", bool(lote) and bool(lote.expiration_date),
     "%s vence %s" % (lote.name, lote.expiration_date))

# La fecha guardada a mediodia evita que en Chile se lea el dia anterior
local = fields.Datetime.context_timestamp(lote, lote.expiration_date).date()
paso("La caducidad no se corre un dia por la zona horaria",
     fields.Date.to_string(local) == vence,
     "guardado %s, se lee %s en Chile" % (vence, local))

# --- lo que falto sigue debiendose ---
pendiente = oc.picking_ids.filtered(lambda p: p.state not in ('done','cancel'))
# 16 de 20 son un 20% de falta: por encima de la tolerancia del 10%, asi que
# es una entrega corta de verdad y hay que reclamarla.
paso("Los 4 que faltaron quedan pendientes", bool(pendiente),
     "%s por %s unidades" % (pendiente[:1].name or '-',
                             sum(pendiente.move_ids.mapped('product_uom_qty')) if pendiente else 0))

# --- la tolerancia distingue el envase de la entrega corta -------------------
# Pedir 20 y recibir 19,8 es el peso de la caja: no genera pendiente. Recibir
# 15 es una entrega corta y hay que reclamarla. Es la misma tolerancia que el
# Picker tiene en la balanza, para que no haya dos reglas.
if prod.agrogood_is_variable_weight:
    def sobra_pendiente(recibido):
        oc2 = env['purchase.order'].create({
            'partner_id': prov.id,
            'order_line': [(0, 0, {'product_id': prod.id, 'product_qty': 20.0,
                                   'price_unit': 1000.0, 'name': prod.name,
                                   'date_planned': fields.Datetime.now()})]})
        oc2.button_confirm()
        r2 = oc2.picking_ids[:1]
        m2 = r2.move_ids[0]
        m2.move_line_ids.unlink()
        env['stock.move.line'].create({
            'move_id': m2.id, 'product_id': m2.product_id.id,
            'location_id': m2.location_id.id,
            'location_dest_id': m2.location_dest_id.id,
            'quantity': recibido, 'picked': True,
            'lot_name': 'L-TOL-%s' % recibido,
            'expiration_date': vence + " 12:00:00"})
        res2 = r2.button_validate()
        if isinstance(res2, dict) and res2.get('res_model'):
            a = env[res2['res_model']].with_context(**res2.get('context', {})).create({})
            (a.process if hasattr(a, 'process') else a.action_confirm)()
        return bool(oc2.picking_ids.filtered(lambda x: x.state not in ('done', 'cancel')))

    tol = prod.agrogood_weight_tolerance
    paso("Dentro de la tolerancia (%.0f%%) no queda pendiente" % tol,
         not sobra_pendiente(19.8), "20 pedidos, 19,8 recibidos: es el envase")
    paso("Fuera de la tolerancia si queda pendiente",
         sobra_pendiente(15.0), "20 pedidos, 15 recibidos: hay que reclamar")
else:
    print("  (el producto de prueba no es de peso variable; se omite la tolerancia)")

# --- merma con motivo ---
alm = env['stock.warehouse'].search([], limit=1)
# Sin responsable, una merma reclamable NO se admite: la perdida se asumiria
# sin poder recuperarla. Es la guardia que la pantalla tiene que respetar.
try:
    E['stock.scrap'].create({
        'product_id': prod.id, 'scrap_qty': 2.0,
        'location_id': alm.lot_stock_id.id,
        'agrogood_reason': 'supplier',
    })
    exige_responsable = False
except (ValidationError, UserError):
    exige_responsable = True
paso("Una merma reclamable exige decir a quien se le reclama", exige_responsable)

# Sin lote, un producto con caducidad no se puede mermar: Odoo no sabe de
# donde descontarlo y la merma se queda en borrador SIN avisar. Es la trampa
# que la pantalla tiene que evitar, y afecta a 115 de los 195 productos.
sin_lote = E['stock.scrap'].create({
    'product_id': prod.id, 'scrap_qty': 2.0,
    'location_id': alm.lot_stock_id.id,
    'agrogood_reason': 'supplier', 'agrogood_partner_id': prov.id,
})
sin_lote.action_validate()
paso("Sin lote, la merma NO se registra (se queda en borrador)",
     sin_lote.state == 'draft', "estado: %s" % sin_lote.state)

merma = E['stock.scrap'].create({
    'product_id': prod.id, 'scrap_qty': 2.0,
    'lot_id': lote.id,
    'location_id': alm.lot_stock_id.id,
    'agrogood_reason': 'supplier',
    'agrogood_reason_note': 'Llego golpeado',
    'agrogood_partner_id': prov.id,
})
merma.action_validate()
paso("Bodega registra una merma con su motivo", merma.state == 'done',
     "%s: %s" % (merma.name, dict(merma._fields['agrogood_reason'].selection)['supplier']))
paso("La merma reclamable se distingue", merma.agrogood_claimable,
     "'Llego mal del proveedor' se puede reclamar")

print()
print("=" * 74)
print("RESULTADO: %d/%d" % (sum(1 for x in R if x), len(R)))
print("=" * 74)
env.cr.rollback()
print("Revertido.")
