"""Saca la lista de quienes pagan y todavia no tienen nombre.

    odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/exportar_pagadores.py

Deja C:\\dev\\Pagadores por identificar.xlsx

Son 454 RUT distintos, pero no hacen falta los 454. Treinta de ellos son el 71%
de la plata: la hoja va ordenada por monto justamente para que se pueda parar
cuando deje de valer la pena, en vez de tener que llegar al final.

La columna que se llena es UNA: el nombre del cliente. El RUT ya viene, y con
el RUT se enlaza solo.
"""

import os
from collections import defaultdict

try:
    import xlsxwriter
except ImportError:
    raise SystemExit("Falta xlsxwriter: .venv\\Scripts\\pip install xlsxwriter")

DESTINO = r"C:\dev\Pagadores por identificar.xlsx"

M = env['agrogood.bank.movement']
sin_nombre = M.search([('state', '=', 'unknown'), ('amount', '>', 0),
                       ('payer_rut', '!=', False)])

# Se agrupa por RUT: el banco escribe el mismo pagador de diez maneras y lo que
# se identifica es la persona, no cada linea.
grupos = defaultdict(lambda: {'monto': 0.0, 'veces': 0, 'alias': set(),
                              'primera': None, 'ultima': None})
for m in sin_nombre:
    g = grupos[m.payer_rut]
    g['monto'] += m.amount
    g['veces'] += 1
    texto = (m.payer_alias or m.payer_name or m.description or "").strip()
    if texto:
        g['alias'].add(texto[:40])
    if not g['primera'] or m.date < g['primera']:
        g['primera'] = m.date
    if not g['ultima'] or m.date > g['ultima']:
        g['ultima'] = m.date

orden = sorted(grupos.items(), key=lambda x: -x[1]['monto'])

# Si el RUT ya esta en una ficha, no hay nada que preguntar: se dice cual es.
P = env['res.partner']
def ficha(rut):
    c = P.search([('vat', 'in', (rut, 'CL' + rut))], limit=1)
    return c.name if c else ""

# Y si no esta en una ficha, puede estar en la planilla de RUT que Victor ya
# tenia. Esa planilla no es una ficha -son empresas, no clientes de Odoo- pero
# sirve para no volver a preguntar 97 nombres que ya estaban escritos.
PLANILLA = r"C:\dev\DATOS CLIENTES RUT.xlsx"
conocidos = {}
if os.path.exists(PLANILLA):
    import openpyxl
    from odoo.addons.agrogood_crm_reactivation.models.agrogood_payer import (
        normalizar_rut)
    hoja = openpyxl.load_workbook(PLANILLA, data_only=True).active
    filas = list(hoja.iter_rows(values_only=True))
    cab = [str(c or "").strip().upper() for c in filas[0]]
    def cual(*claves):
        for i, c in enumerate(cab):
            if any(k in c for k in claves):
                return i
        return None
    iru = cual("RUT")
    ino = cual("EMPRESA", "NOMBRE", "CLIENTE", "RAZON")
    for f in filas[1:]:
        if iru is None or iru >= len(f):
            continue
        r = normalizar_rut(f[iru])
        if r and ino is not None and ino < len(f):
            conocidos[r] = str(f[ino] or "").strip()

if os.path.exists(DESTINO):
    raise SystemExit("Ya existe %s. Se renombra o se borra antes." % DESTINO)

libro = xlsxwriter.Workbook(DESTINO)
h = libro.add_worksheet("Pagadores")
titulo = libro.add_format({'bold': True, 'bg_color': '#1F5C3A',
                           'font_color': 'white', 'border': 1})
pesos = libro.add_format({'num_format': '#,##0'})
llenar = libro.add_format({'bg_color': '#FFF3C4', 'border': 1})
gris = libro.add_format({'font_color': '#888888'})

COLS = ["RUT", "Como aparece en el banco", "Cuanto pago", "Abonos",
        "Desde", "Hasta", "% acumulado", "CLIENTE (llenar aqui)",
        "De donde salio"]
for i, c in enumerate(COLS):
    h.write(0, i, c, titulo)
h.set_column(0, 0, 14)
h.set_column(1, 1, 42)
h.set_column(2, 2, 16)
h.set_column(3, 6, 11)
h.set_column(7, 7, 40)
h.set_column(8, 8, 22)
h.freeze_panes(1, 0)

total = sum(g['monto'] for _, g in orden) or 1.0
acumulado = 0.0
for f, (rut, g) in enumerate(orden, start=1):
    acumulado += g['monto']
    h.write(f, 0, rut)
    h.write(f, 1, " / ".join(sorted(g['alias']))[:120])
    h.write(f, 2, g['monto'], pesos)
    h.write(f, 3, g['veces'])
    h.write(f, 4, str(g['primera'] or ""), gris)
    h.write(f, 5, str(g['ultima'] or ""), gris)
    h.write(f, 6, "%.0f%%" % (100.0 * acumulado / total), gris)
    nombre, origen = ficha(rut), "ficha de Odoo"
    if not nombre:
        nombre, origen = conocidos.get(rut, ""), "planilla de RUT"
    if not nombre:
        origen = ""
    h.write(f, 7, nombre, llenar)
    h.write(f, 8, origen, gris)

libro.close()

ya = sum(1 for rut, _ in orden if ficha(rut) or conocidos.get(rut))
print("Escrito: %s" % DESTINO)
print("  %d RUT sin identificar, %s en total"
      % (len(orden), "{:,.0f}".format(total).replace(",", ".")))
print("  %d vienen con nombre propuesto: solo hay que confirmarlo" % ya)
print("  %d hay que escribirlos a mano" % (len(orden) - ya))
print()
print("Se llena de arriba hacia abajo y se para donde el % acumulado deje de")
print("importar. Despues: tools/importar_pagadores.py")
