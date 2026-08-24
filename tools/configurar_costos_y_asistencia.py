"""Deja utilizables `stock_landed_costs` y `hr_attendance`.

    AGROGOOD_CONFIG=si odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http \\
        < tools/configurar_costos_y_asistencia.py

Instalar estas dos aplicaciones no basta: sin configurarlas quedan decorativas.

* Los costos de traida solo llegan al costo del producto si la categoria usa
  valoracion automatica y costo promedio. Con valoracion manual, el reparto del
  flete se calcula y no se aplica a nada.
* Nadie puede marcar entrada sin una ficha de empleado ligada a su usuario.

Por defecto informa. Escribe con AGROGOOD_CONFIG=si.
"""

import os

APLICAR = os.environ.get("AGROGOOD_CONFIG") == "si"

# Tipos de costo reales de una distribuidora hortofruticola. Son productos de
# servicio: se compran, se reparten sobre la mercaderia y desaparecen.
COSTOS = [
    ("Flete de compra", "Transporte desde el proveedor o la feria hasta bodega"),
    ("Carga y descarga", "Mano de obra de estiba"),
    ("Comision de feria", "Comision del corredor o de la feria mayorista"),
    ("Merma en transito", "Perdida esperada del viaje, repartida sobre lo recibido"),
    ("Otros costos de compra", "Peajes, envases, cualquier otro costo de traida"),
]

print("=" * 74)
print("CONFIGURACION" + ("  [APLICANDO]" if APLICAR else "  [SOLO INFORME]"))
print("=" * 74)

Cat = env['product.category']
Prod = env['product.template']

# ---------------------------------------------------------------------------
# 1. Valoracion de inventario
# ---------------------------------------------------------------------------
raiz = Cat.search([('name', '=', 'Agrogood'), ('parent_id', '=', False)], limit=1)
categorias = Cat.search([('id', 'child_of', raiz.id)]) if raiz else Cat.search([])

print(f"\n1. VALORACION DE INVENTARIO ({len(categorias)} categorias)")
print("   Se pasa a costo PROMEDIO y valoracion AUTOMATICA.")
print("   Promedio y no FIFO porque en fruta y verdura el mismo producto entra")
print("   varias veces por semana a precios distintos: seguir cada lote por su")
print("   costo exacto da un dato mas preciso que nadie va a usar, y complica")
print("   cada movimiento de bodega.")
for c in categorias[:6]:
    print(f"     {c.complete_name[:52]:<52} {c.property_cost_method} / {c.property_valuation}")
if len(categorias) > 6:
    print(f"     ... y {len(categorias)-6} mas")

# ---------------------------------------------------------------------------
# 2. Productos de costo
# ---------------------------------------------------------------------------
print(f"\n2. TIPOS DE COSTO DE TRAIDA ({len(COSTOS)})")
for nombre, desc in COSTOS:
    existe = Prod.search_count([('name', '=', nombre)])
    print(f"     {'ya existe' if existe else 'se creara'}  {nombre:<24} {desc[:36]}")

# ---------------------------------------------------------------------------
# 3. Empleados
# ---------------------------------------------------------------------------
usuarios = env['res.users'].search([
    ('login', 'like', '@agrogood.cl')], order='login')
sin_ficha = usuarios.filtered(
    lambda u: not env['hr.employee'].search_count([('user_id', '=', u.id)]))
print(f"\n3. FICHAS DE EMPLEADO ({len(sin_ficha)} por crear)")
for u in sin_ficha:
    print(f"     {u.name[:26]:<26} {u.login}")

# ---------------------------------------------------------------------------
if not APLICAR:
    print("\n" + "=" * 74)
    print("SOLO INFORME. Para aplicar: AGROGOOD_CONFIG=si")
    print("=" * 74)
else:
    print("\nAPLICANDO...")

    # Valoracion. Solo sobre categorias con productos almacenables: ponersela a
    # una categoria de servicios generaria asientos contables sin sentido.
    n = 0
    for c in categorias:
        if Prod.search_count([('categ_id', '=', c.id), ('is_storable', '=', True)]):
            c.write({
                'property_cost_method': 'average',
                'property_valuation': 'real_time',
            })
            n += 1
    print(f"  valoracion automatica y costo promedio en {n} categorias")

    # Productos de costo
    creados = 0
    for nombre, desc in COSTOS:
        if Prod.search_count([('name', '=', nombre)]):
            continue
        Prod.create({
            'name': nombre,
            'type': 'service',
            'landed_cost_ok': True,
            'purchase_ok': True,
            'sale_ok': False,
            'description': desc,
            # Por cantidad: el flete se reparte segun cuanto pesa o cuantas
            # cajas trae cada linea, que es como se reparte de verdad.
            'split_method_landed_cost': 'by_quantity',
        })
        creados += 1
    print(f"  {creados} tipos de costo creados")

    # Empleados
    dept = env['hr.department'].search([('name', '=', 'Agrogood')], limit=1) \
        or env['hr.department'].create({'name': 'Agrogood'})
    n = 0
    for u in sin_ficha:
        env['hr.employee'].create({
            'name': u.name,
            'user_id': u.id,
            'work_email': u.email or u.login,
            'department_id': dept.id,
            'company_id': env.company.id,
        })
        n += 1
    print(f"  {n} fichas de empleado creadas")

    env.cr.commit()
    print("\n" + "=" * 74)
    print("LISTO")
    print(f"  categorias con valoracion automatica: "
          f"{len(Cat.search([('property_valuation','=','real_time')]))}")
    print(f"  tipos de costo disponibles          : "
          f"{Prod.search_count([('landed_cost_ok','=',True)])}")
    print(f"  empleados que pueden marcar entrada : "
          f"{env['hr.employee'].search_count([('user_id','!=',False)])}")
    print("=" * 74)
    print("\nATENCION: la valoracion automatica genera asientos contables por")
    print("cada movimiento de stock. Es lo que permite conocer el margen real,")
    print("pero conviene que Ventas lo sepa antes de ver aparecer asientos que")
    print("hasta ahora no existian.")
