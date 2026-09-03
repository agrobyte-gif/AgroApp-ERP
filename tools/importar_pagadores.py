"""Ensena a Agroapp quien es cada pagador, desde la planilla ya llena.

    odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/importar_pagadores.py

Lee C:\\dev\\Pagadores por identificar.xlsx, guarda cada RUT como identidad de
pago del cliente que se escribio al lado, y vuelve a cruzar los abonos.

Tres decisiones que conviene tener a la vista:

1. **No se crean clientes.** Si el nombre escrito no existe en Odoo, la fila se
   informa y se deja quieta. Crear la ficha aqui llenaria la lista de clientes
   de variantes tipograficas del mismo negocio, que despues hay que fusionar a
   mano y mientras tanto parten la cuenta corriente en dos.

2. **Un RUT que ya es de otro cliente no se pisa: se marca compartido.** Es lo
   que hace `aprender()`, y es lo que pasa de verdad -la sociedad que paga por
   dos locales-. A partir de ahi ese RUT espera a una persona en vez de
   asignar solo.

3. **Se aprende, y recien despues se cruza.** Cruzar primero no serviria de
   nada: lo que hace que el cruce encuentre algo nuevo es justamente lo que se
   acaba de ensenar.
"""

import os

try:
    import openpyxl
except ImportError:
    raise SystemExit("Falta openpyxl: .venv\\Scripts\\pip install openpyxl")

from odoo.addons.agrogood_crm_reactivation.models.agrogood_payer import (
    normalizar_rut)

ORIGEN = r"C:\dev\Pagadores por identificar.xlsx"
if not os.path.exists(ORIGEN):
    raise SystemExit("No esta %s. Primero: tools/exportar_pagadores.py" % ORIGEN)

hoja = openpyxl.load_workbook(ORIGEN, data_only=True).active
filas = list(hoja.iter_rows(values_only=True))
cab = [str(c or "").strip().upper() for c in filas[0]]


def cual(*claves):
    for i, c in enumerate(cab):
        if any(k in c for k in claves):
            return i
    raise SystemExit("No encuentro la columna %s en la planilla." % (claves,))


iru, ino = cual("RUT"), cual("CLIENTE")

P = env['res.partner']
Pagador = env['agrogood.payer']


def compacto(t):
    return " ".join(str(t or "").split()).upper()


# El indice se arma una vez: buscar cliente por cliente con ilike sobre 450
# filas es lento y ademas encuentra parecidos, que es lo que no se quiere.
indice = {}
for c in P.search([('customer_rank', '>', 0)]):
    indice.setdefault(compacto(c.name), c)

aprendidos, ya_estaban, sin_ficha, sin_nombre = 0, 0, {}, 0

for f in filas[1:]:
    if iru >= len(f) or ino >= len(f):
        continue
    rut = normalizar_rut(f[iru])
    nombre = str(f[ino] or "").strip()
    if not rut:
        continue
    if not nombre:
        sin_nombre += 1
        continue
    cliente = indice.get(compacto(nombre))
    if not cliente:
        sin_ficha[nombre] = sin_ficha.get(nombre, 0) + 1
        continue
    existe = Pagador.search([('kind', '=', 'rut'), ('value', '=', rut)], limit=1)
    if existe and existe.partner_id == cliente:
        ya_estaban += 1
        continue
    Pagador.aprender(cliente, rut=rut)
    aprendidos += 1

print("=" * 74)
print("IDENTIDADES DE PAGO")
print("=" * 74)
print("  aprendidas ahora      : %d" % aprendidos)
print("  ya estaban            : %d" % ya_estaban)
print("  sin nombre en la hoja : %d  (se dejan para despues)" % sin_nombre)
print("  nombre que no existe  : %d" % len(sin_ficha))
for n in sorted(sin_ficha)[:15]:
    print("      %s" % n)
if len(sin_ficha) > 15:
    print("      ... y %d mas" % (len(sin_ficha) - 15))
if sin_ficha:
    print()
    print("  Esos nombres no estan en la lista de clientes de Odoo. O se")
    print("  corrige la escritura en la planilla, o se crea la ficha antes.")

# Ahora si: se vuelve a mirar lo que estaba sin nombre.
M = env['agrogood.bank.movement']
antes = M.search_count([('state', '=', 'identified')])
pendientes = M.search([('state', 'in', ('unknown', 'doubtful'))])
print()
print("Volviendo a cruzar %d abonos..." % len(pendientes))
pendientes._cruzar()
env.cr.flush()
despues = M.search_count([('state', '=', 'identified')])


def plata(x):
    return "{:,.0f}".format(x).replace(",", ".")


nuevos = M.search([('state', '=', 'identified')])
print("  reconocidos antes : %d" % antes)
print("  reconocidos ahora : %d   (+%d)" % (despues, despues - antes))
print("  plata reconocida  : %s" % plata(sum(nuevos.mapped('amount'))))
print()
print("Nada esta guardado todavia. Para dejarlo: env.cr.commit()")
