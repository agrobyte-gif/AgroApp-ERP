"""Completa el RUT de los clientes cruzando con la planilla de Agrogood.

    odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/cruzar_ruts.py

Por defecto SOLO INFORMA. Para escribir: AGROGOOD_RUT=escribir

El cruce es por nombre, y ahi esta todo el riesgo: un RUT equivocado en una
factura es un problema tributario, no un error de datos. Por eso el criterio es
deliberadamente conservador:

* Solo se aplican automaticamente las coincidencias de altisima confianza.
* Todo RUT se valida por digito verificador antes de tocarlo.
* Un RUT que ya aparece en otro cliente NO se reasigna: se reporta.
* Lo dudoso se lista para que una persona lo revise, no se adivina.

Es preferible dejar veinte clientes sin RUT que ponerle a uno el RUT de otro.
"""

import difflib
import os
import re
import unicodedata

import openpyxl

RUTA = r"C:\dev\agrogood\DATOS CLIENTES RUT.xlsx"
ESCRIBIR = os.environ.get("AGROGOOD_RUT") == "escribir"

# Por encima de este parecido se aplica solo; entre el minimo y este, se revisa.
AUTO = 0.92
REVISAR = 0.72


def dv(cuerpo):
    s, m = 0, 2
    for d in reversed(cuerpo):
        s += int(d) * m
        m = 2 if m == 7 else m + 1
    r = 11 - (s % 11)
    return {11: '0', 10: 'K'}.get(r, str(r))


def rut_valido(rut):
    m = re.fullmatch(r"(\d+)-([\dK])", rut)
    return bool(m) and dv(m.group(1)) == m.group(2)


def normaliza(nombre):
    """Deja el nombre en su forma comparable.

    Se quitan las anotaciones entre parentesis -la planilla lleva cosas como
    '(DETALLE:CONTADO)', que son notas de cobranza y no parte del nombre-, los
    sufijos societarios y los acentos.
    """
    t = unicodedata.normalize("NFD", str(nombre or ""))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").upper()
    t = re.sub(r"\([^)]*\)", " ", t)          # notas entre parentesis
    t = re.sub(r"\bDETALLE\b.*$", " ", t)      # notas sin cerrar parentesis
    t = re.sub(r"\b(SPA|LTDA|LIMITADA|EIRL|S\.?A\.?|E\.?I\.?R\.?L\.?)\b", " ", t)
    t = re.sub(r"[^A-Z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# ---------------------------------------------------------------------------
# Lectura de la planilla
# ---------------------------------------------------------------------------
ws = openpyxl.load_workbook(RUTA, data_only=True)["Hoja1"]
filas = [r for r in ws.iter_rows(values_only=True) if any(c not in (None, "") for c in r)]

catalogo = {}      # nombre normalizado -> (rut, nombre original)
ruts_malos = []
for r in filas[1:]:
    rut = str(r[0] or "").strip().upper().replace(".", "")
    nombre = str(r[1] or "").strip()
    if not rut or not nombre:
        continue
    if not rut_valido(rut):
        ruts_malos.append((rut, nombre))
        continue
    clave = normaliza(nombre)
    if clave:
        catalogo.setdefault(clave, (rut, nombre))

print("=" * 78)
print("CRUCE DE RUT" + ("  [ESCRIBIENDO]" if ESCRIBIR else "  [SOLO INFORME]"))
print("=" * 78)
print(f"\nPlanilla: {len(filas)-1} filas, {len(catalogo)} nombres utilizables")
if ruts_malos:
    print(f"  RUT con digito verificador invalido, se descartan: {len(ruts_malos)}")
    for rut, nom in ruts_malos[:6]:
        print(f"     {rut:<13} {nom[:44]}")

# ---------------------------------------------------------------------------
# Clientes sin RUT
# ---------------------------------------------------------------------------
Socio = env['res.partner']
# Se revisan TODOS los clientes, no solo los que no tienen RUT.
# El motivo: se comprobo que los RUT cargados originalmente estaban
# desalineados -alguien ordeno la columna de RUT sin arrastrar la de nombres-,
# de modo que los existentes tampoco son de fiar. La planilla DATOS CLIENTES
# RUT es la fuente correcta y manda sobre lo que haya en el sistema.
sin_rut = Socio.search([
    ('agrogood_business_line_id', '!=', False),
    ('parent_id', '=', False),
])
ya_usados = {p.vat: p for p in Socio.search([('vat', '!=', False)])}
print(f"\nClientes sin RUT en el sistema: {len(sin_rut)}")

claves = list(catalogo.keys())
automaticos, dudosos, sin_encontrar, chocan = [], [], [], []

for socio in sin_rut:
    clave = normaliza(socio.name)
    if not clave:
        sin_encontrar.append((socio, None, 0))
        continue

    if clave in catalogo:
        rut, origen = catalogo[clave]
        parecido = 1.0
    else:
        cercanos = difflib.get_close_matches(clave, claves, n=1, cutoff=REVISAR)
        if not cercanos:
            sin_encontrar.append((socio, None, 0))
            continue
        rut, origen = catalogo[cercanos[0]]
        parecido = difflib.SequenceMatcher(None, clave, cercanos[0]).ratio()

    # Un RUT ya asignado a otro cliente no se reasigna: o son el mismo negocio
    # y hay que unificarlos a mano, o el cruce se equivoco. En ambos casos lo
    # decide una persona.
    # El RUT que ya tuviera el cliente no cuenta como conflicto consigo mismo,
    # y ademas se sabe que puede estar mal.
    if rut in ya_usados and ya_usados[rut].id != socio.id             and ya_usados[rut].vat != socio.vat:
        chocan.append((socio, rut, origen, ya_usados[rut], parecido))
    elif parecido >= AUTO:
        automaticos.append((socio, rut, origen, parecido))
    else:
        dudosos.append((socio, rut, origen, parecido))

print(f"\n  coincidencia clara (>= {AUTO:.0%})  : {len(automaticos)}")
print(f"  a revisar por una persona      : {len(dudosos)}")
print(f"  RUT ya usado por otro cliente  : {len(chocan)}")
print(f"  sin coincidencia en la planilla: {len(sin_encontrar)}")

if automaticos:
    print("\n" + "-" * 78)
    print("SE APLICAN (coincidencia clara)")
    for s, rut, origen, p in automaticos[:40]:
        cambio = f"  (antes tenia {s.vat}, INCORRECTO)" if s.vat and s.vat != rut else ""
        print(f"  {rut:<13} {s.name[:30]:<30} <- {origen[:26]}{cambio}")
    if len(automaticos) > 40:
        print(f"  ... y {len(automaticos)-40} mas")

if dudosos:
    print("\n" + "-" * 78)
    print("A REVISAR - parecidos pero no identicos, NO se tocan")
    for s, rut, origen, p in sorted(dudosos, key=lambda x: -x[3]):
        print(f"  {p:.0%}  {rut:<13} {s.name[:30]:<30} ?= {origen[:30]}")

if chocan:
    print("\n" + "-" * 78)
    print("CONFLICTO - ese RUT ya lo tiene otro cliente")
    for s, rut, origen, otro, p in chocan:
        print(f"  {rut:<13} {s.name[:26]:<26} vs ya asignado a {otro.name[:26]}")
    print("  Probablemente sean el mismo negocio con dos fichas. Unificar a mano.")

if sin_encontrar:
    print("\n" + "-" * 78)
    print(f"SIN COINCIDENCIA ({len(sin_encontrar)}) - no estan en la planilla")
    for s, _, _ in sin_encontrar[:25]:
        print(f"  {s.name[:60]}")
    if len(sin_encontrar) > 25:
        print(f"  ... y {len(sin_encontrar)-25} mas")

# ---------------------------------------------------------------------------
if not ESCRIBIR:
    print("\n" + "=" * 78)
    print("SOLO INFORME. Nada se ha modificado.")
    print("Para aplicar las coincidencias claras: AGROGOOD_RUT=escribir")
    print("=" * 78)
else:
    tipo_rut = env.ref('l10n_cl.it_RUT', raise_if_not_found=False)
    n = 0
    for s, rut, origen, p in automaticos:
        vals = {'vat': rut}
        if tipo_rut:
            vals['l10n_latam_identification_type_id'] = tipo_rut.id
        # Tipo 1: afecto a IVA, primera categoria. Es lo que corresponde a un
        # negocio formal con RUT de empresa, que es el caso de esta cartera.
        if not s.l10n_cl_sii_taxpayer_type:
            vals['l10n_cl_sii_taxpayer_type'] = '1'
        s.write(vals)
        s.message_post(body=(
            "RUT completado automaticamente desde la planilla de Agrogood: "
            "%s (fila '%s'). Verificar antes de la primera factura."
        ) % (rut, origen))
        n += 1
    env.cr.commit()
    print("\n" + "=" * 78)
    print(f"APLICADOS: {n} RUT")
    faltan = Socio.search_count([
        ('agrogood_business_line_id', '!=', False),
        ('agrogood_billing_blocked', '=', True)])
    print(f"Clientes que siguen sin poder facturarse: {faltan}")
    print("\nCada cliente modificado tiene una nota en su historial diciendo de")
    print("donde salio el RUT. Conviene revisarlos antes de la primera factura.")
    print("=" * 78)
