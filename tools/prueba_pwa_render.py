"""Renderiza de verdad cada pantalla de la webapp, por rol.

    odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/prueba_pwa_render.py

Las otras pruebas comprueban la logica: quien puede, que se guarda, que cuadra.
Ninguna renderiza la plantilla, y por eso el 500 de la semana pasada -una
plantilla que pedia un dato que el controlador ya no ponia- paso todas las
pruebas y reventaba en la cara del usuario.

Esto llama a los mismos metodos de ruta que sirven las paginas, con el mismo
contexto que arman, y renderiza el HTML. No comprueba que se vea bien -eso se
mira en el navegador- sino que la plantilla y el controlador siguen hablando
el mismo idioma. Es barato y ataja justo el fallo que no se ve venir.

Termina con rollback: no deja nada.
"""

import werkzeug

from odoo.addons.agrogood_pwa.controllers import main as C

R = []


def paso(t, ok, det=""):
    R.append(ok)
    print("  [%s] %s" % ("OK " if ok else "FALLA", t))
    if det:
        print("        %s" % det)


class Respuesta(object):
    """Lo justo de una respuesta HTTP para saber que se rindio sin reventar."""

    def __init__(self, tipo, dato):
        self.tipo = tipo          # 'render' | 'redirect'
        self.dato = dato          # html renderizado, o url


class PeticionFalsa(object):
    """Un request de mentira que renderiza la plantilla como lo haria el real.

    render() no se limita a anotar la llamada: renderiza el QWeb con el mismo
    contexto que arma el controlador. Ahi es donde salta el desajuste entre
    plantilla y datos, que es todo el punto de esta prueba.

    Devuelve una respuesta werkzeug de verdad -y guarda aparte lo que rindio-
    porque el decorador @http.route valida el tipo de lo que retorna el metodo,
    y una respuesta inventada la rechaza antes de que se pueda mirar.
    """

    def __init__(self, entorno):
        self.env = entorno
        self.ultimo = None

    def render(self, plantilla, contexto=None):
        html = str(self.env['ir.qweb']._render(plantilla, contexto or {}))
        self.ultimo = Respuesta('render', html)
        return werkzeug.wrappers.Response(html, content_type='text/html')

    def redirect(self, url, code=303):
        self.ultimo = Respuesta('redirect', url)
        return werkzeug.utils.redirect(url, code)


def visitar(login, descripcion, fn, *args):
    """Corre un metodo de ruta con el usuario dado y comprueba que rinde algo."""
    usuario = env['res.users'].search([('login', '=', login)], limit=1)
    if not usuario:
        paso("%s (%s)" % (descripcion, login), False, "no existe el usuario")
        return None
    peticion = PeticionFalsa(env(user=usuario))
    C.request = peticion
    try:
        fn(*args)
    except Exception as e:
        paso("%s (%s)" % (descripcion, login), False,
             "%s: %s" % (type(e).__name__, str(e).replace(chr(10), " ")[:80]))
        return None
    resp = peticion.ultimo
    ok = resp is not None
    detalle = ""
    if ok and resp.tipo == 'render':
        # Una pagina vacia o de dos lineas no es un render valido: es un error
        # que no llego a lanzarse.
        ok = len(resp.dato) > 200
        detalle = "%d caracteres de HTML" % len(resp.dato)
    elif ok:
        detalle = "redirige a %s" % resp.dato
    paso("%s (%s)" % (descripcion, login), ok, detalle)
    return resp


print("=" * 74)
print("LAS PANTALLAS RENDERIZAN")
print("=" * 74)

pwa = C.AgrogoodPwa()
ventas = C.AgrogoodVentas()
bodega = C.AgrogoodBodega()
logistica = C.AgrogoodLogistica()
compras = C.AgrogoodCompras()
direccion = C.AgrogoodDireccion()
caja = C.AgrogoodCaja()
cobranza = C.AgrogoodCobranza()

print()
print("LA ENTRADA")
visitar('victor@agrogood.cl', "app: el menu de quien tiene varios roles", pwa.app)
visitar('picker.demo@agrogood.cl', "app: un solo rol redirige directo", pwa.app)
visitar('victor@agrogood.cl', "tablero: los accesos por area", pwa.tablero)

print()
print("CADA AREA")
visitar('picker.demo@agrogood.cl', "picker: sus preparaciones", pwa.picker_home)
visitar('chofer.demo@agrogood.cl', "conductor: su ruta", pwa.driver_home)
visitar('sebastian.ventas@agrogood.cl', "ventas: tomar pedido", ventas.ventas_home)
visitar('matias@agrogood.cl', "bodega: recepciones", bodega.bodega_home)
visitar('matias@agrogood.cl', "bodega: inventario", bodega.bodega_inventario)
visitar('felipe@agrogood.cl', "logistica: asignar y rutas", logistica.logistica_home)
visitar('johan@agrogood.cl', "compras: la pizarra", compras.compras_home)
visitar('victor@agrogood.cl', "direccion: el panel", direccion.direccion_home)
visitar('johan@agrogood.cl', "caja: anotar gasto", caja.caja_home)
visitar('victor@agrogood.cl', "cobranza: por cobrar", cobranza.cobranza_home)

print()
print("=" * 74)
print("%d de %d pantallas renderizan" % (sum(1 for x in R if x), len(R)))
print("=" * 74)
print("La webapp se sirve entera." if all(R)
      else "HAY PANTALLAS QUE REVIENTAN. Revisar arriba.")

env.cr.rollback()
