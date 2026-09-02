"""Prueba de la cuenta corriente: que se debe y que se pago.

    odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/prueba_cobranza.py

Termina con rollback: no deja nada.

Agrogood emite sus facturas en el portal del SII, de modo que en Odoo no hay ni
una factura de venta. La cobranza se lleva sobre la ORDEN DE COMPRA -que es
como Agrogood llama a su pedido de venta-, y eso es lo que se comprueba aqui.

En orden de lo que cuesta si falla:

 1. Que se cobre lo ENTREGADO y no lo pedido. Cobrar los 20 kg pedidos cuando
    salieron 19,4 convierte cada caja en una discusion con el cliente.
 2. Que un abono no se pueda imputar por encima de lo que trae, ni una orden
    quedar pagada de mas. Sin eso, el saldo del cliente miente.
 3. Que el reparto automatico vaya de la deuda mas antigua a la mas nueva, y
    que lo que sobra se vea sobrar en vez de cuadrarse a la fuerza.
"""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError

R = []


def paso(t, ok, det=""):
    R.append(ok)
    print("  [%s] %s" % ("OK " if ok else "FALLA", t))
    if det:
        print("        %s" % det)


def entregar(pedido, cantidades):
    """Valida la salida del pedido entregando lo que se diga, no lo pedido."""
    salida = pedido.picking_ids.filtered(
        lambda p: p.picking_type_id.code == 'outgoing' and p.state != 'cancel')
    salida.action_assign()
    for mov, cantidad in zip(salida.move_ids, cantidades):
        mov.quantity = cantidad
        mov.picked = True
    resultado = salida.button_validate()
    if isinstance(resultado, dict) and resultado.get('res_model'):
        # Odoo pide confirmacion -pedido en espera, cantidad insuficiente-.
        asistente = env[resultado['res_model']].browse(
            resultado.get('res_id')).with_context(**resultado.get('context', {}))
        if hasattr(asistente, 'process'):
            asistente.process()
    return salida


print("=" * 74)
print("CUENTA CORRIENTE")
print("=" * 74)

linea = env.ref('agrogood_base.business_line_horeca')
alm = env['stock.warehouse'].search([], limit=1)

cliente = env['res.partner'].create({
    'name': 'CLIENTE PRUEBA COBRANZA', 'is_company': True, 'customer_rank': 1,
    'agrogood_business_line_id': linea.id, 'agrogood_credit_days': 30,
})
producto = env['product.template'].create({
    'name': 'TOMATE PRUEBA COBRANZA', 'is_storable': True,
    'list_price': 1000.0, 'agrogood_is_variable_weight': True,
    'uom_id': env.ref('uom.product_uom_kgm').id,
    'uom_po_id': env.ref('uom.product_uom_kgm').id,
}).product_variant_id
env['stock.quant'].with_context(inventory_mode=True).create({
    'product_id': producto.id, 'location_id': alm.lot_stock_id.id,
    'inventory_quantity': 500,
})._apply_inventory()

# ------------------------------------------------- 1. se debe lo entregado
print()
print("QUE SE DEBE")

pedido = env['sale.order'].create({
    'partner_id': cliente.id,
    'order_line': [(0, 0, {'product_id': producto.id, 'product_uom_qty': 20})],
})
pedido.action_confirm()
paso("Un pedido confirmado y sin entregar no se cobra todavia",
     pedido.agrogood_collection_state == 'nothing'
     and pedido.agrogood_charge_amount == 0,
     "cobrable: %.0f" % pedido.agrogood_charge_amount)

entregar(pedido, [19.4])
pedido.invalidate_recordset()
esperado = pedido.order_line[0].price_total * 19.4 / 20.0
paso("Se cobra lo entregado, no lo pedido",
     abs(pedido.agrogood_charge_amount - esperado) < 1.0,
     "pedidos 20 kg, entregados %g; cobrable %s de %s"
     % (pedido.order_line[0].qty_delivered,
        "{:,.0f}".format(pedido.agrogood_charge_amount).replace(",", "."),
        "{:,.0f}".format(pedido.order_line[0].price_total).replace(",", ".")))
paso("La orden entra en la lista de por cobrar",
     pedido.agrogood_collection_state == 'open'
     and pedido.agrogood_due_amount == pedido.agrogood_charge_amount)

cliente.invalidate_recordset()
paso("El saldo del cliente recoge la orden",
     abs(cliente.agrogood_balance - pedido.agrogood_due_amount) < 1.0,
     "saldo: %s" % "{:,.0f}".format(cliente.agrogood_balance).replace(",", "."))
paso("Con 30 dias de plazo, la orden todavia no esta vencida",
     pedido.agrogood_overdue_days == 0 and cliente.agrogood_overdue_balance == 0,
     "vence el %s" % pedido.agrogood_due_date)

# --------------------------------------------------------- 2. el abono calza
print()
print("EL ABONO Y LA ORDEN")

Mov = env['agrogood.bank.movement']
abono = Mov.create({
    'bank': 'santander', 'date': fields.Date.context_today(cliente),
    'amount': pedido.agrogood_due_amount, 'partner_id': cliente.id,
    'unique_key': 'cobranza|exacto',
})
paso("Se reconoce la orden que calza exactamente con el abono",
     abono.order_match_id == pedido, abono.order_match_id.name or "ninguna")

abono.action_imputar()
pedido.invalidate_recordset()
abono.invalidate_recordset()
cliente.invalidate_recordset()
paso("Al imputarlo, la orden queda pagada",
     pedido.agrogood_collection_state == 'paid'
     and abs(pedido.agrogood_due_amount) < 1.0)
paso("El abono queda sin nada por imputar",
     abs(abono.amount_unapplied) < 1.0,
     "sin imputar: %.0f" % abono.amount_unapplied)
paso("El saldo del cliente vuelve a cero",
     abs(cliente.agrogood_balance) < 1.0)

# -------------------------------------- 3. una transferencia, varias entregas
print()
print("UNA TRANSFERENCIA QUE CUBRE VARIAS ENTREGAS")

hoy = fields.Date.context_today(cliente)
cliente.write({'agrogood_credit_days': 0})    # estas dos se pactan al contado
pedidos = []
for dias, cantidad in ((10, 10), (3, 10)):
    p = env['sale.order'].create({
        'partner_id': cliente.id,
        'order_line': [(0, 0, {'product_id': producto.id,
                               'product_uom_qty': cantidad})],
    })
    p.action_confirm()
    entregar(p, [cantidad])
    p.write({'date_order': fields.Datetime.now() - timedelta(days=dias)})
    p.invalidate_recordset()
    pedidos.append(p)
vieja, nueva = pedidos

paso("Sin plazo pactado, lo entregado hace diez dias esta vencido",
     vieja.agrogood_overdue_days >= 9 and cliente.agrogood_overdue_balance > 0,
     "atraso mas antiguo: %d dias" % cliente.agrogood_oldest_due_days)

# Ampliarle el plazo a un cliente moroso NO puede descontar sus entregas ya
# vencidas: vale el plazo que se pacto ese dia, no el de hoy. Sin esto, un
# cliente desaparece de la lista de cobranza cambiandole un numero en la ficha.
cliente.write({'agrogood_credit_days': 60})
vieja.invalidate_recordset()
cliente.invalidate_recordset()
paso("Ampliar el plazo del cliente no re-fecha lo ya entregado",
     vieja.agrogood_overdue_days >= 9 and vieja.agrogood_credit_days == 0,
     "la orden conserva sus %d dias de plazo" % vieja.agrogood_credit_days)

# Una transferencia que cubre la entrega vieja entera y parte de la nueva.
parcial = vieja.agrogood_due_amount + nueva.agrogood_due_amount / 2.0
abono2 = Mov.create({
    'bank': 'scotiabank', 'date': hoy, 'amount': parcial,
    'partner_id': cliente.id, 'unique_key': 'cobranza|parcial',
})
abono2.action_imputar()
vieja.invalidate_recordset()
nueva.invalidate_recordset()
paso("Se paga primero la deuda mas antigua",
     vieja.agrogood_collection_state == 'paid'
     and nueva.agrogood_collection_state == 'partial',
     "la vieja %s, la nueva %s"
     % (vieja.agrogood_collection_state, nueva.agrogood_collection_state))
paso("Lo que queda de la nueva sigue apareciendo como deuda",
     abs(nueva.agrogood_due_amount - nueva.agrogood_charge_amount / 2.0) < 1.0,
     "queda debiendo %s"
     % "{:,.0f}".format(nueva.agrogood_due_amount).replace(",", "."))

# ------------------------------------------------- 4. lo que no puede pasar
print()
print("LO QUE NO PUEDE PASAR")

try:
    env['agrogood.payment.allocation'].create({
        'movement_id': abono2.id, 'order_id': nueva.id, 'amount': 999999999.0,
    })
    paso("No se puede repartir mas de lo que trae el abono", False, "se acepto")
except ValidationError:
    paso("No se puede repartir mas de lo que trae el abono", True)

sobrante = Mov.create({
    'bank': 'santander', 'date': hoy, 'amount': 5000000.0,
    'partner_id': cliente.id, 'unique_key': 'cobranza|sobra',
})
sobrante.action_imputar()
sobrante.invalidate_recordset()
paso("Si sobra dinero, sobra y se ve; no se cuadra a la fuerza",
     sobrante.amount_unapplied > 0,
     "queda sin imputar %s"
     % "{:,.0f}".format(sobrante.amount_unapplied).replace(",", "."))

huerfano = Mov.create({
    'bank': 'santander', 'date': hoy, 'amount': 1000.0,
    'unique_key': 'cobranza|sin cliente',
})
resultado = huerfano.action_imputar()
paso("Un abono sin cliente no imputa nada y lo dice",
     not huerfano.allocation_ids
     and resultado['params']['type'] == 'warning')

# ------------------------------------------- 5. la deuda de antes de Agroapp
print()
print("EL SALDO DE APERTURA")

viejo = env['res.partner'].create({
    'name': 'CLIENTE PRUEBA APERTURA', 'is_company': True, 'customer_rank': 1,
    'agrogood_business_line_id': linea.id, 'agrogood_credit_days': 0,
    'agrogood_opening_balance': 100000.0,
    'agrogood_opening_date': hoy - timedelta(days=30),
})
paso("Lo que ya debia cuenta en su saldo sin ninguna orden de compra",
     viejo.agrogood_balance == 100000.0 and viejo.agrogood_open_order_count == 0,
     "debe %s con %d ordenes en el sistema"
     % ("{:,.0f}".format(viejo.agrogood_balance).replace(",", "."),
        viejo.agrogood_open_order_count))
paso("Y esta vencido por definicion: es deuda de antes del corte",
     viejo.agrogood_overdue_balance == 100000.0
     and viejo.agrogood_oldest_due_days == 30,
     "%d dias de atraso" % viejo.agrogood_oldest_due_days)

# Una entrega nueva, posterior al corte.
reciente = env['sale.order'].create({
    'partner_id': viejo.id,
    'order_line': [(0, 0, {'product_id': producto.id, 'product_uom_qty': 10})],
})
reciente.action_confirm()
entregar(reciente, [10])
reciente.invalidate_recordset()
viejo.invalidate_recordset()
paso("El saldo suma lo viejo y lo nuevo",
     abs(viejo.agrogood_balance
         - (100000.0 + reciente.agrogood_due_amount)) < 1.0,
     "%s de apertura mas %s de la entrega"
     % ("{:,.0f}".format(viejo.agrogood_opening_due).replace(",", "."),
        "{:,.0f}".format(reciente.agrogood_due_amount).replace(",", ".")))

# Un abono que NO alcanza para todo: tiene que morder primero lo mas antiguo.
# 105.000 cubre los 100.000 de apertura y deja 5.000 para la entrega, que debe
# 11.900. Si el reparto fuera al reves, la apertura quedaria a medias y seria
# la deuda que nunca se termina de cobrar.
abono3 = Mov.create({
    'bank': 'santander', 'date': hoy, 'amount': 105000.0,
    'partner_id': viejo.id, 'unique_key': 'cobranza|apertura',
})
abono3.action_imputar()
viejo.invalidate_recordset()
reciente.invalidate_recordset()
abono3.invalidate_recordset()
paso("Se paga primero lo de antes de Agroapp, que es lo mas antiguo",
     viejo.agrogood_opening_due == 0
     and reciente.agrogood_collection_state == 'partial',
     "apertura saldada; de la entrega quedan %s"
     % "{:,.0f}".format(reciente.agrogood_due_amount).replace(",", "."))
paso("Y el abono se reparte entero, sin dejar nada suelto",
     abs(abono3.amount_unapplied) < 1.0
     and len(abono3.allocation_ids) == 2,
     "%d imputaciones" % len(abono3.allocation_ids))

try:
    env['agrogood.payment.allocation'].create({
        'movement_id': abono3.id, 'opening_partner_id': viejo.id,
        'order_id': reciente.id, 'amount': 100.0,
    })
    paso("Una imputacion apunta a una sola deuda", False, "se acepto a las dos")
except ValidationError:
    paso("Una imputacion apunta a una sola deuda", True)

sobra = Mov.create({
    'bank': 'santander', 'date': hoy, 'amount': 90000.0,
    'partner_id': viejo.id, 'unique_key': 'cobranza|apertura2'})
try:
    env['agrogood.payment.allocation'].create({
        'movement_id': sobra.id, 'opening_partner_id': viejo.id,
        'amount': 90000.0})
    paso("No se puede pagar el saldo de apertura de mas", False, "se acepto")
except ValidationError:
    paso("No se puede pagar el saldo de apertura de mas", True,
         "ya estaba saldado")

print()
print("=" * 74)
print("%d de %d comprobaciones" % (sum(1 for x in R if x), len(R)))
print("=" * 74)
print("La cuenta corriente cuadra." if all(R) else "HAY FALLOS. Revisar arriba.")

env.cr.rollback()
