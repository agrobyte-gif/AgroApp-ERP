"""Prueba de la pantalla de Cobranza en el telefono.

    odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/prueba_pwa_cobranza.py

Termina con rollback: no deja nada.

Cobrar es una conversacion. Lo que se comprueba es que la pantalla diga lo que
hace falta decir por telefono -cuanto debe, desde cuando, que ordenes son- y
que lo unico que se anota al colgar quede guardado en los dos sitios donde se
va a buscar: el campo, para saber cuando dijo que pagaba, y la conversacion del
cliente, para saber cuantas veces lo ha dicho ya.
"""

from datetime import timedelta

from odoo import fields
from odoo.addons.agrogood_pwa.controllers.main import AgrogoodCobranza

R = []


def paso(t, ok, det=""):
    R.append(ok)
    print("  [%s] %s" % ("OK " if ok else "FALLA", t))
    if det:
        print("        %s" % det)


print("=" * 74)
print("COBRANZA EN EL TELEFONO")
print("=" * 74)

pantalla = AgrogoodCobranza()

# ------------------------------------------------------------ el telefono
print()
print("EL NUMERO PARA WHATSAPP")

Socio = env['res.partner']
linea = env.ref('agrogood_base.business_line_horeca')


def con_numero(movil):
    return Socio.new({'name': 'X', 'mobile': movil})


casos = [
    ("912345678", "56912345678", "un movil chileno sin prefijo"),
    ("+56 9 1234 5678", "56912345678", "el mismo escrito como se escribe"),
    ("0912345678", "56912345678", "con el cero de marcar"),
    ("", "", "sin telefono no se pinta el boton"),
    ("2431", "", "un numero que no es un movil tampoco"),
]
for entrada, esperado, comentario in casos:
    obtenido = pantalla._telefono_internacional(con_numero(entrada))
    paso(comentario, obtenido == esperado,
         "%r -> %r" % (entrada, obtenido))

# ------------------------------------------------------------ un deudor
print()
print("LA PANTALLA")

cliente = Socio.create({
    'name': 'CLIENTE PRUEBA PWA COBRANZA', 'is_company': True,
    'customer_rank': 1, 'agrogood_business_line_id': linea.id,
    'mobile': '912345678', 'agrogood_credit_days': 0,
})
producto = env['product.template'].create({
    'name': 'PRODUCTO PRUEBA PWA COBRANZA', 'is_storable': True,
    'list_price': 8000.0,
}).product_variant_id
alm = env['stock.warehouse'].search([], limit=1)
env['stock.quant'].with_context(inventory_mode=True).create({
    'product_id': producto.id, 'location_id': alm.lot_stock_id.id,
    'inventory_quantity': 100,
})._apply_inventory()

pedido = env['sale.order'].create({
    'partner_id': cliente.id,
    'order_line': [(0, 0, {'product_id': producto.id, 'product_uom_qty': 5})],
})
pedido.action_confirm()
salida = pedido.picking_ids.filtered(
    lambda p: p.picking_type_id.code == 'outgoing' and p.state != 'cancel')
salida.action_assign()
for mov in salida.move_ids:
    mov.quantity = mov.product_uom_qty
    mov.picked = True
resultado = salida.button_validate()
if isinstance(resultado, dict) and resultado.get('res_model'):
    asistente = env[resultado['res_model']].browse(resultado.get('res_id'))
    if hasattr(asistente, 'process'):
        asistente.process()
pedido.write({'date_order': fields.Datetime.now() - timedelta(days=7)})
pedido.invalidate_recordset()
cliente.invalidate_recordset()

paso("El cliente aparece debiendo y vencido",
     cliente.agrogood_balance > 0 and cliente.agrogood_overdue_balance > 0,
     "debe %s, vencido hace %d dias"
     % ("{:,.0f}".format(cliente.agrogood_balance).replace(",", "."),
        cliente.agrogood_oldest_due_days))

hoy = fields.Date.context_today(env.user)
victor = env['res.users'].search([('login', '=', 'victor@agrogood.cl')], limit=1)

html = str(env['ir.qweb']._render('agrogood_pwa.cobranza_home', {
    'prometieron': Socio.browse(),
    'vencidos': cliente,
    'al_dia': Socio.browse(),
    'total': cliente.agrogood_balance,
    'total_vencido': cliente.agrogood_overdue_balance,
    'usuario': victor, 'env': env,
}))
paso("La lista se dibuja y lleva al cliente", len(html) > 800
     and cliente.display_name in html and '/agrogood/cobranza/%s' % cliente.id in html,
     "%d caracteres" % len(html))

detalle = str(env['ir.qweb']._render('agrogood_pwa.cobranza_cliente', {
    'socio': cliente,
    'ordenes': pedido,
    'abonos': env['agrogood.bank.movement'].browse(),
    'hoy': hoy,
    'telefono': pantalla._telefono_internacional(cliente),
    'usuario': victor, 'env': env,
}))
paso("La ficha de la llamada se dibuja", len(detalle) > 800,
     "%d caracteres" % len(detalle))
paso("Con el boton de llamar y el de WhatsApp",
     'tel:912345678' in detalle and 'wa.me/56912345678' in detalle)
paso("Y muestra que orden se debe y desde cuando",
     pedido.name in detalle and 'dias de atraso' in detalle)

# ----------------------------------------------------------- la promesa
print()
print("LO QUE SE ANOTA AL COLGAR")

antes = len(cliente.message_ids)
cliente.agrogood_registrar_promesa(fecha=hoy + timedelta(days=3),
                                   nota="Deposita el viernes")
cliente.invalidate_recordset()
paso("La promesa queda en el campo",
     cliente.agrogood_payment_promise_date == hoy + timedelta(days=3)
     and cliente.agrogood_payment_promise_note == "Deposita el viernes",
     "dijo el %s" % cliente.agrogood_payment_promise_date)
paso("Y tambien en la conversacion del cliente",
     len(cliente.message_ids) > antes,
     "para poder ver cuantas veces lo ha prometido ya")
cuerpo = cliente.message_ids[0].body or ""
paso("Con lo que debia en ese momento",
     "Debia" in cuerpo and "Deposita el viernes" in cuerpo,
     "el mensaje recoge el saldo y lo que dijo, no solo la fecha")

cliente.agrogood_registrar_promesa(fecha=hoy + timedelta(days=10),
                                   nota="Vuelve a pedir plazo")
cliente.invalidate_recordset()
paso("Una promesa nueva pisa la fecha pero no borra la anterior del historial",
     cliente.agrogood_payment_promise_date == hoy + timedelta(days=10)
     and len(cliente.message_ids) > antes + 1,
     "%d mensajes de cobranza en su ficha" % (len(cliente.message_ids) - antes))

# ------------------------------------------------------------- el acceso
print()
print("QUIEN ENTRA")

grupos_de_cobranza = ('agrogood_base.group_agrogood_sales',
                      'agrogood_base.group_agrogood_general_admin')
paso("Victor llega a Cobranza",
     any(victor.has_group(g) for g in grupos_de_cobranza))
picker = env['res.users'].search([('login', 'like', 'picker')], limit=1)
if picker:
    paso("Un Picker no",
         not any(picker.has_group(g) for g in grupos_de_cobranza),
         picker.login)

print()
print("=" * 74)
print("%d de %d comprobaciones" % (sum(1 for x in R if x), len(R)))
print("=" * 74)
print("La pantalla de cobranza sirve." if all(R) else "HAY FALLOS. Revisar arriba.")

env.cr.rollback()
