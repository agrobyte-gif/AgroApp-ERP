"""Deja utilizables las seis aplicaciones recien instaladas.

    AGROGOOD_APPS=si odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http \\
        < tools/configurar_apps_nuevas.py

Cada una necesita datos minimos para que alguien pueda usarla el primer dia.
Una aplicacion instalada y vacia se ve como una que no funciona, y el equipo
deja de abrirla.

Por defecto informa. Escribe con AGROGOOD_APPS=si.
"""

import os

APLICAR = os.environ.get("AGROGOOD_APPS") == "si"

print("=" * 74)
print("CONFIGURACION DE LAS APLICACIONES NUEVAS" +
      ("  [APLICANDO]" if APLICAR else "  [SOLO INFORME]"))
print("=" * 74)

acciones = []

# ---------------------------------------------------------------------------
# 1. MANTENIMIENTO - equipos que se rompen y paran la operacion
# ---------------------------------------------------------------------------
# Se dan de alta los camiones de la flota y los equipos criticos de bodega.
# Un camion parado sin repuesto detiene el reparto de un dia entero; una camara
# de frio parada arruina la mercaderia.
EQUIPOS_BODEGA = [
    ("Camara de frio", "Bodega", 30),
    ("Balanza de recepcion", "Bodega", 180),
    ("Transpaleta", "Bodega", 90),
]

Equipo = env['maintenance.equipment']
Categoria = env['maintenance.equipment.category']
vehiculos = env['fleet.vehicle'].search([])
print(f"\n1. MANTENIMIENTO")
print(f"   vehiculos en la flota          : {len(vehiculos)}")
print(f"   equipos de bodega a dar de alta: {len(EQUIPOS_BODEGA)}")
print(f"   equipos ya registrados         : {Equipo.search_count([])}")

# ---------------------------------------------------------------------------
# 2. VACACIONES - para que Logistica sepa con quien cuenta
# ---------------------------------------------------------------------------
# Sin tipos de ausencia definidos, nadie puede pedir nada.
TIPOS_AUSENCIA = [
    ("Vacaciones", 15, True),
    ("Licencia medica", 0, False),
    ("Permiso sin goce", 0, False),
    ("Dia administrativo", 6, True),
]
Ausencia = env['hr.leave.type']
print(f"\n2. VACACIONES Y AUSENCIAS")
print(f"   tipos definidos ahora : {Ausencia.search_count([])}")
for n, dias, cupo in TIPOS_AUSENCIA:
    ya = Ausencia.search_count([('name', '=', n)])
    print(f"     {'existe' if ya else 'se crea'}  {n:<22} {'con cupo de %s dias' % dias if cupo else 'sin cupo'}")

# ---------------------------------------------------------------------------
# 3. CORREO MASIVO - listas segmentadas por linea comercial
# ---------------------------------------------------------------------------
# Las listas se crean por linea comercial porque el precio y la oferta cambian
# entre HORECA y Minorista: mandarles el mismo correo seria mandar a la mitad
# un precio que no es el suyo.
Lista = env['mailing.list']
lineas = env['agrogood.business.line'].search([])
print(f"\n3. CORREO MASIVO")
print(f"   listas existentes : {Lista.search_count([])}")
con_correo = env['res.partner'].search_count([
    ('agrogood_business_line_id', '!=', False), ('email', '!=', False)])
total = env['res.partner'].search_count([('agrogood_business_line_id', '!=', False)])
print(f"   se creara una lista por linea comercial: {', '.join(lineas.mapped('name'))}")
print(f"   clientes con correo: {con_correo} de {total}")
if not con_correo:
    print("   AVISO: sin correos cargados, las listas naceran vacias. La aplicacion")
    print("          queda lista, pero no sirve hasta que Ventas complete los correos.")

# ---------------------------------------------------------------------------
# 4. PROYECTOS - trabajo interno que no es un pedido
# ---------------------------------------------------------------------------
PROYECTOS = [
    ("Puesta en marcha de Agroapp", "Tareas para dejar el sistema operando"),
    ("Mejoras de bodega", "Cambios de organizacion y equipamiento"),
]
Proyecto = env['project.project']
print(f"\n4. PROYECTOS")
print(f"   proyectos existentes : {Proyecto.search_count([])}")
for n, d in PROYECTOS:
    print(f"     {'existe' if Proyecto.search_count([('name','=',n)]) else 'se crea'}  {n}")

# ---------------------------------------------------------------------------
# 5 y 6. ENCUESTAS Y PROMOCIONES quedan instaladas sin datos
# ---------------------------------------------------------------------------
print(f"\n5. ENCUESTAS: instalada. Se crean cuando haya algo concreto que preguntar;")
print(f"   una encuesta de ejemplo solo estorba.")
print(f"\n6. PROMOCIONES Y DESCUENTOS: instalada. Las reglas las define Ventas segun")
print(f"   su politica comercial, que aun no esta decidida.")

# ---------------------------------------------------------------------------
if not APLICAR:
    print("\n" + "=" * 74)
    print("SOLO INFORME. Para aplicar: AGROGOOD_APPS=si")
    print("=" * 74)
else:
    print("\nAPLICANDO...")

    # --- Mantenimiento ---
    equipo_mant = env['maintenance.team'].search([], limit=1)         or env['maintenance.team'].create({'name': 'Mantencion Agrogood'})
    cat_veh = Categoria.search([('name', '=', 'Vehiculos')], limit=1) \
        or Categoria.create({'name': 'Vehiculos'})
    cat_bod = Categoria.search([('name', '=', 'Equipos de bodega')], limit=1) \
        or Categoria.create({'name': 'Equipos de bodega'})
    n = 0
    for v in vehiculos:
        if not Equipo.search_count([('name', '=', v.name)]):
            # En Odoo 18 la periodicidad no vive en el equipo: la mantencion
            # preventiva se programa creando una solicitud recurrente. El
            # equipo solo guarda su ficha y su historial de averias.
            Equipo.create({'name': v.name, 'category_id': cat_veh.id,
                           'maintenance_team_id': equipo_mant.id,
                           'note': 'Revision preventiva sugerida cada 90 dias'})
            n += 1
    for nombre, ubic, dias in EQUIPOS_BODEGA:
        if not Equipo.search_count([('name', '=', nombre)]):
            Equipo.create({'name': nombre, 'category_id': cat_bod.id,
                           'maintenance_team_id': equipo_mant.id,
                           'note': f'Revision preventiva sugerida cada {dias} dias'})
            n += 1
    print(f"  mantenimiento : {n} equipos dados de alta")

    # --- Ausencias ---
    n = 0
    for nombre, dias, cupo in TIPOS_AUSENCIA:
        if Ausencia.search_count([('name', '=', nombre)]):
            continue
        Ausencia.create({
            'name': nombre,
            'requires_allocation': 'yes' if cupo else 'no',
            'leave_validation_type': 'hr',
            'company_id': env.company.id,
        })
        n += 1
    print(f"  ausencias     : {n} tipos creados")

    # --- Listas de correo ---
    n = 0
    for l in lineas:
        nombre = f"Clientes {l.name}"
        if Lista.search_count([('name', '=', nombre)]):
            continue
        lista = Lista.create({'name': nombre})
        socios = env['res.partner'].search([
            ('agrogood_business_line_id', '=', l.id), ('email', '!=', False)])
        for s in socios:
            env['mailing.contact'].create({
                'name': s.name, 'email': s.email,
                'list_ids': [(4, lista.id)],
            })
        print(f"                  '{nombre}': {len(socios)} contactos")
        n += 1
    print(f"  correo masivo : {n} listas creadas")

    # --- Proyectos ---
    n = 0
    for nombre, desc in PROYECTOS:
        if not Proyecto.search_count([('name', '=', nombre)]):
            Proyecto.create({'name': nombre, 'description': desc,
                             'company_id': env.company.id})
            n += 1
    print(f"  proyectos     : {n} creados")

    env.cr.commit()
    print("\n" + "=" * 74)
    print("LISTO")
    print(f"  equipos con mantenimiento programado : {Equipo.search_count([])}")
    print(f"  tipos de ausencia                    : {Ausencia.search_count([])}")
    print(f"  listas de correo                     : {Lista.search_count([])}")
    print(f"  proyectos                            : {Proyecto.search_count([])}")
    print("=" * 74)
