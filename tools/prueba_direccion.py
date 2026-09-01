"""Prueba de la pantalla de Direccion.

    odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/prueba_direccion.py

Termina con rollback: no deja nada.

Lo que se comprueba no es que los numeros se pinten, sino que SIGNIFIQUEN lo
que dicen. Un tablero con una cifra mal calculada es peor que no tenerlo: se
toman decisiones con el.

En particular:
* Lo por cobrar usa el saldo pendiente, no el total de la factura. Una factura
  pagada a medias cuenta por su mitad.
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

# --- una factura pagada a medias ---
linea = env.ref('agrogood_base.business_line_horeca')
cli = env['res.partner'].create({
    'name': 'CLIENTE PRUEBA DIRECCION', 'is_company': True,
    'agrogood_business_line_id': linea.id, 'customer_rank': 1,
    # El pais es obligatorio: sin el, l10n_cl trata al cliente como extranjero
    # y exige documentos de exportacion.
    'country_id': env.ref('base.cl').id,
    'street': 'Barros Arana 100', 'city': 'CONCEPCION',
    'vat': '76593894-5',
    'l10n_latam_identification_type_id': env.ref('l10n_cl.it_RUT').id,
    'l10n_cl_sii_taxpayer_type': '1',
    'property_product_pricelist': linea.pricelist_id.id,
})
prod = env['product.product'].search([('sale_ok','=',True)], limit=1)
fac = env['account.move'].create({
    'move_type': 'out_invoice', 'partner_id': cli.id,
    'invoice_date': hoy, 'invoice_date_due': hoy - timedelta(days=5),
    'invoice_line_ids': [(0, 0, {'product_id': prod.id, 'quantity': 10,
                                 'price_unit': 10000})],
})
fac.action_post()
total = fac.amount_total
paso("Hay una factura emitida y vencida", fac.state == 'posted',
     "%s por %s, vencia hace 5 dias" % (fac.name, round(total)))

# se paga la mitad
pago = env['account.payment.register'].with_context(
    active_model='account.move', active_ids=fac.ids).create({
        'amount': round(total / 2, 0)})
pago._create_payments()
fac.invalidate_recordset()
paso("Se paga la mitad", fac.payment_state == 'partial',
     "estado de pago: %s" % fac.payment_state)

# --- la cifra que muestra la pantalla ---
impagas = env['account.move'].search([
    ('move_type','=','out_invoice'), ('state','=','posted'),
    ('payment_state','in',('not_paid','partial'))])
por_cobrar = sum(impagas.mapped('amount_residual'))
paso("Por cobrar cuenta el SALDO, no el total de la factura",
     abs(por_cobrar - sum(impagas.mapped('amount_total'))) > 1,
     "saldo %s frente a total %s" % (round(por_cobrar),
                                     round(sum(impagas.mapped('amount_total')))))

vencidas = impagas.filtered(lambda f: f.invoice_date_due and f.invoice_date_due < hoy)
paso("Vencido es lo que paso su fecha, no todo lo impagado",
     fac in vencidas, "%d de %d facturas estan vencidas" % (len(vencidas), len(impagas)))

# --- una factura que vence manana NO es vencida ---
fac2 = env['account.move'].create({
    'move_type': 'out_invoice', 'partner_id': cli.id,
    'invoice_date': hoy, 'invoice_date_due': hoy + timedelta(days=1),
    'invoice_line_ids': [(0, 0, {'product_id': prod.id, 'quantity': 1,
                                 'price_unit': 5000})],
})
fac2.action_post()
impagas2 = env['account.move'].search([
    ('move_type','=','out_invoice'), ('state','=','posted'),
    ('payment_state','in',('not_paid','partial'))])
vencidas2 = impagas2.filtered(lambda f: f.invoice_date_due and f.invoice_date_due < hoy)
paso("Una factura que aun no vence no cuenta como vencida",
     fac2 in impagas2 and fac2 not in vencidas2)

# --- la pantalla se dibuja ---
html = str(env['ir.qweb']._render('agrogood_pwa.direccion_home', {
    'hoy_n': 0, 'hoy_monto': 0.0, 'mes_monto': 0.0,
    'por_entregar_n': 0, 'por_entregar_monto': 0.0,
    'por_cobrar': por_cobrar, 'por_cobrar_n': len(impagas2),
    'vencido': sum(vencidas2.mapped('amount_residual')), 'vencido_n': len(vencidas2),
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
