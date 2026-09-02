"""Quita los permisos que Odoo reparte solo al instalar aplicaciones.

    AGROGOOD_PERMISOS=limpiar odoo-bin shell -c config/odoo.conf -d agrogood_dev \
        --no-http < tools/limpiar_permisos_sobrantes.py

SE EJECUTA DESPUES DE INSTALAR CUALQUIER APLICACION. No es un arreglo de una
vez: es parte del procedimiento de instalar algo.

El motivo es un comportamiento de Odoo que sorprende a casi todo el mundo:
al instalar una aplicacion, su grupo de ADMINISTRADOR se anade al usuario
plantilla `base.default_user`, que es el molde del que nacen los usuarios
nuevos. Instalar seis aplicaciones dejo la plantilla con administrador de
Ventas, Inventario, Proyectos, Punto de Venta, Gastos y Vacaciones.

La consecuencia no se ve el dia de la instalacion, sino el dia que se da de
alta a un conductor: nace pudiendo cambiar precios y ajustar stock. Y nadie lo
nota, porque el permiso no se pidio, se heredo.

Aqui se hacen dos cosas:

1. La plantilla vuelve a tener SOLO `Usuario interno`. Los permisos de un
   usuario deben venir de su rol de Agrogood, que es donde estan escritos y
   donde se pueden revisar. Un permiso que llega por herencia silenciosa no se
   audita porque nadie sabe que existe.

2. Se retiran los grupos de dos aplicaciones que estan instaladas pero que
   nadie usa, y que estaban dando acceso de lectura a la contabilidad a todo
   el mundo, Picker y conductor incluidos. Eso importa mas desde que la
   valoracion de inventario es automatica: cada movimiento de stock genera un
   asiento con el costo real de la mercaderia. Leer contabilidad hoy es ver a
   que precio compra Johan y que margen deja cada cliente.

Por defecto informa. Escribe con AGROGOOD_PERMISOS=limpiar.
"""

import os

APLICAR = os.environ.get("AGROGOOD_PERMISOS") == "limpiar"

# Aplicaciones instaladas que Agrogood no usa. Los grupos se retiran; el modulo
# NO se desinstala aqui: desinstalar borra tablas y es una decision de negocio,
# no de limpieza.
#
# El orden importa: primero el administrador y luego el usuario. Al reves, Odoo
# vuelve a poner el de usuario porque el de administrador lo implica.
# Punto de Venta estuvo aqui: los nueve usuarios eran administradores de una
# caja que no existe. Se confirmo que Agrogood no vende en mostrador y el
# modulo se desinstalo entero (nueve modulos, cero datos que perder), asi que
# ya no hay grupos que retirar. Si algun dia abren local y se reinstala,
# volveran a aparecer y habra que anadirlo de nuevo aqui.
RETIRAR_A_TODOS = []

# De Gastos se conserva un aprobador: si algun dia reembolsan combustible o
# peajes a los conductores, tiene que haber alguien que lo apruebe. Lo que no
# tiene sentido es que lo aprueben los diez.
RETIRAR_SALVO = [
    ("Gastos", [
        "hr_expense.group_hr_expense_manager",
        "hr_expense.group_hr_expense_user",
        "hr_expense.group_hr_expense_team_approver",
    ], ["victor@agrogood.cl"],
     "Nadie ha registrado un gasto todavia. Se deja un aprobador."),

    # Al crear las cuentas del equipo de bodega aparecio que el conductor de
    # demostracion podia administrar empleados, proyectos y vacaciones. No se
    # lo dio nadie: Odoo suma a la plantilla de usuario nuevo un grupo de cada
    # aplicacion que se instala, y esa plantilla se copia en cada alta.
    #
    # Se retiran a todos menos a Victor. Nadie en Agrogood administra proyectos
    # desde Odoo, y "administrar empleados" incluye ver y cambiar los datos
    # personales de los companeros.
    ("Empleados", [
        "hr.group_hr_manager",
        "hr.group_hr_user",
    ], ["victor@agrogood.cl"],
     "Incluye ver y cambiar los datos personales de los companeros."),

    ("Vacaciones", [
        "hr_holidays.group_hr_holidays_manager",
        "hr_holidays.group_hr_holidays_user",
    ], ["victor@agrogood.cl"],
     "Aprobar las vacaciones de todos no es trabajo de un Picker."),

    ("Asistencias", [
        "hr_attendance.group_hr_attendance_manager",
        "hr_attendance.group_hr_attendance_officer",
    ], ["victor@agrogood.cl"],
     "Cada uno conserva la lectura de la suya, que va en otro grupo."),

    ("Proyectos", [
        "project.group_project_manager",
        "project.group_project_user",
    ], ["victor@agrogood.cl"],
     "Agrogood no lleva proyectos en Odoo."),

    ("Respuestas predefinidas", [
        "mail.group_mail_template_editor",
    ], ["victor@agrogood.cl"],
     "Editar plantillas de correo cambia lo que se le manda a los clientes."),
]

Usuarios = env["res.users"]
intocables = {env.ref("base.user_root").id, env.ref("base.user_admin").id}
personas = Usuarios.search([("id", "not in", list(intocables)),
                            ("share", "=", False)], order="login")

print("=" * 78)
print("PERMISOS REPARTIDOS POR LA INSTALACION" +
      ("  [LIMPIANDO]" if APLICAR else "  [SOLO INFORME]"))
print("=" * 78)


def grupo(xmlid):
    return env.ref(xmlid, raise_if_not_found=False)


# ---------------------------------------------------------------------------
# 1. El usuario plantilla
# ---------------------------------------------------------------------------
plantilla = env.ref("base.default_user", raise_if_not_found=False)
interno = env.ref("base.group_user")
sobran = plantilla.groups_id - interno if plantilla else env["res.groups"]
# Los grupos que `Usuario interno` ya implica llegan igual y no son un problema.
sobran = sobran - interno.implied_ids

print("\n1. USUARIO PLANTILLA  (el molde de los usuarios nuevos)")
if not plantilla:
    print("   No existe. Nada que hacer.")
elif not sobran:
    print("   Correcto: solo Usuario interno. Un usuario nuevo nace sin permisos.")
else:
    admin = [g for g in sobran if "manager" in (g.name or "").lower()
             or "dminis" in (g.name or "")]
    print(f"   {len(sobran)} grupos de mas, {len(admin)} de ellos de administrador.")
    print("   Un usuario creado ahora naceria pudiendo:")
    for g in sorted(sobran, key=lambda x: x.full_name)[:14]:
        print(f"     - {g.full_name}")
    if len(sobran) > 14:
        print(f"     ... y {len(sobran) - 14} grupos mas")

# ---------------------------------------------------------------------------
# 2. Grupos de aplicaciones sin uso
# ---------------------------------------------------------------------------
print("\n2. GRUPOS DE APLICACIONES QUE NADIE USA")
plan = []          # (usuario, grupos a quitar)
for app, xmlids, motivo in RETIRAR_A_TODOS:
    grupos = env["res.groups"].browse([g.id for g in map(grupo, xmlids) if g])
    if not grupos:
        continue
    afectados = personas.filtered(lambda u: u.groups_id & grupos)
    print(f"\n   {app}: {motivo}")
    print(f"   lo tienen {len(afectados)} de {len(personas)} usuarios -> se retira a todos")
    for u in afectados:
        plan.append((u, grupos & u.groups_id))

for app, xmlids, salvo, motivo in RETIRAR_SALVO:
    grupos = env["res.groups"].browse([g.id for g in map(grupo, xmlids) if g])
    if not grupos:
        continue
    afectados = personas.filtered(
        lambda u: (u.groups_id & grupos) and u.login not in salvo)
    print(f"\n   {app}: {motivo}")
    print(f"   se retira a {len(afectados)}; conserva: {', '.join(salvo)}")
    for u in afectados:
        plan.append((u, grupos & u.groups_id))

# ---------------------------------------------------------------------------
# 3. Quien queda viendo la contabilidad
# ---------------------------------------------------------------------------
# Es la comprobacion que de verdad interesa: la lista de quien puede ver los
# costos de compra y los margenes.
acls = env["ir.model.access"].search([
    ("model_id.model", "=", "account.move"), ("perm_read", "=", True)])
grupos_conta = acls.mapped("group_id")
quitados = {}
for u, gs in plan:
    quitados.setdefault(u.id, env["res.groups"])
    quitados[u.id] |= gs

print("\n3. QUIEN PODRA VER LA CONTABILIDAD DESPUES DE LIMPIAR")
for u in personas:
    restantes = (u.groups_id - quitados.get(u.id, env["res.groups"])) & grupos_conta
    marca = "SI " if restantes else " no"
    via = ", ".join(restantes.mapped("full_name")) if restantes else ""
    print(f"   {marca}  {u.login:<30} {via[:44]}")

# ---------------------------------------------------------------------------
if not APLICAR:
    print("\n" + "=" * 78)
    print("SOLO INFORME. Nada se ha modificado.")
    print("Para aplicar: AGROGOOD_PERMISOS=limpiar")
    print("=" * 78)
else:
    print("\nLIMPIANDO...")
    if plantilla and sobran:
        plantilla.write({"groups_id": [(3, g.id) for g in sobran]})
        print(f"  plantilla : {len(sobran)} grupos retirados; queda Usuario interno")

    n = 0
    for u, gs in plan:
        u.write({"groups_id": [(3, g.id) for g in gs]})
        print(f"  {u.login:<30} -{len(gs)}: {', '.join(gs.mapped('name'))[:38]}")
        n += 1
    print(f"  {n} usuarios ajustados")

    env.cr.commit()
    print("\n" + "=" * 78)
    print("LISTO")
    p = env.ref("base.default_user")
    print(f"  grupos del usuario plantilla : {len(p.groups_id)}")
    print("=" * 78)
    print("\nRECORDATORIO: volver a ejecutar esto despues de instalar cualquier")
    print("aplicacion. Odoo repuebla la plantilla en cada instalacion.")
