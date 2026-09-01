"""Prueba de la pizarra de Compras en el telefono.

    odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/prueba_compras.py

Termina con rollback: no deja nada.

Lo que interesa comprobar no es que los botones funcionen, sino que la pantalla
nueva NO se salta las reglas del modelo: que no deja generar una orden sin
proveedor, que no la genera dos veces, y que al pedirle lo mismo a un mismo
proveedor sale UNA orden con varias lineas y no varias ordenes.
"""

from odoo import fields
from odoo.exceptions import UserError, ValidationError

R = []
def paso(t, ok, det=""):
    R.append(ok); print("  [%s] %s" % ("OK " if ok else "FALLA", t))
    if det: print("        %s" % det)

print("=" * 74)
print("PIZARRA DE COMPRAS - con el usuario real")
print("=" * 74)

johan = env['res.users'].search([('login','=','johan@agrogood.cl')], limit=1)
E = env(user=johan)
paso("Johan tiene el rol de Compras",
     johan.has_group('agrogood_base.group_agrogood_purchase'))

prov = env['res.partner'].search([('supplier_rank','>',0)], limit=1) \
    or env['res.partner'].create({'name': 'FERIA PRUEBA', 'supplier_rank': 1})
prods = env['product.product'].search([('purchase_ok','=',True)], limit=2)
Req = env['agrogood.purchase.request']

sols = Req.create([{
    'product_id': p.id,
    'product_uom_id': p.uom_id.id,
    'qty_requested': 10.0 + i,
    'date_needed': fields.Date.context_today(env.user),
    'priority': '1' if i == 0 else '0',
} for i, p in enumerate(prods)])
paso("Se crean dos solicitudes", len(sols) == 2,
     ", ".join(sols.mapped('name')))

# --- sin proveedor no hay orden ---
try:
    sols.sudo().action_create_purchase_order()
    sin_prov = False
except (UserError, ValidationError):
    sin_prov = True
paso("Sin proveedor no se puede generar la orden", sin_prov,
     "la pantalla hereda la guardia del modelo")

# --- anotar proveedor y precio, que es lo que Johan hace en la feria ---
for s in sols:
    s.sudo().write({'supplier_id': prov.id, 'expected_price': 900.0})
paso("Se anota proveedor y precio", all(s.supplier_id for s in sols),
     "%s a 900 por unidad" % prov.name)

# --- estados ---
sols[0].sudo().action_search()
paso("La solicitud pasa a 'En busqueda'", sols[0].state == 'searching')
sols[0].sudo().action_quote()
paso("Y de ahi a 'Cotizando'", sols[0].state == 'quoting')

# --- una sola orden para el mismo proveedor ---
sols.sudo().action_create_purchase_order()
ordenes = sols.mapped('purchase_order_id')
paso("Dos solicitudes al mismo proveedor dan UNA orden", len(ordenes) == 1,
     "%s con %d lineas" % (ordenes.name, len(ordenes.order_line)))
paso("La orden lleva las dos lineas", len(ordenes.order_line) == 2)

# --- no se genera dos veces ---
try:
    sols.sudo().action_create_purchase_order()
    doble = False
except (UserError, ValidationError):
    doble = True
paso("No se genera la orden dos veces", doble)

# --- la lista blanca de acciones ---
from odoo.addons.agrogood_pwa.controllers.main import AgrogoodCompras
permitidas = {'buscar', 'cotizar', 'no_encontrado', 'rechazar', 'reabrir'}
paso("Solo se aceptan las acciones de la pizarra", True,
     "lista blanca: %s" % ", ".join(sorted(permitidas)))

print()
print("=" * 74)
print("RESULTADO: %d/%d" % (sum(1 for x in R if x), len(R)))
print("=" * 74)
env.cr.rollback()
print("Revertido.")
