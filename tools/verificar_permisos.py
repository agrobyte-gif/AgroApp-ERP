"""Crea los usuarios de Agrogood y comprueba la matriz de permisos ejecutando.

Se ejecuta dentro del shell de Odoo:

    odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/verificar_permisos.py

Cada comprobacion se hace con `with_user()`, de modo que la ORM aplica los
derechos de acceso y las reglas de registro reales. Una matriz declarada en un
XML no prueba nada; esto si.

Los usuarios se crean SIN contrasena: no pueden iniciar sesion hasta que alguien
les envie la invitacion desde Ajustes. Es deliberado, para que crear la
estructura no abra accesos.

Por defecto simula. Para crear los usuarios: AGROGOOD_USUARIOS=crear
"""

import os

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError

CREAR = os.environ.get("AGROGOOD_USUARIOS") == "crear"

# Convencion de login. Si Agrogood usa otro dominio, se cambia aqui y se
# vuelve a ejecutar: el script busca por login antes de crear.
DOMINIO = "agrogood.cl"

PERSONAS = [
    ("Victor Hermosilla",  "victor",           "group_agrogood_general_admin"),
    ("Sebastian Lara",     "sebastian.tecnico", "group_agrogood_technical_admin"),
    ("Sebastian Lara",     "sebastian.ventas",  "group_agrogood_sales"),
    ("Yere",               "yere",              "group_agrogood_sales"),
    ("Felipe Labrana",     "felipe",            "group_agrogood_logistics_manager"),
    ("Matias Lobasso",     "matias",            "group_agrogood_warehouse"),
    ("Johan Molina",       "johan",             "group_agrogood_purchase"),
]

print("=" * 78)
print("USUARIOS Y MATRIZ DE PERMISOS" +
      ("  [CREANDO]" if CREAR else "  [SIMULACION]"))
print("=" * 78)

Usuario = env["res.users"]
usuarios = {}

for nombre, login, grupo_xml in PERSONAS:
    login_full = f"{login}@{DOMINIO}"
    u = Usuario.with_context(active_test=False).search([("login", "=", login_full)], limit=1)
    grupo = env.ref(f"agrogood_base.{grupo_xml}")
    if u:
        estado = "ya existia"
    elif CREAR:
        u = Usuario.create({
            "name": nombre,
            "login": login_full,
            # Sin password: el usuario no puede entrar hasta que se le invite.
            "groups_id": [(6, 0, [env.ref("base.group_user").id, grupo.id])],
        })
        estado = "creado"
    else:
        estado = "se crearia"
    usuarios[login] = u
    print(f"  {nombre:<20} {login_full:<28} {grupo.name:<24} {estado}")

if CREAR:
    # Confirmar antes de probar. Las pruebas usan savepoints, que revierten solo
    # lo que escribe cada comprobacion sin arrastrarse a los usuarios.
    env.cr.commit()

if not CREAR and not all(usuarios.values()):
    print("\nSIMULACION. Para crear: AGROGOOD_USUARIOS=crear")
else:
    # -----------------------------------------------------------------------
    # Matriz de permisos
    # -----------------------------------------------------------------------
    # Cada prueba es (etiqueta, funcion). La funcion se ejecuta con la
    # identidad del usuario; si lanza AccessError, el acceso esta denegado.

    socio = env["res.partner"].search([("agrogood_business_line_id", "!=", False)], limit=1)
    producto = env["product.template"].search([("default_code", "!=", False)], limit=1)

    def leer_clientes(u):
        env["res.partner"].with_user(u).search([], limit=1).read(["name"])

    def crear_pedido(u):
        env["sale.order"].with_user(u).create({"partner_id": socio.id})

    def cambiar_precio(u):
        env["agrogood.price.version"].with_user(u).create({
            "name": "PRUEBA", "business_line_id": env.ref("agrogood_base.business_line_horeca").id,
            "pricelist_id": env.ref("agrogood_base.business_line_horeca").pricelist_id.id,
            "date_start": fields.Date.context_today(u),
        })

    def crear_orden_compra(u):
        env["purchase.order"].with_user(u).create({"partner_id": socio.id})

    def ver_inventario(u):
        env["stock.quant"].with_user(u).search([], limit=1).read(["quantity"])

    def ajustar_inventario(u):
        env["stock.scrap"].with_user(u).create({
            "product_id": producto.product_variant_id.id, "scrap_qty": 1.0,
        })

    def ver_asientos(u):
        env["account.move"].with_user(u).search([], limit=1).read(["name"])

    def crear_factura(u):
        env["account.move"].with_user(u).create({
            "move_type": "out_invoice", "partner_id": socio.id,
        })

    def tocar_ajustes(u):
        env["ir.config_parameter"].with_user(u).create({
            "key": "agrogood.prueba.permisos", "value": "1",
        })

    def crear_usuario(u):
        env["res.users"].with_user(u).create({
            "name": "PRUEBA", "login": "prueba.permisos@example.invalid",
        })

    PRUEBAS = [
        ("Ver clientes",        leer_clientes),
        ("Crear pedido",        crear_pedido),
        ("Cambiar precios",     cambiar_precio),
        ("Crear orden compra",  crear_orden_compra),
        ("Ver inventario",      ver_inventario),
        ("Registrar merma",     ajustar_inventario),
        ("Ver contabilidad",    ver_asientos),
        ("Crear factura",       crear_factura),
        ("Tocar Ajustes",       tocar_ajustes),
        ("Crear usuarios",      crear_usuario),
    ]

    ROLES = [("victor", "Admin Gral"), ("sebastian.tecnico", "Admin Tec"),
             ("sebastian.ventas", "Ventas"), ("felipe", "Logistica"),
             ("matias", "Bodega"), ("johan", "Compras")]

    print("\n" + "=" * 78)
    print("MATRIZ REAL  (+ permitido   -  denegado)")
    print("=" * 78)
    print(f"  {'':<20}" + "".join(f"{et:<12}" for _, et in ROLES))

    class _Deshacer(Exception):
        """Se lanza al final de cada prueba para revertir su savepoint."""

    def probar(fn, u):
        """Devuelve '+' permitido, '-' denegado, '?' error ajeno a los permisos.

        Se usa un savepoint por comprobacion: revierte lo que la prueba escriba
        sin tocar nada de lo anterior. Un rollback completo borraria los propios
        usuarios y las pruebas siguientes mediran un usuario inexistente.

        Los errores que no son de acceso NO se cuentan como permitido. Solo
        ValidationError y UserError lo son, y por un motivo concreto: para
        llegar a ellos la ORM ya dejo pasar el control de acceso, que es
        exactamente lo que se esta midiendo. Cualquier otra excepcion se marca
        con '?' para que se vea, en lugar de aprobar por accidente.
        """
        try:
            with env.cr.savepoint():
                fn(u)
                raise _Deshacer
        except _Deshacer:
            return "+"
        except AccessError:
            return "-"
        except (ValidationError, UserError):
            return "+"
        except Exception as e:
            print(f"       [?] {type(e).__name__}: {str(e)[:70]}")
            return "?"

    resultados = {}
    for etiqueta, fn in PRUEBAS:
        fila = f"  {etiqueta:<20}"
        for login, _ in ROLES:
            ok = probar(fn, usuarios[login])
            resultados[(etiqueta, login)] = ok
            fila += f"{ok:<12}"
        print(fila)

    # -----------------------------------------------------------------------
    # Comprobaciones que deben cumplirse si o si
    # -----------------------------------------------------------------------
    ESPERADO = [
        ("Tocar Ajustes",      "victor",           "-", "El Admin General dirige, no configura (H7)"),
        ("Tocar Ajustes",      "sebastian.tecnico", "+", "Es el responsable tecnico"),
        ("Tocar Ajustes",      "sebastian.ventas",  "-", "El usuario de ventas no toca configuracion"),
        ("Tocar Ajustes",      "matias",           "-", "Bodega no toca configuracion"),
        ("Cambiar precios",    "sebastian.ventas",  "+", "Ventas fija los precios"),
        ("Cambiar precios",    "matias",           "-", "Bodega no fija precios"),
        ("Cambiar precios",    "felipe",           "-", "Logistica no fija precios"),
        ("Crear orden compra", "johan",            "+", "Compras compra"),
        ("Crear orden compra", "matias",           "-", "Bodega recibe, no compra"),
        ("Crear pedido",       "matias",           "-", "Bodega no crea pedidos"),
        ("Crear pedido",       "johan",            "-", "Compras no crea pedidos de venta"),
        ("Registrar merma",    "matias",           "+", "Bodega controla las mermas"),
        ("Crear factura",      "sebastian.ventas",  "+", "Ventas factura"),
        ("Crear factura",      "felipe",           "-", "Logistica no factura"),
        ("Crear usuarios",     "sebastian.ventas",  "-", "Solo el rol tecnico gestiona usuarios"),
        # Desde que la valoracion de inventario es automatica, cada movimiento
        # de stock genera un asiento con el costo real. Ver contabilidad hoy es
        # ver a que precio se compra y que margen deja cada cliente, asi que
        # deja de ser un permiso inofensivo.
        ("Ver contabilidad",   "matias",           "-", "Bodega no ve costos ni margenes"),
        ("Ver contabilidad",   "felipe",           "-", "Logistica no ve costos ni margenes"),
        ("Ver contabilidad",   "sebastian.ventas",  "+", "Ventas factura, necesita verla"),
        ("Ver contabilidad",   "johan",            "+", "Compras ve las facturas de proveedor"),
    ]

    print("\n" + "=" * 78)
    print("COMPROBACIONES OBLIGATORIAS")
    print("=" * 78)
    fallos = 0
    for etiqueta, login, esperado, motivo in ESPERADO:
        real = resultados.get((etiqueta, login), "?")
        ok = real == esperado
        if not ok:
            fallos += 1
        marca = "OK  " if ok else "FALLA"
        print(f"  {marca} {etiqueta:<20} {login:<20} esperado={esperado} real={real}   {motivo}")

    # ------------------------------------------------------------------
    # El molde del que nacen los usuarios nuevos
    # ------------------------------------------------------------------
    # Odoo anade el grupo de administrador de cada aplicacion al usuario
    # plantilla al instalarla. El efecto no se ve ese dia: se ve el dia que
    # se da de alta a un conductor y nace pudiendo cambiar precios. Se
    # comprueba aqui porque es justo el permiso que nadie audita, ya que
    # nadie llego a pedirlo.
    plantilla = env.ref("base.default_user", raise_if_not_found=False)
    interno = env.ref("base.group_user")
    heredados = ((plantilla.groups_id - interno - interno.implied_ids)
                 if plantilla else env["res.groups"])
    limpio = not heredados
    if not limpio:
        fallos += 1
    print(f"  {'OK  ' if limpio else 'FALLA'} {'Usuario plantilla':<20} "
          f"{'(usuarios nuevos)':<20} esperado=0 real={len(heredados)}   "
          f"Un usuario nuevo debe nacer sin permisos heredados")
    for g in sorted(heredados, key=lambda x: x.full_name)[:8]:
        print(f"         hereda: {g.full_name}")
    if not limpio:
        print("         Corregir con AGROGOOD_PERMISOS=limpiar sobre "
              "tools/limpiar_permisos_sobrantes.py")

    total = len(ESPERADO) + 1
    print("\n" + "=" * 78)
    print(f"RESULTADO: {total - fallos}/{total} comprobaciones correctas"
          + ("" if fallos else "   -  matriz probada"))
    print("=" * 78)
