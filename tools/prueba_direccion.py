"""Prueba de la pantalla de Direccion.

    odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/prueba_direccion.py

Termina con rollback: no deja nada.

Lo que se comprueba no es que los numeros se pinten, sino que SIGNIFIQUEN lo
que dicen. Un tablero con una cifra mal calculada es peor que no tenerlo: se
toman decisiones con el.

En particular:
* Lo por cobrar sale de las ORDENES DE COMPRA y no de facturas. La factura se
  emite en el portal del SII y en Odoo no existe: mientras esta cifra miraba
  `account.move`, el panel enseno un cero constante. Ver ADR-006.
* Cuenta el saldo pendiente, no el total: una orden pagada a medias cuenta por
  su mitad.
* Vencido es lo que paso su fecha, no todo lo impagado.
* Direccion NO puede operar: la pantalla no tiene acciones y la matriz de
  permisos ya se lo impide.
"""

from datetime import timedelta
from odoo import fields

R = []
def paso(t, ok, det=""):
    R.append(ok); print("  [%s] %s" % ("OK " if ok else "FALLA", t))
    if det: print("        %s" % det)

print("=" * 74)
print("PANTALLA DE DIRECCION")
print("=" * 74)

victor = env['res.users'].search([('login','=','victor@agrogood.cl')], limit=1)
paso("Victor tiene el rol de Direccion",
     victor.has_group('agrogood_base.group_agrogood_general_admin'))

# Nadie mas debe entrar
for login in ('sebastian.ventas@agrogood.cl', 'matias@agrogood.cl',
              'felipe@agrogood.cl', 'johan@agrogood.cl'):
    u = env['res.users'].search([('login','=',login)], limit=1)
    if u.has_group('agrogood_base.group_agrogood_general_admin'):
        paso("Solo Direccion entra", False, "%s tambien entra" % login)
        break
else:
    paso("Solo Direccion entra a esta pantalla", True,
         "Ventas, Bodega, Logistica y Compras quedan fuera")

hoy = fields.Date.context_today(env.user)


def entregar(pedido):
    """Valida la salida del pedido entera."""
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


linea = env.ref('agrogood_base.business_line_horeca')
cli = env['res.partner'].create({
    'name': 'CLIENTE PRUEBA DIRECCION', 'is_company': True,
    'agrogood_business_line_id': linea.id, 'customer_rank': 1,
    'country_id': env.ref('base.cl').id,
    'street': 'Barros Arana 100', 'city': 'CONCEPCION',
    'vat': '76593894-5',
    'property_product_pricelist': linea.pricelist_id.id,
    'agrogood_credit_days': 0,
})
prod = env['product.product'].create({
    'name': 'PRODUCTO PRUEBA DIRECCION', 'is_storable': True,
    'list_price': 10000.0,
})
alm = env['stock.warehouse'].search([], limit=1)
env['stock.quant'].with_context(inventory_mode=True).create({
    'product_id': prod.id, 'location_id': alm.lot_stock_id.id,
    'inventory_quantity': 100,
})._apply_inventory()

# --- una entrega vencida y pagada a medias ---
vencida = env['sale.order'].create({
    'partner_id': cli.id,
    'order_line': [(0, 0, {'product_id': prod.id, 'product_uom_qty': 10})],
})
vencida.action_confirm()
entregar(vencida)
vencida.write({'date_order': fields.Datetime.now() - timedelta(days=5)})
vencida.invalidate_recordset()
total = vencida.agrogood_charge_amount
paso("Hay una entrega hecha y vencida",
     vencida.agrogood_collection_state == 'open' and total > 0,
     "%s por %s, vencia hace 5 dias" % (vencida.name, round(total)))

abono = env['agrogood.bank.movement'].create({
    'bank': 'santander', 'date': hoy, 'amount': round(total / 2, 0),
    'partner_id': cli.id, 'unique_key': 'direccion|mitad',
})
abono.action_imputar()
vencida.invalidate_recordset()
paso("Se paga la mitad", vencida.agrogood_collection_state == 'partial',
     "estado del cobro: %s" % vencida.agrogood_collection_state)

# --- una entrega que aun no vence ---
cli.write({'agrogood_credit_days': 30})
al_dia = env['sale.order'].create({
    'partner_id': cli.id,
    'order_line': [(0, 0, {'product_id': prod.id, 'product_uom_qty': 1})],
})
al_dia.action_confirm()
entregar(al_dia)
al_dia.invalidate_recordset()

# --- las cifras que muestra la pantalla, calculadas como las calcula ---
impagas = env['sale.order'].search([
    ('agrogood_collection_state', 'in', ('open', 'partial'))])
por_cobrar = sum(impagas.mapped('agrogood_due_amount'))
paso("Por cobrar cuenta el SALDO, no el total de la orden",
     abs(por_cobrar - sum(impagas.mapped('agrogood_charge_amount'))) > 1,
     "saldo %s frente a entregado %s"
     % (round(por_cobrar), round(sum(impagas.mapped('agrogood_charge_amount')))))

vencidas = impagas.filtered(
    lambda o: o.agrogood_due_date and o.agrogood_due_date < hoy)
paso("Vencido es lo que paso su fecha, no todo lo impagado",
     vencida in vencidas,
     "%d de %d ordenes estan vencidas" % (len(vencidas), len(impagas)))
paso("Una entrega que aun no vence no cuenta como vencida",
     al_dia in impagas and al_dia not in vencidas,
     "vence el %s" % al_dia.agrogood_due_date)

# --- la pantalla se dibuja ---
html = str(env['ir.qweb']._render('agrogood_pwa.direccion_home', {
    'hoy_n': 0, 'hoy_monto': 0.0, 'mes_monto': 0.0,
    'por_entregar_n': 0, 'por_entregar_monto': 0.0,
    'por_cobrar': por_cobrar, 'por_cobrar_n': len(impagas),
    'vencido': sum(vencidas.mapped('agrogood_due_amount')),
    'vencido_n': len(vencidas),
    'merma_monto': 0.0, 'merma_n': 0,
    'no_facturables': 0, 'cartera_n': 0,
    'rutas': env['agrogood.route'], 'llamar': 0,
    'usuario': victor, 'env': env,
}))
paso("La pantalla se dibuja", len(html) > 800, "%d caracteres" % len(html))
paso("Y no lleva ningun boton de accion",
     'data-action' not in html and '<button' not in html,
     "Direccion mira, no opera")

print()
print("=" * 74)
print("RESULTADO: %d/%d" % (sum(1 for x in R if x), len(R)))
print("=" * 74)
env.cr.rollback()
print("Revertido.")
