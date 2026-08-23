"""Importa clientes y productos de Agrogood desde las planillas de carga masiva.

Se ejecuta dentro del shell de Odoo:

    odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/importar_datos_maestros.py

Por defecto SIMULA: analiza, informa y no escribe nada. Para escribir de verdad
hay que definir la variable de entorno AGROGOOD_IMPORT=escribir.

Decisiones que implementa (ver docs/ADR-003 y ADR-004):

* Entran los 158 clientes. Los que no traen RUT quedan marcados con
  `agrogood_vat_pending`; el bloqueo de facturacion ya lo aplica `l10n_cl`.
* Un RUT compartido por varios locales se modela como UNA empresa con
  direcciones de entrega hijas, no como varios clientes. La factura va al RUT,
  el reparto a cada direccion.
* Las 35 escrituras de unidad se normalizan. Cuando la unidad mezcla formato y
  peso ("Caja 15 Kg"), se separa: unidad = kg, formato = Caja, peso de
  referencia = 15.
* No se importan costos ni stock: los 3 costos existentes son incoherentes
  (costo por bulto contra precio por kilo) y el stock viene vacio.
* No se crea tarifa Mayorista. Sus 4 precios son casos puntuales.
"""

import os
import re
import unicodedata
from collections import Counter, defaultdict

import openpyxl

from odoo import fields

RUTA_CLIENTES = r"C:\Users\pedid\OneDrive\Documents\GitHub\Odoo\Plantilla_Carga_Masiva_Clientes.xlsx"
RUTA_PRODUCTOS = r"C:\Users\pedid\OneDrive\Documents\GitHub\Odoo\Plantilla_Carga_Masiva_Productos.xlsx"

ESCRIBIR = os.environ.get("AGROGOOD_IMPORT") == "escribir"


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def vacio(v):
    return v is None or str(v).strip() == ""


def limpio(v):
    return "" if vacio(v) else str(v).strip()


def sin_tildes(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn").upper()


def leer(ruta, hoja):
    ws = openpyxl.load_workbook(ruta, data_only=True)[hoja]
    filas = [r for r in ws.iter_rows(values_only=True) if any(not vacio(c) for c in r)]
    return filas[1:]


def normaliza_telefono(t):
    """Deja el telefono en formato chileno +56 9 XXXX XXXX cuando se puede."""
    if vacio(t):
        return False
    d = re.sub(r"\D", "", str(t))
    if d.startswith("56"):
        d = d[2:]
    if len(d) == 9 and d.startswith("9"):
        return f"+56 {d[0]} {d[1:5]} {d[5:]}"
    if len(d) == 8:
        return f"+56 9 {d[:4]} {d[4:]}"
    return limpio(t)


# ---------------------------------------------------------------------------
# Normalizacion de unidades
# ---------------------------------------------------------------------------
# Cada entrada devuelve (unidad_odoo, formato, peso_referencia, peso_variable).
#
# El criterio es el de ADR-003: la unidad es aquella en la que se factura.
# Un producto que se vende por peso real va en kilogramos y se marca como de
# peso variable; el formato solo indica como se presenta en bodega.
# Un envase de peso fijo ("200 grs.") es un articulo cerrado: se vende por
# unidad y NO es de peso variable, porque el peso no cambia entre bultos.

FORMATO_CON_PESO = re.compile(
    r"^(caja|malla|mallon|saco|bandeja|paquete|pqte|bolsa)\s*"
    r"(?:de\s*)?(\d+(?:[.,]\d+)?)\s*(kg|kilos?|k)\.?$",
    re.IGNORECASE,
)
SOLO_PESO = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(kg|kilos?)\.?$", re.IGNORECASE)
PESO_FIJO_GRAMOS = re.compile(
    r"^(?:(caja|malla|bandeja|paquete|pqte|bolsa)\s*)?(\d+)\s*(grs?|gramos?)\.?$",
    re.IGNORECASE,
)
CANTIDAD_UNIDADES = re.compile(
    r"^(?:(caja|malla|bandeja|paquete|pqte|bolsa)\s*)?\(?(\d+)\s*(?:un|uni|unid|unidades?)\.?\)?"
    r"(?:\s*aprox\.?)?$",
    re.IGNORECASE,
)

FORMATO_SIMPLE = {
    "CAJA": "Caja", "MALLA": "Malla", "MALLON": "Malla", "SACO": "Saco",
    "BANDEJA": "Bandeja", "PAQUETE": "Paquete", "PQTE": "Paquete",
    "BOLSA": "Bolsa", "BIDON": "Bolsa",
}


def normaliza_unidad(texto):
    """Traduce una de las 35 escrituras de unidad a la configuracion real."""
    t = limpio(texto)
    if not t:
        return ("Units", None, 0.0, False)
    plano = sin_tildes(t).strip()

    if plano in ("KG", "KILO", "KILOS", "K"):
        return ("kg", None, 0.0, True)
    if plano in ("LT", "L", "LITRO", "LITROS"):
        return ("Liters", None, 0.0, False)
    if plano in ("UNIDAD", "UNIDADES", "UN", "UNID"):
        return ("Units", None, 0.0, False)

    m = FORMATO_CON_PESO.match(t)
    if m:  # "Caja 15 Kg" -> se factura por peso, la caja es el formato
        return ("kg", FORMATO_SIMPLE.get(sin_tildes(m.group(1)), None),
                float(m.group(2).replace(",", ".")), True)

    m = SOLO_PESO.match(t)
    if m:  # "25 Kg"
        return ("kg", None, float(m.group(1).replace(",", ".")), True)

    m = PESO_FIJO_GRAMOS.match(t)
    if m:  # "200 grs." -> envase cerrado, peso fijo
        return ("Units", FORMATO_SIMPLE.get(sin_tildes(m.group(1) or ""), "Bolsa"),
                float(m.group(2)) / 1000.0, False)

    m = CANTIDAD_UNIDADES.match(t)
    if m:  # "12 unid", "Bandeja 30 uni."
        return ("Units", FORMATO_SIMPLE.get(sin_tildes(m.group(1) or ""), None), 0.0, False)

    if plano in FORMATO_SIMPLE:
        return ("Units", FORMATO_SIMPLE[plano], 0.0, False)

    return ("Units", None, 0.0, False)


# ---------------------------------------------------------------------------
# Clasificacion comercial de clientes
# ---------------------------------------------------------------------------
# La planilla de clientes no trae linea comercial. Se deduce del nombre solo
# cuando la evidencia es explicita; el resto va a HORECA, que es la linea
# dominante (95% de cobertura de precios). Es una propuesta revisable, no un
# dato: por eso el informe lista uno a uno los clasificados como Minorista.

PISTAS_MINORISTA = ("MINIMARKET", "MINI MARKET", "MINIMARKED", "ALMACEN",
                    "BOTILLERIA", "MERCADO", "SUPERMERCADO", "VERDULERIA")


def clasifica_linea(nombre, fantasia):
    texto = sin_tildes(f"{nombre} {fantasia}")
    if any(p in texto for p in PISTAS_MINORISTA):
        return "MINOR"
    return "HORECA"


# ===========================================================================
# Analisis y carga
# ===========================================================================

print("=" * 76)
print("IMPORTACION DE DATOS MAESTROS AGROGOOD" +
      ("  [ESCRITURA REAL]" if ESCRIBIR else "  [SIMULACION - no se escribe nada]"))
print("=" * 76)

linea_por_codigo = {
    l.code: l for l in env["agrogood.business.line"].with_context(active_test=False).search([])
}
formatos = {f.name: f for f in env["agrogood.product.format"].search([])}
tipo_rut = env.ref("l10n_cl.it_RUT", raise_if_not_found=False) or \
    env["l10n_latam.identification.type"].search([("name", "=", "RUT")], limit=1)

# ---------------------------------------------------------------------------
# CLIENTES
# ---------------------------------------------------------------------------
filas_cli = leer(RUTA_CLIENTES, "Plantilla_Clientes")
por_rut = defaultdict(list)
sin_rut = []
for f in filas_cli:
    rut = limpio(f[0]).upper().replace(".", "")
    (por_rut[rut] if rut else sin_rut).append(f)

grupos = {r: fs for r, fs in por_rut.items()}
matrices = sum(1 for fs in grupos.values() if len(fs) > 1)
sucursales = sum(len(fs) - 1 for fs in grupos.values() if len(fs) > 1)

print(f"\nCLIENTES  ({len(filas_cli)} filas)")
print(f"  con RUT               : {sum(len(f) for f in grupos.values())}  "
      f"-> {len(grupos)} empresas")
print(f"     de ellas, con varios locales: {matrices} empresas, {sucursales} direcciones hijas")
print(f"  sin RUT               : {len(sin_rut)}  (entran marcados con 'RUT pendiente')")

reparto = Counter()
minoristas = []
for f in filas_cli:
    cod = clasifica_linea(limpio(f[1]), limpio(f[2]))
    reparto[cod] += 1
    if cod == "MINOR":
        minoristas.append(limpio(f[1]))
print(f"\n  Linea comercial propuesta (deducida del nombre, revisable):")
for cod, n in reparto.most_common():
    print(f"     {linea_por_codigo[cod].name if cod in linea_por_codigo else cod:<12} {n:>4}")
print(f"     clasificados como Minorista ({len(minoristas)}):")
for n in minoristas:
    print(f"        - {n[:60]}")

# ---------------------------------------------------------------------------
# PRODUCTOS
# ---------------------------------------------------------------------------
filas_pro = leer(RUTA_PRODUCTOS, "Plantilla_Productos")
print(f"\n\nPRODUCTOS  ({len(filas_pro)} filas)")

resumen_uom = Counter()
variables = fijos = 0
con_formato = Counter()
ejemplos = defaultdict(list)
for f in filas_pro:
    uom, fmt, peso, var = normaliza_unidad(f[10])
    resumen_uom[uom] += 1
    if var:
        variables += 1
    else:
        fijos += 1
    if fmt:
        con_formato[fmt] += 1
    if len(ejemplos[(limpio(f[10]))]) < 1:
        ejemplos[limpio(f[10])] = [(uom, fmt, peso, var)]

print(f"  Unidades tras normalizar (de 35 escrituras a {len(resumen_uom)}):")
for u, n in resumen_uom.most_common():
    print(f"     {u:<10} {n:>4}")
print(f"\n  Peso variable : {variables:>4}  (se factura el peso registrado en picking)")
print(f"  Peso fijo     : {fijos:>4}")
print(f"\n  Formato de presentacion asignado:")
for fmt, n in con_formato.most_common():
    print(f"     {fmt:<10} {n:>4}")

print(f"\n  Traduccion de las escrituras mas ambiguas:")
interesantes = [t for t in ejemplos if re.search(r"\d", t)]
for t in sorted(interesantes)[:14]:
    uom, fmt, peso, var = ejemplos[t][0]
    print(f"     {t!r:<22} -> uom={uom:<7} formato={str(fmt):<8} "
          f"peso_ref={peso:<6.3f} variable={var}")

precios = {"HORECA": 0, "MINOR": 0}
for f in filas_pro:
    if not vacio(f[5]):
        precios["HORECA"] += 1
    if not vacio(f[6]):
        precios["MINOR"] += 1
print(f"\n  Precios a cargar: HORECA={precios['HORECA']}  Minorista={precios['MINOR']}")
print(f"  Sin ningun precio (entran sin tarifa): "
      f"{sum(1 for f in filas_pro if all(vacio(f[i]) for i in (5, 6, 7)))}")
print(f"  Categoria 'MAYORISTA' usada como categoria de producto: "
      f"{sum(1 for f in filas_pro if sin_tildes(limpio(f[2])) == 'MAYORISTA')} productos "
      f"-> se reasignan a 'OTROS PRODUCTOS'")

if not ESCRIBIR:
    print("\n" + "=" * 76)
    print("SIMULACION TERMINADA. No se ha escrito nada en la base de datos.")
    print("Para ejecutar de verdad: AGROGOOD_IMPORT=escribir")
    print("=" * 76)


# ===========================================================================
# ESCRITURA
# ===========================================================================
if ESCRIBIR:
    UOM = {
        "kg": env.ref("uom.product_uom_kgm"),
        "Units": env.ref("uom.product_uom_unit"),
        "Liters": env.ref("uom.product_uom_litre"),
    }
    Categoria, Producto, Socio = (env["product.category"], env["product.template"],
                                  env["res.partner"])

    print("\n\n" + "=" * 76)
    print("ESCRIBIENDO")
    print("=" * 76)

    # --- Categorias --------------------------------------------------------
    raiz = Categoria.search([("name", "=", "Agrogood"), ("parent_id", "=", False)], limit=1) \
        or Categoria.create({"name": "Agrogood"})
    cats = {}
    for f in filas_pro:
        c = limpio(f[2]) or "OTROS PRODUCTOS"
        # 'MAYORISTA' es un canal de venta, no una familia de producto.
        if sin_tildes(c) == "MAYORISTA":
            c = "OTROS PRODUCTOS"
        if c not in cats:
            cats[c] = Categoria.search([("name", "=", c), ("parent_id", "=", raiz.id)], limit=1) \
                or Categoria.create({"name": c, "parent_id": raiz.id})
    print(f"  categorias: {len(cats)} bajo '{raiz.name}'")

    # --- Productos ---------------------------------------------------------
    creados = actualizados = 0
    productos_por_sku = {}
    for f in filas_pro:
        sku = limpio(f[0])
        uom_txt, fmt, peso, variable = normaliza_unidad(f[10])
        cat = limpio(f[2]) or "OTROS PRODUCTOS"
        if sin_tildes(cat) == "MAYORISTA":
            cat = "OTROS PRODUCTOS"
        vals = {
            "name": limpio(f[1]),
            "default_code": sku,
            "categ_id": cats[cat].id,
            "uom_id": UOM[uom_txt].id,
            "uom_po_id": UOM[uom_txt].id,
            "type": "consu",
            "is_storable": True,
            "sale_ok": True,
            "purchase_ok": True,
            # ADR-003: se factura lo entregado, no lo pedido.
            "invoice_policy": "delivery",
            "agrogood_is_variable_weight": variable,
            "agrogood_format_id": formatos[fmt].id if fmt and fmt in formatos else False,
            "agrogood_reference_weight": peso,
            "list_price": 0.0,
        }
        p = Producto.search([("default_code", "=", sku)], limit=1)
        if p:
            p.write(vals); actualizados += 1
        else:
            p = Producto.create(vals); creados += 1
        productos_por_sku[sku] = p
    print(f"  productos : {creados} creados, {actualizados} actualizados")

    # --- Tarifas y precios, usando el propio agrogood_pricing ---------------
    for cod, col in (("HORECA", 5), ("MINOR", 6)):
        linea = linea_por_codigo[cod]
        pl = linea.pricelist_id or env["product.pricelist"].create({
            "name": f"Tarifa {linea.name}", "currency_id": env.company.currency_id.id,
        })
        linea.pricelist_id = pl
        lineas_ver = [
            (0, 0, {"product_tmpl_id": productos_por_sku[limpio(f[0])].id,
                    "price": float(f[col])})
            for f in filas_pro if not vacio(f[col]) and limpio(f[0]) in productos_por_sku
        ]
        ver = env["agrogood.price.version"].create({
            "name": f"Carga inicial {linea.name}",
            "business_line_id": linea.id, "pricelist_id": pl.id,
            "date_start": fields.Date.context_today(env.user),
            "note": "Precios de la planilla de carga masiva.",
            "line_ids": lineas_ver,
        })
        ver.action_apply()
        print(f"  precios   : {linea.name:<10} {len(lineas_ver):>3} en '{pl.name}' (version publicada)")

    # La linea Mayorista no opera hoy: sus 4 precios son casos puntuales.
    may = linea_por_codigo.get("MAYOR")
    if may:
        may.active = False
        print(f"  linea Mayorista archivada (no eliminada: es reversible)")

    # --- Clientes ----------------------------------------------------------
    def vals_socio(f, linea_cod, con_rut):
        v = {
            "name": limpio(f[1]),
            "phone": normaliza_telefono(f[4]),
            "street": limpio(f[5]) or False,
            "city": limpio(f[6]) or False,
            "country_id": env.ref("base.cl").id,
            "customer_rank": 1,
            "agrogood_business_line_id": linea_por_codigo[linea_cod].id,
        }
        if con_rut:
            v["vat"] = con_rut
            if tipo_rut:
                v["l10n_latam_identification_type_id"] = tipo_rut.id
        return v

    n_emp = n_hijos = n_srut = 0
    for rut, fs in grupos.items():
        principal, resto = fs[0], fs[1:]
        cod = clasifica_linea(limpio(principal[1]), limpio(principal[2]))
        madre = Socio.search([("vat", "=", rut)], limit=1)
        vals = vals_socio(principal, cod, rut)
        vals["is_company"] = True
        if madre:
            madre.write(vals)
        else:
            madre = Socio.create(vals); n_emp += 1
        # Varios locales bajo un mismo RUT: la factura va al RUT, el reparto a
        # cada direccion. Por eso son direcciones de entrega, no clientes.
        for f in resto:
            h = vals_socio(f, clasifica_linea(limpio(f[1]), limpio(f[2])), None)
            h.update({"parent_id": madre.id, "type": "delivery"})
            if not Socio.search([("parent_id", "=", madre.id), ("name", "=", h["name"])], limit=1):
                Socio.create(h); n_hijos += 1
    for f in sin_rut:
        cod = clasifica_linea(limpio(f[1]), limpio(f[2]))
        v = vals_socio(f, cod, None)
        v["is_company"] = True
        if not Socio.search([("name", "=", v["name"]),
                             ("agrogood_business_line_id", "!=", False)], limit=1):
            Socio.create(v); n_srut += 1
    print(f"  clientes  : {n_emp} empresas con RUT, {n_hijos} direcciones de entrega, "
          f"{n_srut} sin RUT")

    env.cr.commit()
    print("\n" + "=" * 76)
    print("IMPORTACION CONFIRMADA")
    print("=" * 76)
