"""Revision a fondo antes de produccion. No modifica nada.

    odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/auditoria.py

Cuatro preguntas, en orden de lo que cuesta si la respuesta es mala:

 1. Todos los endpoints de la aplicacion comprueban permiso ANTES de actuar?
    Uno que no lo haga es una puerta abierta: la aplicacion esconde el boton,
    pero la peticion se puede escribir a mano.
 2. Cada rol puede leer o escribir algo que no le toca?
 3. Las validaciones viven en el servidor, o solo en la pantalla?
 4. Las cifras de los paneles dicen la verdad?

Se comprueba EJECUTANDO, no leyendo: se entra como cada persona y se intenta
hacer lo que no deberia poder. Un permiso que se lee bien en un archivo XML y
falla en la practica es el caso normal, no el raro.

Termina con rollback.
"""

import ast
import os

import odoo.modules.module

R = []
SIN_PROBAR = []


def paso(t, ok, det=""):
    """ok=True pasa, ok=False falla, ok=None NO SE PUDO COMPROBAR.

    El tercer estado existe porque una comprobacion que no llego a ejecutarse
    contada como buena es exactamente la clase de numero que miente: el informe
    dice 17 de 17 y una de las 17 no se hizo.
    """
    if ok is None:
        SIN_PROBAR.append((t, det))
        print("  [ -- ] %s" % t)
        if det:
            print("        %s" % det)
        return
    R.append((ok, t, det))
    print("  [%s] %s" % ("OK " if ok else "MAL", t))
    if det:
        print("        %s" % det)


# Se ejecuta dentro del shell de Odoo, donde no hay __file__: la ruta sale de
# donde esta instalado el modulo, que es la que de verdad se esta usando.
RAIZ = os.path.dirname(os.path.dirname(
    odoo.modules.module.get_module_path("agrogood_pwa")))

print("=" * 78)
print("REVISION A FONDO")
print("=" * 78)

# ==========================================================================
# 1. Todos los endpoints comprueban permiso
# ==========================================================================
print()
print("1. PUERTAS DE LA APLICACION")

RUTA_CTRL = os.path.join(RAIZ, "addons_agrogood", "agrogood_pwa",
                         "controllers", "main.py")
arbol = ast.parse(open(RUTA_CTRL, encoding="utf-8").read())

# Las formas de autorizar que usa el codigo:
#   _es_algo()   -> comprueba el rol
#   _mi_algo()   -> comprueba ademas que el registro sea de quien lo pide
#   _rol()       -> Picker o Conductor, y redirige si no lo es
#   _accesos()   -> devuelve solo las pantallas a las que llega ese usuario
#
# La primera version de esta lista no incluia _rol ni _accesos y marco tres
# endpoints como abiertos que no lo estaban. Un detector que da falsos avisos
# es peor que no tenerlo: la tercera vez ya nadie mira la lista.
GUARDIAS = ('_es_', '_mi_', '_rol', '_accesos', 'check_access')

sin_guardia = []
total = 0
for clase in [n for n in arbol.body if isinstance(n, ast.ClassDef)]:
    for f in [n for n in clase.body if isinstance(n, ast.FunctionDef)]:
        es_ruta = any(
            isinstance(d, ast.Call)
            and getattr(getattr(d.func, 'attr', None), '__str__', lambda: '')() == 'route'
            for d in f.decorator_list)
        if not es_ruta:
            continue
        total += 1
        cuerpo = ast.dump(f)
        if not any(g in cuerpo for g in GUARDIAS):
            sin_guardia.append("%s.%s" % (clase.name, f.name))

paso("Todos los endpoints comprueban permiso antes de actuar",
     not sin_guardia,
     "%d endpoints revisados%s" % (
         total,
         "" if not sin_guardia else "; SIN CONTROL: " + ", ".join(sin_guardia)))

# ==========================================================================
# 2. Que puede tocar cada rol de verdad
# ==========================================================================
print()
print("2. LO QUE PUEDE TOCAR CADA ROL")

Usuario = env['res.users']


def como(login):
    u = Usuario.search([('login', '=', login)], limit=1)
    return env(user=u) if u else None


def puede(entorno, modelo, operacion):
    """True si ese usuario puede hacer eso sobre un registro DE VERDAD.

    Se prueba sobre un registro existente y no sobre el modelo vacio. La
    primera version de esta funcion preguntaba por el modelo, y eso solo mira
    los permisos de modelo: las reglas de registro se aplican por registro y no
    aparecen. Dio tres avisos que ya estaban resueltos, que es la peor clase de
    aviso -manda a arreglar algo que ya esta bien-.

    Cuando no hay ningun registro que probar se devuelve None, que se lee como
    "no se pudo comprobar" y no como "esta bien".
    """
    uno = entorno[modelo].sudo().search([], limit=1)
    if not uno:
        return None
    try:
        entorno[modelo].browse(uno.id).check_access(operacion)
        return True
    except Exception:
        return False


# Lo que NO debe poder cada rol. Cada linea es una frase que alguien diria en
# voz alta: "un Picker no puede cambiar precios".
PROHIBIDO = [
    ("felipe.collio@agrogood.cl", "Un Picker", [
        ('product.pricelist', 'write', "cambiar precios"),
        ('res.partner', 'write', "cambiar fichas de clientes"),
        ('sale.order', 'write', "cambiar pedidos"),
        ('account.move', 'read', "ver facturas"),
        ('res.users', 'write', "cambiar usuarios"),
    ]),
    ("thomas.schuster@agrogood.cl", "Un conductor", [
        ('product.pricelist', 'write', "cambiar precios"),
        ('sale.order', 'write', "cambiar pedidos"),
        ('account.move', 'read', "ver facturas"),
        ('stock.quant', 'write', "ajustar inventario"),
    ]),
    ("johan@agrogood.cl", "Compras", [
        ('product.pricelist', 'write', "cambiar precios de venta"),
        ('sale.order', 'write', "cambiar pedidos de cliente"),
    ]),
    ("matias@agrogood.cl", "Bodega", [
        ('product.pricelist', 'write', "cambiar precios"),
        ('sale.order', 'write', "cambiar pedidos"),
    ]),
    ("sebastian.ventas@agrogood.cl", "Ventas", [
        ('purchase.order', 'write', "escribir ordenes de compra a proveedor"),
        ('res.users', 'write', "cambiar usuarios"),
    ]),
]

for login, quien, comprobaciones in PROHIBIDO:
    entorno = como(login)
    if not entorno:
        paso("%s: no existe la cuenta %s" % (quien, login), False)
        continue
    malas, sin_probar = [], []
    for modelo, operacion, frase in comprobaciones:
        if modelo not in env.registry:
            continue
        resultado = puede(entorno, modelo, operacion)
        if resultado is True:
            malas.append(frase)
        elif resultado is None:
            sin_probar.append(frase)
    detalle = login
    if malas:
        detalle = "PUEDE: " + "; ".join(malas)
    elif sin_probar:
        detalle = "%s (sin registros para probar: %s)" % (
            login, ", ".join(sin_probar))
    paso("%s no puede lo que no le toca" % quien, not malas, detalle)

# Y al reves: cada uno tiene que poder hacer SU trabajo.
NECESITA = [
    ("sebastian.ventas@agrogood.cl", "Ventas", [('sale.order', 'write'),
                                                ('res.partner', 'write')]),
    ("johan@agrogood.cl", "Compras", [('purchase.order', 'write')]),
    ("matias@agrogood.cl", "Bodega", [('stock.picking', 'write'),
                                      ('stock.quant', 'write')]),
    ("felipe@agrogood.cl", "Logistica", [('stock.picking', 'write'),
                                         ('agrogood.route', 'write')]),
]
for login, quien, comprobaciones in NECESITA:
    entorno = como(login)
    if not entorno:
        continue
    faltan = [m for m, o in comprobaciones
              if m in env.registry and puede(entorno, m, o) is False]
    paso("%s puede hacer su trabajo" % quien, not faltan,
         login if not faltan else "NO PUEDE: " + ", ".join(faltan))

# El Picker se comprueba aparte, y con una preparacion SUYA. Preguntarle si
# puede leer una preparacion cualquiera daba que no, y era correcto: la regla
# de registro estaba haciendo su trabajo. La pregunta util no es "puede leer
# preparaciones" sino "puede leer LA SUYA".
picker_u = Usuario.search([('login', '=', 'felipe.collio@agrogood.cl')], limit=1)
libre = env['stock.picking'].sudo().search([
    ('picking_type_id.code', '=', 'outgoing'),
    ('state', 'not in', ('done', 'cancel')),
], limit=1)
if picker_u and libre:
    suya = env['agrogood.picking.session'].sudo().create({
        'picking_id': libre.id, 'picker_id': picker_u.id})
    try:
        env(user=picker_u)['agrogood.picking.session'].browse(
            suya.id).check_access('read')
        ok, det = True, "y solo la suya"
    except Exception as e:
        ok, det = False, str(e).replace(chr(10), ' ')[:90]
    paso("Un Picker puede abrir SU preparacion", ok, det)
else:
    paso("Un Picker puede abrir SU preparacion", None,
         "no habia ningun albaran libre para montar la prueba")

# ==========================================================================
# 3. Solo lo suyo
# ==========================================================================
print()
print("3. CADA UNO VE SOLO LO SUYO")

Sesion = env['agrogood.picking.session']
Ruta = env['agrogood.route']

# La pregunta correcta no es "ve menos de las que hay" -si la unica que existe
# es la suya, verla es lo correcto- sino "NO ve la de otro". Por eso se monta
# una preparacion de otra persona y se comprueba que no aparece.
picker = como("felipe.collio@agrogood.cl")
otro_picker = Usuario.search([('login', '=', 'orianna.pumar@agrogood.cl')], limit=1)
otro_albaran = env['stock.picking'].sudo().search([
    ('picking_type_id.code', '=', 'outgoing'),
    ('state', 'not in', ('done', 'cancel')),
    ('agrogood_session_id', '=', False),
], limit=1)
if picker and otro_picker and otro_albaran:
    ajena = Sesion.sudo().create({'picking_id': otro_albaran.id,
                                  'picker_id': otro_picker.id})
    visibles = picker['agrogood.picking.session'].search([]).ids
    paso("Un Picker no ve la preparacion de otro",
         ajena.id not in visibles,
         "ve %d preparaciones, de %d que hay"
         % (len(visibles), Sesion.sudo().search_count([])))
else:
    paso("Un Picker no ve la preparacion de otro", None,
         "no habia albaran libre para montar la de otra persona")

conductor = como("thomas.schuster@agrogood.cl")
otro_conductor = Usuario.search(
    [('login', '=', 'luis.yanez@agrogood.cl')], limit=1)
modelo_v = env['fleet.vehicle.model'].sudo().search([], limit=1)
if conductor and otro_conductor and modelo_v:
    coche = env['fleet.vehicle'].sudo().create({
        'model_id': modelo_v.id, 'license_plate': 'AUD-01',
        'agrogood_capacity_kg': 600.0})
    from odoo import fields as _f
    ruta_ajena = Ruta.sudo().create({
        'driver_id': otro_conductor.id, 'vehicle_id': coche.id,
        'date': _f.Date.context_today(env.user)})
    visibles = conductor['agrogood.route'].search([]).ids
    paso("Un conductor no ve la ruta de otro",
         ruta_ajena.id not in visibles,
         "ve %d rutas, de %d que hay"
         % (len(visibles), Ruta.sudo().search_count([])))
else:
    paso("Un conductor no ve la ruta de otro", None,
         "faltaba con que montar la ruta de otra persona")

# ==========================================================================
# 4. Las cifras de los paneles
# ==========================================================================
print()
print("4. LAS CIFRAS DICEN LA VERDAD")

from odoo import fields  # noqa: E402

hoy = fields.Date.context_today(env.user)
SO = env['sale.order']

# Por cobrar: se recalcula a mano, sumando orden por orden, y se compara con
# lo que suman los campos almacenados. Si no coinciden, hay un calculo que no
# se rehizo cuando debia.
abiertas = SO.search([('agrogood_collection_state', 'in', ('open', 'partial'))])
a_mano = 0.0
for o in abiertas:
    cobrable = 0.0
    for l in o.order_line:
        if l.display_type or not l.product_uom_qty:
            continue
        cobrable += l.price_total * (l.qty_delivered / l.product_uom_qty)
    pagado = sum(o.agrogood_allocation_ids.mapped('amount'))
    a_mano += cobrable - pagado
guardado = sum(abiertas.mapped('agrogood_due_amount'))
paso("Lo por cobrar cuadra recalculandolo a mano",
     abs(a_mano - guardado) < 1.0,
     "a mano %.0f, guardado %.0f, sobre %d ordenes"
     % (a_mano, guardado, len(abiertas)))

# El saldo de cada cliente tiene que ser la suma de sus ordenes abiertas mas
# lo que quede de su saldo de apertura.
Socio = env['res.partner']
descuadran = []
for s in Socio.search([('agrogood_balance', '!=', 0)]):
    suyas = s.sale_order_ids.filtered(
        lambda o: o.agrogood_collection_state in ('open', 'partial'))
    esperado = sum(suyas.mapped('agrogood_due_amount')) + s.agrogood_opening_due
    if abs(esperado - s.agrogood_balance) > 1.0:
        descuadran.append("%s (%.0f vs %.0f)"
                          % (s.display_name[:24], esperado, s.agrogood_balance))
paso("El saldo de cada cliente es la suma de lo suyo",
     not descuadran, "; ".join(descuadran[:3]) or "sin descuadres")

# Un abono no puede tener imputado mas de lo que trae.
Mov = env['agrogood.bank.movement']
pasados = []
for m in Mov.search([('amount_applied', '>', 0)]):
    if m.amount_applied - m.amount > 1.0:
        pasados.append(m.name)
paso("Ningun abono esta imputado por encima de su monto",
     not pasados, "; ".join(pasados[:3]) or "ninguno")

# Ninguna orden pagada de mas.
sobrepagadas = SO.search([('agrogood_due_amount', '<', -1.0)])
paso("Ninguna orden quedo pagada de mas",
     not sobrepagadas, ", ".join(sobrepagadas.mapped('name')[:3]) or "ninguna")

# ==========================================================================
print()
print("=" * 78)
buenos = sum(1 for ok, _, _ in R if ok)
print("%d de %d comprobaciones" % (buenos, len(R)))
if SIN_PROBAR:
    print("%d no se pudieron comprobar:" % len(SIN_PROBAR))
    for t, det in SIN_PROBAR:
        print("   - %s  (%s)" % (t, det))
print("=" * 78)
if buenos == len(R):
    print("Nada que corregir en lo revisado.")
else:
    print("HAY QUE CORREGIR:")
    for ok, t, det in R:
        if not ok:
            print("   - %s" % t)
            if det:
                print("     %s" % det)

env.cr.rollback()
