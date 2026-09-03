"""Prueba de la caja chica.

    odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/prueba_caja_chica.py

Termina con rollback: no deja nada.

Una caja chica es un sobre con plata y un cuaderno. Lo que la hace servir no es
anotar los gastos -eso lo hace cualquiera- sino dos controles:

 1. Un gasto exige boleta, y si no la hay, exige decir por que. Sin eso, "se
    gastaron 20 mil en algo" es indistinguible de que falten 20 mil.
 2. Quien gasta no repone. Si la misma persona pudiera sacar y rellenar, el
    saldo siempre cuadraria y no significaria nada.

Eso es lo que se comprueba, mas que el saldo salga bien.
"""

import base64

from odoo.exceptions import AccessError, ValidationError
from odoo.addons.agrogood_pwa.controllers import main as controlador
from odoo.addons.agrogood_pwa.controllers.main import AgrogoodCaja

R = []


def paso(t, ok, det=""):
    R.append(ok)
    print("  [%s] %s" % ("OK " if ok else "FALLA", t))
    if det:
        print("        %s" % det)


class PeticionFalsa(object):
    def __init__(self, entorno):
        self.env = entorno


def rechaza(descripcion, vals, detalle=""):
    """Comprueba que ESOS valores no se puedan guardar, y no deje rastro.

    El punto de retorno no es un adorno. Cuando una restriccion revienta un
    create, el INSERT ya se hizo y sigue vivo en la transaccion: sin deshacerlo,
    el gasto rechazado se suma al saldo y las cuentas de mas abajo salen mal
    por un movimiento que nunca debio existir. En una peticion de verdad Odoo
    deshace la transaccion entera y esto no pasa; en un script hay que hacerlo
    a mano.
    """
    punto = env.cr.savepoint(flush=False)
    try:
        env['agrogood.petty.cash'].create(vals)
        env.cr.flush()
        punto.rollback()
        paso(descripcion, False, "se acepto")
    except Exception as e:
        punto.rollback()
        paso(descripcion, isinstance(e, ValidationError),
             detalle or str(e).replace(chr(10), " ")[:70])


# Un PNG de 1x1 hace de boleta: lo que se prueba es que se exija una foto, no
# que la foto se vea bien.
BOLETA = base64.b64encode(base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
    "IQAAAABJRU5ErkJggg=="))

print("=" * 74)
print("CAJA CHICA")
print("=" * 74)

Caja = env['agrogood.petty.cash']
# La prueba mide su propio movimiento contra este punto de partida, no contra
# cero. La caja de verdad puede tener ya un sobre cargado -de hecho lo tiene,
# para poder probarla en el telefono- y una prueba que diera por vacia la base
# fallaria por plata que no puso ella. El saldo es un acumulado: importa cuanto
# lo mueve cada movimiento, no en que numero cae.
saldo_base = Caja.saldo()
victor = env['res.users'].search([('login', '=', 'victor@agrogood.cl')], limit=1)
johan = env['res.users'].search([('login', '=', 'johan@agrogood.cl')], limit=1)
picker = env['res.users'].search(
    [('login', '=', 'felipe.collio@agrogood.cl')], limit=1)

# ------------------------------------------------------- 1. el respaldo
print()
print("EL RESPALDO DEL GASTO")

rechaza("Un gasto sin boleta ni explicacion no entra",
        {'kind': 'gasto', 'amount': 20000, 'category': 'peaje'},
        "sin eso, un gasto sin respaldo no se distingue de plata que falta")

con_foto = Caja.create({'kind': 'gasto', 'amount': 12000,
                        'category': 'combustible', 'receipt': BOLETA,
                        'note': 'Bencina camion INT-01'})
paso("Con boleta, entra", bool(con_foto.receipt))

sin_foto = Caja.create({'kind': 'gasto', 'amount': 3000, 'category': 'peaje',
                        'no_receipt_reason': 'No dieron boleta en el peaje'})
paso("Sin boleta pero con explicacion, tambien",
     bool(sin_foto.no_receipt_reason) and not sin_foto.receipt,
     "queda a la vista para cuando Direccion cuadre el sobre")

rechaza("Un gasto sin decir en que no entra",
        {'kind': 'gasto', 'amount': 5000, 'receipt': BOLETA})

rechaza("Un monto negativo no entra",
        {'kind': 'gasto', 'amount': -5000, 'category': 'otros',
         'receipt': BOLETA},
        "gasto y reposicion se distinguen por el tipo, no por el signo")

# ------------------------------------------------------------ 2. el saldo
print()
print("EL SALDO DEL SOBRE")

# Hasta aqui la prueba lleva gastados 15.000 (12.000 + 3.000). La reposicion
# sube 100.000, de modo que el saldo tiene que quedar 85.000 por encima de
# donde arranco, sea cual sea ese numero.
reposicion = Caja.create({'kind': 'reposicion', 'amount': 100000,
                          'note': 'Sobre de septiembre'})
paso("La reposicion suma", Caja.saldo() == saldo_base + 100000 - 15000,
     "85.000 mas que al empezar; ahora hay %s"
     % "{:,.0f}".format(Caja.saldo()).replace(",", "."))

con_foto.invalidate_recordset()
# La reposicion es el ultimo movimiento, asi que lo que quedaba despues de ella
# es el saldo de ahora. Es la invariante que ata las dos cuentas -recorrer
# desde el principio y sumar el total- sin depender de con que numero arranco.
paso("Cada movimiento sabe cuanto quedaba despues de el",
     reposicion.balance_after == Caja.saldo(),
     "el saldo se recorre desde el principio, no se resta del total")

# Un gasto mayor que lo que hay tiene que dejar el sobre en rojo y anotarse
# igual. Se dimensiona sobre el saldo actual para que caiga en negativo
# cualquiera sea el punto de partida.
gasto_grande = Caja.create({'kind': 'gasto', 'amount': Caja.saldo() + 50000,
                            'category': 'mercaderia', 'receipt': BOLETA,
                            'note': 'Compra de urgencia en la feria'})
paso("Un gasto que deja el sobre en negativo se ANOTA igual",
     bool(gasto_grande.id) and Caja.saldo() < 0,
     "bloquearlo solo conseguiria que no se anotara en ningun sitio")

# ------------------------------------------------ 3. quien puede y quien no
print()
print("QUIEN PUEDE")

caja_pwa = AgrogoodCaja()

controlador.request = PeticionFalsa(env(user=johan))
paso("Compras puede sacar del sobre", caja_pwa._es_caja(),
     "Johan compra en la feria")

controlador.request = PeticionFalsa(env(user=picker))
paso("Un Picker no", not caja_pwa._es_caja(), picker.login)

r = None
try:
    r = caja_pwa.api_gasto(5000, 'insumos', receipt=BOLETA)
    paso("Y el servidor se lo impide, no solo la pantalla", False, "se acepto")
except AccessError:
    paso("Y el servidor se lo impide, no solo la pantalla", True)

controlador.request = PeticionFalsa(env(user=johan))
r = caja_pwa.api_gasto(4000, 'insumos', note='Guantes', receipt=BOLETA)
paso("Johan anota un gasto desde el telefono", r.get('ok'), r.get('mensaje'))

r = caja_pwa.api_gasto(4000, 'insumos', note='Sin nada')
paso("Sin boleta ni motivo, el endpoint lo rechaza",
     not r.get('ok') and 'boleta' in r.get('mensaje', '').lower(),
     r.get('mensaje', '')[:70])

# La reposicion no esta en la pantalla del telefono: es la separacion que
# hace que el saldo signifique algo.
paso("Reponer el sobre NO se puede desde el telefono",
     not hasattr(caja_pwa, 'api_reposicion'),
     "lo hace Direccion desde el escritorio")

# --------------------------------------------------------- 4. el rastro
print()
print("EL RASTRO")

paso("Cada movimiento queda en su conversacion, con quien y cuanto quedaba",
     bool(con_foto.message_ids)
     and 'sobre' in (con_foto.message_ids[0].body or ''),
     "permite reconstruir por que el sobre no cuadra")
paso("Y se sabe quien lo anoto", con_foto.user_id == env.user,
     con_foto.user_id.name)

sin_boleta = Caja.search_count([('kind', '=', 'gasto'), ('receipt', '=', False)])
paso("Los gastos sin boleta se pueden listar de un tiron",
     sin_boleta >= 1, "%d ahora mismo; es el filtro con el que se cuadra" % sin_boleta)

print()
print("=" * 74)
print("%d de %d comprobaciones" % (sum(1 for x in R if x), len(R)))
print("=" * 74)
print("La caja chica se puede auditar." if all(R)
      else "HAY FALLOS. Revisar arriba.")

env.cr.rollback()
