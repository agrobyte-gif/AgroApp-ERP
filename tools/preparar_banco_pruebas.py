"""Deja la base lista para ensayar el flujo completo con la PWA.

    AGROGOOD_BANCO=si odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/preparar_banco_pruebas.py

No es lo mismo que `limpiar_datos_prueba.py`. Aquella deja la base vacia, que
es lo que se quiere antes de pasar a produccion. Esta deja la base LISTA PARA
PRACTICAR: borra los restos de ensayos anteriores y monta un dia de trabajo
verosimil con clientes y productos reales.

El montaje se detiene a proposito en el punto en que hay pedidos confirmados y
mercaderia reservada, SIN Picker asignado. Asignarlo es trabajo de Felipe desde
el escritorio, y es parte de lo que hay que ensayar: si el banco lo dejara
hecho, el ensayo se saltaria justo el paso donde Logistica decide quien prepara
que.

Dos modos de escritura:

    AGROGOOD_BANCO=si       borra los restos y monta tres pedidos nuevos.
    AGROGOOD_BANCO=vaciar   solo borra, y deja el stock a cero.

El modo `vaciar` sirve para construir el flujo a mano de punta a punta: se
empieza sin mercaderia, de modo que el primer pedido genera faltante, el
faltante llega a Compras, Compras compra, Bodega recibe y solo entonces hay
algo que preparar. Es el recorrido completo, incluida la parte de
aprovisionamiento que el modo `si` se salta al dejar 200 unidades puestas.

Lo que NO borra ninguno de los dos modos: clientes, productos, tarifas,
usuarios -incluidos Picker Demo y Conductor Demo, que hacen falta para probar
el movil-, vehiculos, empleados y el historial ya cerrado.

Por defecto informa.
"""

import os
from datetime import timedelta

from odoo import fields

MODO = os.environ.get("AGROGOOD_BANCO", "")
APLICAR = MODO in ("si", "vaciar")
SOLO_VACIAR = MODO == "vaciar"

# Tres pedidos: suficiente para armar una ruta con varias paradas y ver como se
# comporta la pantalla del conductor con una lista, no con un solo elemento.
CUANTOS_PEDIDOS = 3
LINEAS_POR_PEDIDO = 4

print("=" * 78)
print("BANCO DE PRUEBAS PARA LA PWA" +
      ("  [VACIANDO]" if SOLO_VACIAR else
       "  [MONTANDO]" if APLICAR else "  [SOLO INFORME]"))
print("=" * 78)

Socio = env['res.partner']
Prod = env['product.product']
SO = env['sale.order']
Pick = env['stock.picking']

# ---------------------------------------------------------------------------
# 1. Restos de ensayos anteriores
# ---------------------------------------------------------------------------
rutas = env['agrogood.route'].search([])
sesiones = env['agrogood.picking.session'].search([])
pend = Pick.search([('state', 'not in', ('done', 'cancel'))])
ventas_abiertas = SO.search([('state', 'in', ('draft', 'sent', 'sale'))])

print("\n1. RESTOS DE ENSAYOS ANTERIORES")
print("   rutas                    : %d  (%s)"
      % (len(rutas), ', '.join(rutas.mapped('state')) or 'ninguna'))
print("   sesiones de preparacion  : %d" % len(sesiones))
print("   albaranes sin terminar   : %d" % len(pend))
print("   pedidos abiertos         : %d" % len(ventas_abiertas))
print("   Se cancelan y se borran. Los datos maestros -clientes, productos,")
print("   tarifas, usuarios- y el historial ya cerrado no se tocan.")

# ---------------------------------------------------------------------------
# 2. Con quien y con que se monta
# ---------------------------------------------------------------------------
# Clientes que se puedan facturar de verdad al final del ensayo. Sin RUT el
# ensayo se corta en el ultimo paso, que es justo el que interesa comprobar.
candidatos = Socio.search([
    ('agrogood_business_line_id', '!=', False),
    ('parent_id', '=', False),
    ('street', '!=', False),
    ('agrogood_billing_blocked', '=', False),
], order='name')
# Sin repetir nombre. La cartera trae fichas duplicadas del mismo negocio
# -AKURA LOMAS esta dos veces con el mismo RUT- y montar dos paradas para el
# mismo cliente confundiria al conductor durante el ensayo.
clientes, nombres = Socio, set()
for c in candidatos:
    clave = (c.name or '').strip().upper()
    if clave in nombres:
        continue
    nombres.add(clave)
    clientes |= c
    if len(clientes) >= CUANTOS_PEDIDOS:
        break

# Una canasta creible: verdura y fruta, que es el negocio, y mitad de peso
# variable. Los de peso variable obligan al Picker a pesar y teclear, que es
# donde la pantalla se pone a prueba; los de peso fijo comprueban que la misma
# pantalla no se lo pida cuando no corresponde. Solo con unos u otros el ensayo
# probaria la mitad.
NUCLEO = [('default_code', '=like', 'VER-%'), ('default_code', '=like', 'FRUT%')]
mitad = LINEAS_POR_PEDIDO // 2


def canasta(variable, cuantos):
    if cuantos <= 0:
        # Ojo con `limit`: en Odoo, limit=0 no significa "ninguno" sino "sin
        # limite", y la busqueda devolveria el catalogo entero.
        return Prod
    base = [('is_storable', '=', True),
            ('agrogood_is_variable_weight', '=', variable)]
    r = Prod.search(base + ['|'] + NUCLEO, limit=cuantos, order='default_code')
    if len(r) < cuantos:                       # sin verdura suficiente, lo que haya
        r |= Prod.search(base + [('id', 'not in', r.ids)], limit=cuantos - len(r))
    return r


variables = canasta(True, mitad)
fijos = canasta(False, LINEAS_POR_PEDIDO - len(variables))
productos = variables | fijos

print("\n2. CON QUIEN Y CON QUE")
print("   clientes facturables encontrados: %d" % len(clientes))
for c in clientes:
    print("     %-34s %-10s %s" % (c.name[:34],
                                   c.agrogood_business_line_id.name,
                                   (c.street or '')[:22]))
print("   productos: %d (%d de peso variable)" % (len(productos), len(variables)))
for p in productos:
    marca = "peso variable" if p.agrogood_is_variable_weight else "peso fijo"
    print("     %-10s %-30s %s" % ((p.default_code or '-'), p.name[:30], marca))

if len(clientes) < CUANTOS_PEDIDOS or not productos:
    print("\n   NO SE PUEDE MONTAR: faltan clientes facturables o productos.")
    print("   Completar RUT en Paneles > Ventas > Completar RUT de clientes.")

# ---------------------------------------------------------------------------
if not APLICAR:
    print("\n" + "=" * 78)
    print("SOLO INFORME. Nada se ha modificado.")
    print("Para montar tres pedidos : AGROGOOD_BANCO=si")
    print("Para dejarlo todo vacio  : AGROGOOD_BANCO=vaciar")
    print("=" * 78)
else:
    print("\nMONTANDO...")

    # --- Borrar los restos ---
    # El orden importa: primero lo que cuelga de otra cosa. Y hay que cancelar
    # antes de borrar, porque Odoo no deja eliminar un documento confirmado.
    facturas = env['account.move'].search([('move_type', '!=', 'entry')])
    facturas.filtered(lambda f: f.state == 'posted').button_draft()
    facturas.filtered(lambda f: f.state != 'cancel').button_cancel()
    facturas.unlink()

    env['agrogood.followup'].search([]).unlink()
    env['agrogood.driver.position'].search([]).unlink()
    rutas.filtered(lambda r: r.state != 'done').action_cancel()
    env['agrogood.route.stop'].search([]).unlink()
    rutas.unlink()
    sesiones.unlink()

    compras = env['purchase.order'].search([])
    compras.filtered(lambda o: o.state not in ('cancel',)).button_cancel()
    compras.unlink()
    env['agrogood.purchase.request'].search([]).unlink()

    todos_alb = env['stock.picking'].search([('state', '!=', 'done')])
    todos_alb.action_cancel()
    ventas_abiertas.filtered(lambda o: o.state != 'cancel')._action_cancel()
    ventas_abiertas.unlink()
    todos_alb.unlink()
    print("  operaciones eliminadas: facturas, rutas, preparaciones, compras,")
    print("  solicitudes, albaranes y pedidos")

    if SOLO_VACIAR:
        # Los asientos de valoracion ya generados NO se pueden borrar sin
        # falsear la contabilidad, asi que el stock se pone a cero con un
        # ajuste de inventario, que es lo que se haria en la vida real.
        quants = env['stock.quant'].search([
            ('location_id.usage', '=', 'internal'), ('quantity', '!=', 0)])
        if quants:
            quants.with_context(inventory_mode=True).write({'inventory_quantity': 0})
            quants.with_context(inventory_mode=True)._apply_inventory()
        # Se confirma AQUI, antes de tocar los lotes. Si el borrado de lotes
        # falla y hubiera que deshacerlo, un rollback posterior se llevaria por
        # delante la puesta a cero del stock, que ya esta bien hecha.
        env.cr.commit()
        # Los lotes del banco solo se pueden borrar si ya no queda ningun
        # registro de inventario apuntandolos, y Odoo conserva los registros en
        # cero. Si no se dejan borrar no pasa nada: un lote vacio no afecta a
        # nada y se reutiliza si se vuelve a montar el banco.
        lotes = env['stock.lot'].search([('name', '=', 'BANCO-PRUEBAS')])
        if lotes:
            try:
                env['stock.quant'].search([('lot_id', 'in', lotes.ids)]).unlink()
                lotes.unlink()
                print("  lotes del banco eliminados")
            except Exception:
                env.cr.rollback()
                print("  lotes del banco: se conservan (siguen referenciados)")
        env.cr.commit()
        print("  stock puesto a cero (%d ubicaciones ajustadas)" % len(quants))
        print(chr(10) + "=" * 78)
        print("BASE VACIA Y LISTA PARA CONSTRUIR EL FLUJO A MANO")
        print("  clientes         : %d" % env['res.partner'].search_count(
            [('agrogood_business_line_id', '!=', False)]))
        print("  productos        : %d" % env['product.template'].search_count(
            [('is_storable', '=', True)]))
        print("  usuarios         : %d" % env['res.users'].search_count(
            [('login', 'like', '@agrogood.cl')]))
        print("  pedidos abiertos : %d" % env['sale.order'].search_count(
            [('state', 'in', ('draft', 'sent', 'sale'))]))
        print("  stock            : %d productos con existencias" %
              env['stock.quant'].search_count(
                  [('location_id.usage', '=', 'internal'), ('quantity', '>', 0)]))
        print("=" * 78)
        raise SystemExit(0)

    # --- Stock, que sin el no hay nada que preparar ---
    almacen = env['stock.warehouse'].search([], limit=1)
    ubic = almacen.lot_stock_id
    n = 0
    for p in productos:
        vals = {'product_id': p.id, 'location_id': ubic.id,
                'inventory_quantity': 200.0}
        if p.tracking == 'lot':
            # Los perecibles llevan lote con caducidad: sin el, la reserva FEFO
            # no tiene entre que elegir.
            lote = env['stock.lot'].search([
                ('product_id', '=', p.id),
                ('name', '=', 'BANCO-PRUEBAS')], limit=1)
            if not lote:
                lote = env['stock.lot'].create({
                    'product_id': p.id,
                    'name': 'BANCO-PRUEBAS',
                    'expiration_date': fields.Datetime.now() + timedelta(days=8),
                    'company_id': env.company.id,
                })
            vals['lot_id'] = lote.id
        cuant = env['stock.quant'].with_context(inventory_mode=True).create(vals)
        cuant._apply_inventory()
        n += 1
    print("  %d productos con 200 unidades en bodega" % n)

    # --- Los pedidos ---
    creados = SO
    for i, cliente in enumerate(clientes):
        pedido = SO.create({'partner_id': cliente.id})
        for j, p in enumerate(productos):
            env['sale.order.line'].create({
                'order_id': pedido.id,
                'product_id': p.id,
                'product_uom_qty': 5.0 + (i * 2) + j,
            })
        pedido.action_confirm()
        creados |= pedido
    print("  %d pedidos confirmados" % len(creados))

    env.cr.commit()

    listos = Pick.search([('picking_type_id.code', '=', 'outgoing'),
                          ('state', '=', 'assigned')])
    print("\n" + "=" * 78)
    print("BANCO LISTO")
    for p in creados:
        alb = p.picking_ids.filtered(lambda x: x.state not in ('cancel', 'done'))
        print("  %s  %-28s %d lineas  ->  %s"
              % (p.name, p.partner_id.name[:28], len(p.order_line),
                 ', '.join(alb.mapped('name'))))
    print("\n  albaranes listos para preparar: %d" % len(listos))
    print("  Ninguno tiene Picker asignado todavia: eso lo hace Felipe desde")
    print("  Inventario > Albaranes > Asignar a un Picker.")
    print("=" * 78)
