"""Crea las cuentas del equipo de bodega y reparto.

    odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/crear_equipo.py

Por defecto SOLO INFORMA. Para crear: AGROGOOD_EQUIPO=crear

NO pone contrasenas. Se crean las cuentas y despues Victor le pone la clave a
cada una desde Ajustes > Usuarios > (el usuario) > Accion > Cambiar contrasena.
Que las claves las ponga una persona y no un script es a proposito: una clave
escrita en un archivo del repositorio deja de ser una clave.

CADA CUENTA QUEDA CON DOS GRUPOS Y NADA MAS

Un Picker y un conductor no necesitan ningun grupo estandar de Odoo: todo lo
que hacen pasa por la aplicacion, que autoriza con la identidad real y ejecuta
elevado. Por eso se les asigna EXACTAMENTE `base.group_user` mas su rol de
Agrogood, pisando lo que la plantilla de usuario nuevo hubiera anadido.

Hace falta pisarlo: Odoo suma a esa plantilla un grupo de cada aplicacion que
se instala, y asi es como el conductor de demostracion acabo con 22 grupos,
entre ellos administrar empleados, proyectos y vacaciones. Nadie se lo dio: se
lo dieron las instalaciones, una a una, sin que nadie lo pidiera.
"""

import os

CREAR = os.environ.get("AGROGOOD_EQUIPO") == "crear"

# nombre, correo, y si prepara, si conduce
EQUIPO = [
    ("Felipe Collio",     "felipe.collio@agrogood.cl",     True,  False),
    ("Orianna Pumar",     "orianna.pumar@agrogood.cl",     True,  False),
    ("Thomas Schuster",   "thomas.schuster@agrogood.cl",   True,  True),
    ("Earvin Juarez",     "earvin.juarez@agrogood.cl",     True,  True),
    ("Luis Yanez",        "luis.yanez@agrogood.cl",        True,  True),
    ("Fernando Figueroa", "fernando.figueroa@agrogood.cl", True,  False),
    ("Felipe Fuentes",    "felipe.fuentes@agrogood.cl",    True,  True),
]

# Ya existe un `felipe@agrogood.cl` que es Felipe Labrana, de Logistica. Por eso
# todas las cuentas nuevas llevan nombre y apellido: con dos Felipes en bodega,
# un correo de solo nombre es el que se equivoca.

Usuario = env['res.users']
interno = env.ref('base.group_user')
picker = env.ref('agrogood_base.group_agrogood_picker')
conductor = env.ref('agrogood_base.group_agrogood_driver')


def esperados():
    """Los grupos que una cuenta minima tiene por fuerza.

    `base.group_user` arrastra los suyos -caracteristicas tecnicas, lotes,
    tarifas, multimoneda- y Odoo los vuelve a poner solo. No son permisos para
    administrar nada; contarlos como sobrantes haria que el informe gritara
    todos los dias por algo correcto, y un aviso que siempre suena deja de
    leerse.
    """
    todos = interno | picker | conductor
    while True:
        mas = todos.implied_ids - todos
        if not mas:
            return todos
        todos |= mas

print("=" * 78)
print("EQUIPO DE BODEGA Y REPARTO" +
      ("  [CREANDO]" if CREAR else "  [SOLO INFORME]"))
print("=" * 78)

nuevos, existentes = [], []
for nombre, correo, prepara, conduce in EQUIPO:
    ya = Usuario.with_context(active_test=False).search(
        [('login', '=', correo)], limit=1)
    (existentes if ya else nuevos).append((nombre, correo, prepara, conduce, ya))

print()
print("%-22s %-32s %s" % ("QUIEN", "CORREO", "HACE"))
for nombre, correo, prepara, conduce, ya in nuevos + existentes:
    trabajos = " y ".join(
        [t for t, si in (("prepara", prepara), ("reparte", conduce)) if si])
    print("%-22s %-32s %-18s %s"
          % (nombre, correo, trabajos, "YA EXISTE" if ya else ""))

print()
print("Cuentas por crear: %d   ya existentes: %d" % (len(nuevos), len(existentes)))

# --- Yerendi -------------------------------------------------------------
yere = Usuario.search([('login', '=', 'yere@agrogood.cl')], limit=1)
if yere and yere.name != "Yerendi Zambrano":
    print()
    print("Ademas: la ficha de %s se completa a 'Yerendi Zambrano'." % yere.name)

# --- lo que ya esta de mas ----------------------------------------------
demos = Usuario.search([('login', 'in', ('picker.demo@agrogood.cl',
                                         'chofer.demo@agrogood.cl'))])
if demos:
    print()
    print("-" * 78)
    print("LAS CUENTAS DE DEMOSTRACION TIENEN PERMISOS DE MAS")
    minimo = esperados()
    for u in demos:
        sobra = u.groups_id - minimo
        graves = sobra.filtered(
            lambda g: 'manager' in (g.name or '').lower()
            or 'dminist' in (g.name or ''))
        print("  %-26s %d grupos, %d de mas" % (u.login, len(u.groups_id), len(sobra)))
        for g in graves.sorted(lambda x: x.full_name)[:6]:
            print("       %s" % g.full_name)
    print("  Nadie se los dio: se los dieron las instalaciones de aplicaciones.")
    print("  Se limpian con tools/limpiar_permisos_sobrantes.py")

if not CREAR:
    print()
    print("=" * 78)
    print("SOLO INFORME. No se ha creado ninguna cuenta.")
    print("Para crearlas: AGROGOOD_EQUIPO=crear")
    print("=" * 78)
else:
    creados = []
    for nombre, correo, prepara, conduce, ya in nuevos:
        roles = interno
        if prepara:
            roles |= picker
        if conduce:
            roles |= conductor
        u = Usuario.create({'name': nombre, 'login': correo})
        # Se PISA la lista entera en vez de anadir. Lo que la plantilla de
        # usuario nuevo trae de las aplicaciones instaladas no lo pidio nadie,
        # y con un solo comando se queda solo lo que hace falta.
        u.groups_id = [(6, 0, roles.ids)]
        creados.append(u)

    if yere and yere.name != "Yerendi Zambrano":
        yere.name = "Yerendi Zambrano"
        if yere.partner_id:
            yere.partner_id.name = "Yerendi Zambrano"

    env.cr.commit()

    print()
    print("-" * 78)
    print("CREADAS (%d). Comprobacion de que quedaron con lo justo:" % len(creados))
    minimo = esperados()
    for u in creados:
        sobra = u.groups_id - minimo
        print("  %-32s %d grupos%s"
              % (u.login, len(u.groups_id),
                 "   OJO: %d de mas" % len(sobra) if sobra
                 else "   solo lo que necesita"))
        for g in sobra.sorted(lambda x: x.full_name):
            print("       de mas: %s" % g.full_name)
    print()
    print("=" * 78)
    print("FALTA PONERLES CONTRASENA. Una por una, desde el escritorio:")
    print("   Ajustes > Usuarios y companias > Usuarios > (el usuario)")
    print("   > Accion > Cambiar contrasena")
    print()
    print("Las claves las pone una persona, no este script: una clave escrita")
    print("en un archivo del repositorio deja de ser una clave.")
    print("=" * 78)
