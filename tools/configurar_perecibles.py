"""Activa el control de caducidad y la salida FEFO en las categorias perecibles.

    AGROGOOD_PERECIBLES=si odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/configurar_perecibles.py

Cierra el hallazgo H6 de la auditoria y la decision de ADR-003, que quedaron
documentados pero sin aplicar: `product_expiry` estaba instalado y ningun
producto tenia caducidad activada, con lo que el control de mermas por
vencimiento no funcionaba en absoluto.

Por defecto solo informa. Escribe con AGROGOOD_PERECIBLES=si.
"""

import os

APLICAR = os.environ.get("AGROGOOD_PERECIBLES") == "si"

# Categorias que se echan a perder. Los abarrotes y condimentos caducan tambien,
# pero en plazos de meses o anios: exigir lote y fecha en la sal complica la
# recepcion sin aportar nada. Se limita a lo que rota en dias.
CATEGORIAS_PERECIBLES = ["VERDURAS", "FRUTAS", "HUEVOS", "CONGELADOS"]

# Dias de vida util por categoria, contados desde la recepcion. Son valores de
# partida razonables: Bodega los ajustara con la experiencia real, producto a
# producto, desde la ficha.
VIDA_UTIL = {
    "VERDURAS": (5, 3, 2),      # (caducidad, consumo preferente, retirada)
    "FRUTAS": (7, 5, 3),
    "HUEVOS": (21, 18, 14),
    "CONGELADOS": (180, 150, 120),
}

print("=" * 74)
print("CONTROL DE CADUCIDAD Y FEFO" + ("  [APLICANDO]" if APLICAR else "  [SOLO INFORME]"))
print("=" * 74)

Categoria = env['product.category']
Producto = env['product.template']

fefo = env['product.removal'].search([('method', '=', 'fefo')], limit=1)
if not fefo:
    print("ERROR: la estrategia FEFO no esta disponible. Falta product_expiry.")
else:
    print(f"\nEstrategia de salida disponible: {fefo.name} ({fefo.method})")

print("\nCATEGORIAS")
afectados = Producto.browse()
for nombre in CATEGORIAS_PERECIBLES:
    cat = Categoria.search([('name', '=', nombre)], limit=1)
    if not cat:
        print(f"  {nombre:<16} no existe en el catalogo")
        continue
    prods = Producto.search([('categ_id', '=', cat.id), ('type', '=', 'consu')])
    afectados |= prods
    dias = VIDA_UTIL[nombre]
    print(f"  {nombre:<16} {len(prods):>3} productos | caduca a los {dias[0]} dias "
          f"(preferente {dias[1]}, retirar {dias[2]})")

print(f"\nTOTAL a configurar: {len(afectados)} productos de {Producto.search_count([('default_code','!=',False)])}")
print(f"  con caducidad ya activada: {len(afectados.filtered('use_expiration_date'))}")

almacenes = env['stock.warehouse'].search([])
print(f"\nUBICACIONES DE STOCK: {len(almacenes)} almacen(es)")
for a in almacenes:
    actual = a.lot_stock_id.removal_strategy_id.name or "por defecto (FIFO)"
    print(f"  {a.name}: estrategia actual = {actual}")

if not APLICAR:
    print("\n" + "=" * 74)
    print("Solo informe. Para aplicar: AGROGOOD_PERECIBLES=si")
    print("=" * 74)
else:
    print("\nAPLICANDO...")
    for nombre in CATEGORIAS_PERECIBLES:
        cat = Categoria.search([('name', '=', nombre)], limit=1)
        if not cat:
            continue
        prods = Producto.search([('categ_id', '=', cat.id), ('type', '=', 'consu')])
        caduca, preferente, retirar = VIDA_UTIL[nombre]
        prods.write({
            # Trazabilidad por lote: sin lote no hay fecha de vencimiento que
            # seguir, y FEFO no tiene por que ordenar.
            'tracking': 'lot',
            'use_expiration_date': True,
            'expiration_time': caduca,
            'use_time': preferente,
            'removal_time': retirar,
            'alert_time': max(1, retirar - 1),
        })
        print(f"  {nombre:<16} {len(prods):>3} productos configurados")

    # FEFO en el stock de cada almacen: primero sale lo que antes vence.
    if fefo:
        for a in almacenes:
            a.lot_stock_id.removal_strategy_id = fefo
            for hija in env['stock.location'].search(
                    [('id', 'child_of', a.lot_stock_id.id)]):
                hija.removal_strategy_id = fefo
        print(f"  FEFO fijado en las ubicaciones de {len(almacenes)} almacen(es)")

    # El grupo de lotes debe estar activo para que Bodega vea los campos.
    grupo_lote = env.ref('stock.group_production_lot')
    grupo_fecha = env.ref('product_expiry.group_expiry_date_on_delivery_slip',
                          raise_if_not_found=False)
    for g in (env.ref('agrogood_base.group_agrogood_warehouse'),
              env.ref('agrogood_base.group_agrogood_logistics_manager')):
        if grupo_lote not in g.implied_ids:
            g.implied_ids = [(4, grupo_lote.id)]
    print("  grupo de lotes activo para Bodega y Logistica")

    env.cr.commit()
    print("\n" + "=" * 74)
    print("APLICADO")
    print(f"  productos con caducidad : "
          f"{Producto.search_count([('use_expiration_date', '=', True)])}")
    print(f"  productos con lote      : "
          f"{Producto.search_count([('tracking', '=', 'lot')])}")
    print(f"  ubicaciones con FEFO    : "
          f"{env['stock.location'].search_count([('removal_strategy_id', '=', fefo.id)]) if fefo else 0}")
    print("=" * 74)
    print("\nA partir de ahora, al recibir mercaderia perecible Bodega debera")
    print("indicar el lote y la fecha de vencimiento. A cambio, el sistema")
    print("sacara siempre primero lo que antes vence y avisara antes de que")
    print("algo se pierda.")
