"""Prueba integral: el criterio de aceptacion completo, de punta a punta.

Recorre los quince pasos del flujo real de Agrogood en una sola corrida, sobre
la base de datos con los clientes y productos reales importados.

    odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/prueba_integral.py

No escribe nada permanente: termina con rollback. Sirve para comprobar que los
modulos siguen encajando entre si despues de cualquier cambio.
"""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError

R = []


def paso(n, titulo, condicion, detalle=""):
    R.append((n, titulo, bool(condicion)))
    marca = "OK " if condicion else "FALLA"
    print(f"  [{marca}] {n:>2}. {titulo}")
    if detalle:
        print(f"            {detalle}")


SO = env['sale.order']
REQ = env['agrogood.purchase.request']
RUTA = env['agrogood.route']
FUP = env['agrogood.followup']
ESTADO = dict(SO._fields['agrogood_state'].selection)
E = lambda p: ESTADO[p.agrogood_state]

print("=" * 78)
print("PRUEBA INTEGRAL AGROGOOD - criterio de aceptacion")
print("=" * 78)

# --- Preparativos -----------------------------------------------------------
G = env.ref
alm = env['stock.warehouse'].search([], limit=1)
# La prueba crea SUS PROPIOS cliente y productos. Reutilizar los reales la
# haria depender de lo que otros pedidos tengan reservado en ese momento: el
# faltante saldria distinto cada vez y el resultado no significaria nada.
modelo_tomate = env['product.template'].search(
    [('default_code', '=', 'VER-081')], limit=1)
linea = env.ref('agrogood_base.business_line_horeca')
cliente = env['res.partner'].create({
    'name': 'CLIENTE PRUEBA INTEGRAL',
    'is_company': True,
    'street': 'Colo Colo 486', 'city': 'CONCEPCION',
    'phone': '+56 9 1234 5678',
    'country_id': env.ref('base.cl').id,
    'vat': '76593894-5',
    'l10n_latam_identification_type_id': env.ref('l10n_cl.it_RUT').id,
    'l10n_cl_sii_taxpayer_type': '1',
    'customer_rank': 1,
    'agrogood_business_line_id': linea.id,
    'property_product_pricelist': linea.pricelist_id.id,
})
tomate = env['product.template'].create({
    'name': 'TOMATE PRUEBA INTEGRAL', 'default_code': 'TEST-INT-01',
    'type': 'consu', 'is_storable': True, 'invoice_policy': 'delivery',
    'uom_id': env.ref('uom.product_uom_kgm').id,
    'uom_po_id': env.ref('uom.product_uom_kgm').id,
    'categ_id': modelo_tomate.categ_id.id,
    'agrogood_is_variable_weight': True,
    'agrogood_format_id': env.ref('agrogood_base.product_format_caja').id,
    'agrogood_reference_weight': 10.0,
}).product_variant_id
acelga = env['product.template'].create({
    'name': 'ACELGA PRUEBA INTEGRAL', 'default_code': 'TEST-INT-02',
    'type': 'consu', 'is_storable': True, 'invoice_policy': 'delivery',
    'categ_id': modelo_tomate.categ_id.id,
}).product_variant_id
# Precios via el propio modulo de tarifas, como en la operacion real.
version = env['agrogood.price.version'].create({
    'name': 'Precios prueba integral',
    'business_line_id': linea.id, 'pricelist_id': linea.pricelist_id.id,
    'date_start': fields.Date.context_today(env.user) - timedelta(days=1),
    'line_ids': [
        (0, 0, {'product_tmpl_id': tomate.product_tmpl_id.id, 'price': 15500.0}),
        (0, 0, {'product_tmpl_id': acelga.product_tmpl_id.id, 'price': 1800.0}),
    ],
})
version.action_apply()

picker = env['res.users'].create({
    'name': 'Picker Integral', 'login': 'picker.integral@agrogood.cl',
    'groups_id': [(6, 0, [G('base.group_user').id,
                          G('agrogood_base.group_agrogood_picker').id])]})
chofer = env['res.users'].create({
    'name': 'Conductor Integral', 'login': 'chofer.integral@agrogood.cl',
    'groups_id': [(6, 0, [G('base.group_user').id,
                          G('agrogood_base.group_agrogood_driver').id])]})
proveedor = env['res.partner'].create({'name': 'Feria Integral', 'supplier_rank': 1})
marca = env['fleet.vehicle.model.brand'].create({'name': 'Integral'})
modelo = env['fleet.vehicle.model'].create({'name': 'Camion', 'brand_id': marca.id})
camion = env['fleet.vehicle'].create({
    'model_id': modelo.id, 'license_plate': 'INT-01',
    'agrogood_capacity_kg': 600.0})

# Stock inicial deliberadamente insuficiente: el pedido debe generar faltante.
env['stock.quant'].with_context(inventory_mode=True).create([
    {'product_id': tomate.id, 'location_id': alm.lot_stock_id.id,
     'inventory_quantity': 8},
    {'product_id': acelga.id, 'location_id': alm.lot_stock_id.id,
     'inventory_quantity': 50},
])._apply_inventory()

print(f"\nCliente: {cliente.name} ({cliente.agrogood_business_line_id.name})")
print(f"Stock inicial: 8 kg de tomate (se van a pedir 30) y 50 de acelga\n")

# --- 1-2. WhatsApp -> pedido ------------------------------------------------
pedido = SO.create({
    'partner_id': cliente.id,
    'agrogood_source': 'whatsapp',
    'agrogood_delivery_slot': 'morning',
    'agrogood_delivery_note': 'Recibe Marcela, antes de las 10',
    'order_line': [
        (0, 0, {'product_id': tomate.id, 'product_uom_qty': 30}),
        (0, 0, {'product_id': acelga.id, 'product_uom_qty': 10}),
    ],
})
paso(1, "El pedido entra por WhatsApp y queda registrado",
     pedido.agrogood_source == 'whatsapp' and pedido.state == 'draft',
     f"{pedido.name} para {cliente.name}")
paso(2, "El precio sale de la tarifa de su linea comercial",
     pedido.order_line[0].price_unit > 0,
     f"tomate a {pedido.order_line[0].price_unit:,.0f} CLP/kg "
     f"({pedido.agrogood_business_line_id.name})")

# --- 3-4. Stock y faltante --------------------------------------------------
pedido.action_confirm()
pedido.invalidate_recordset()
falta = pedido.order_line[0].agrogood_shortage_qty
paso(3, "El sistema valida el stock y detecta el faltante",
     abs(falta - 22) < 0.01 and pedido.agrogood_state == 'awaiting_stock',
     f"faltan {falta:g} kg de tomate; estado: {E(pedido)}")

# --- 5. Pizarra de compras --------------------------------------------------
res = pedido.action_agrogood_request_replenishment()
solicitudes = REQ.browse(res['domain'][0][2])
paso(4, "El faltante genera solicitud en la pizarra de Compras",
     len(solicitudes) == 1 and abs(solicitudes.qty_requested - 22) < 0.01,
     f"{solicitudes.name}: {solicitudes.qty_requested:g} kg, "
     f"prioridad {dict(solicitudes._fields['priority'].selection)[solicitudes.priority]}, "
     f"responsable {solicitudes.user_id.name}")

# --- 6. Compras gestiona ----------------------------------------------------
solicitudes.action_search()
solicitudes.action_quote()
solicitudes.state_note = "Conseguido en Lo Valledor"
solicitudes.supplier_id = proveedor
compra = env['purchase.order'].browse(
    solicitudes.action_create_purchase_order().get('res_id'))
solicitudes.invalidate_recordset()
paso(5, "Compras cotiza y genera la orden de compra",
     compra and solicitudes.state == 'purchased',
     f"{compra.name} a {proveedor.name} por {compra.order_line.product_qty:g} kg")

# --- 7. Bodega recibe -------------------------------------------------------
compra.button_confirm()
recepcion = compra.picking_ids
for mv in recepcion.move_ids:
    mv.quantity, mv.picked = mv.product_uom_qty, True
recepcion.button_validate()
solicitudes.action_mark_received()
pedido.picking_ids.action_assign()
pedido.invalidate_recordset()
paso(6, "Bodega recibe la compra y el faltante desaparece",
     pedido.order_line[0].agrogood_shortage_qty == 0
     and pedido.agrogood_state == 'to_pick',
     f"estado del pedido: {E(pedido)}")

# --- 8-9. Picking -----------------------------------------------------------
salida = pedido.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing')
w = env['agrogood.assign.picker'].create({
    'picking_ids': [(6, 0, salida.ids)], 'picker_id': picker.id})
sesion = env['agrogood.picking.session'].browse(w.action_assign()['domain'][0][2])
sesion.action_start()
pedido.invalidate_recordset()
paso(7, "Logistica asigna un Picker y este empieza",
     pedido.agrogood_state == 'picking',
     f"{sesion.picker_id.name}; estado: {E(pedido)}")

mv_tom = salida.move_ids.filtered(lambda m: m.product_id == tomate)
mv_ace = salida.move_ids.filtered(lambda m: m.product_id == acelga)

# El cero de mas debe detenerse en el momento, no una hora despues.
mv_tom.quantity, mv_tom.picked, mv_tom.agrogood_line_status = 300.0, True, 'confirmed'
mv_ace.quantity, mv_ace.picked, mv_ace.agrogood_line_status = 10.0, True, 'confirmed'
bloqueado = False
try:
    sesion.action_finish()
except (UserError, ValidationError):
    bloqueado = True
paso(8, "Un peso disparatado se detiene mientras el Picker lo teclea",
     bloqueado, "300 kg donde se pedian 30: rechazado")

# Peso real: 28,6 kg de los 30 pedidos.
mv_tom.quantity = 28.6
sesion.action_finish()
pedido.invalidate_recordset()
paso(9, "El Picker registra el peso real y termina",
     pedido.agrogood_state == 'picked',
     f"28,6 kg de los 30 pedidos ({mv_tom.agrogood_weight_deviation:+.1f}%); "
     f"preparado en {sesion.duration_minutes:.2f} min")

# --- 10. Ruta ---------------------------------------------------------------
ruta = RUTA.create({'date': fields.Date.context_today(env.user),
                    'driver_id': chofer.id, 'vehicle_id': camion.id})
env['agrogood.route.add.pickings'].create({
    'route_id': ruta.id, 'picking_ids': [(6, 0, salida.ids)]}).action_add()
ruta.action_sequence_by_window()
ruta.action_plan()
pedido.invalidate_recordset()
ruta.invalidate_recordset()
paso(10, "Logistica arma la ruta y asigna conductor y vehiculo",
     pedido.agrogood_state == 'to_dispatch',
     f"{ruta.name}: {ruta.estimated_weight:.0f} kg de {ruta.vehicle_capacity:.0f} "
     f"({ruta.capacity_usage:.0f}% del camion); estado: {E(pedido)}")

# --- 10 bis. La revision del vehiculo ---------------------------------------
# Bloquea la salida a proposito: una revision que se puede saltar deja de
# hacerse la segunda semana. Se comprueba primero que de verdad bloquea, porque
# un candado que no cierra es peor que no tener candado -da la sensacion de que
# el camion se revisa-.
try:
    ruta.action_start()
    bloquea = False
except UserError:
    bloquea = True
paso(11, "Sin revisar el vehiculo, la ruta no arranca", bloquea,
     "la salida queda bloqueada hasta que el conductor la haga")

revision = env['agrogood.vehicle.check'].create({
    'route_id': ruta.id,
    'vehicle_id': ruta.vehicle_id.id,
    'driver_id': ruta.driver_id.id,
    'check_combustible': True, 'check_neumaticos': True, 'check_luces': True,
    'check_frenos': True, 'check_frio': True, 'check_carga': True,
})
paso(12, "El conductor revisa el vehiculo y queda sin novedad",
     revision.state == 'ok' and revision.problem_count == 0,
     f"{revision.name}: los seis puntos pasan")

# Y marcar un fallo sin explicarlo tampoco se admite: Logistica veria que algo
# pasa sin saber que, con el camion ya en la calle.
try:
    env['agrogood.vehicle.check'].create({
        'vehicle_id': ruta.vehicle_id.id, 'driver_id': ruta.driver_id.id,
        'check_combustible': True, 'check_neumaticos': True, 'check_luces': True,
        'check_frenos': False, 'check_frio': True, 'check_carga': True,
    })
    exige = False
except UserError:
    exige = True
paso(13, "Marcar un fallo obliga a decir cual", exige,
     "sin explicacion, la revision no se guarda")

# --- 11. En ruta ------------------------------------------------------------
ruta.action_start()
pedido.invalidate_recordset()
parada = ruta.stop_ids[0]
paso(14, "El conductor sale y el pedido queda en ruta",
     pedido.agrogood_state == 'in_route',
     f"parada 1: {parada.partner_id.name}, {parada.street or 's/d'} "
     f"({parada.scheduled_time})")

# --- 12. Entrega con evidencia ---------------------------------------------
parada.action_arrived()
parada.write({'received_by': 'Marcela Soto',
              'gps_latitude': -36.8270, 'gps_longitude': -73.0498,
              'stop_note': 'Entregado en recepcion'})
parada.action_delivered()
pedido.invalidate_recordset()
salida.invalidate_recordset()
n_espera = env['stock.picking'].search_count([('backorder_id', '=', salida.id)])
paso(15, "Entrega registrada con evidencia y stock descontado",
     parada.state == 'delivered' and salida.state == 'done'
     and pedido.agrogood_state == 'delivered',
     f"recibido por {parada.received_by}; albaran {salida.state}; "
     f"entregados {pedido.order_line[0].qty_delivered:g} kg")
paso(16, "Peso variable: no queda ningun albaran fantasma",
     n_espera == 0,
     f"pedidos en espera creados por los 1,4 kg de diferencia: {n_espera}")

# --- 13. Facturacion --------------------------------------------------------
factura = pedido._create_invoices()
factura.action_post()
pedido.invalidate_recordset()
linea_tom = factura.invoice_line_ids.filtered(lambda l: l.product_id == tomate)
paso(17, "Se factura lo entregado, no lo pedido",
     abs(linea_tom.quantity - 28.6) < 0.01 and pedido.agrogood_state == 'invoiced',
     f"{factura.name}: {linea_tom.quantity:g} kg de tomate (no 30); "
     f"total {factura.amount_total:,.0f} CLP")

# --- 14-15. CRM -------------------------------------------------------------
cliente._agrogood_recompute_metrics()
cliente.invalidate_recordset()
tenia = cliente.agrogood_order_count
paso(18, "El CRM registra el comportamiento del cliente",
     cliente.agrogood_order_count > 0 and cliente.agrogood_last_order_date,
     f"{tenia} pedidos; ticket medio {cliente.agrogood_avg_ticket:,.0f} CLP; "
     f"situacion: {dict(cliente._fields['agrogood_customer_status'].selection)[cliente.agrogood_customer_status]}; "
     f"suele llevar: {(cliente.agrogood_top_products or '')[:40]}")

# El motor de recontacto: se simula que este pedido fue hace 7 dias.
pedido.date_order = fields.Datetime.now() - timedelta(days=7)
cliente._agrogood_recompute_metrics()
cliente.invalidate_recordset()
FUP.search([('partner_id', '=', cliente.id)]).unlink()
FUP._cron_generar_seguimientos()
seg = FUP.search([('partner_id', '=', cliente.id)], limit=1)
paso(19, "El sistema sabe cuando volver a contactarlo",
     seg and seg.reason in ('same_weekday', 'expected_day'),
     f"{dict(seg._fields['reason'].selection)[seg.reason] if seg else 'sin seguimiento'}"
     + (f"; llevo: {(seg.last_order_products or '')[:34]}" if seg else ""))

pedido.action_agrogood_close()
pedido.invalidate_recordset()
paso(20, "El pedido se cierra", pedido.agrogood_state == 'closed', E(pedido))

# --- 18. Los avisos de pantalla ---------------------------------------------
# Los metodos `onchange` SOLO se ejecutan desde el navegador: ninguna prueba de
# las de arriba los toca, porque todas trabajan contra el ORM. Un campo
# renombrado deja el aviso apuntando a un nombre que ya no existe y nadie se
# entera hasta que Ventas abre la pantalla y le revienta con un error rojo.
# Paso de verdad: `agrogood_vat_pending` se renombro a
# `agrogood_billing_blocked` y este aviso se quedo atras.
#
# Se ejecutan todos los onchange de los modulos propios sobre un registro
# virtual. Solo se persigue AttributeError: es el sintoma exacto de una
# referencia caduca. Cualquier otro fallo depende de los datos, no del codigo.
rotos = []
revisados = 0
# Se recorren TODOS los modelos y se filtra por los onchange nuestros, en vez
# de mantener a mano una lista de modelos. Esa lista es exactamente la misma
# clase de error que esta prueba persigue: la primera version se dejaba fuera
# `agrogood.price.version` -las versiones semanales de precios- y la prueba
# habria pasado en verde ignorando un tercio de los avisos que existen.
for _modelo in sorted(env.registry.models):
    _M = env[_modelo]
    # Se recorre la CLASE y no el conjunto de registros: pedirle un atributo
    # cualquiera a un recordset vacio hace que Odoo intente leer campos y
    # revienta antes de llegar a lo que interesa.
    _vistos = set()
    for _klass in type(_M).__mro__:
        for _nombre, _f in list(vars(_klass).items()):
            if _nombre in _vistos:
                continue
            if not callable(_f) or not hasattr(_f, '_onchange'):
                continue
            if 'agrogood' not in (getattr(_f, '__module__', '') or ''):
                continue       # los de Odoo son cosa de Odoo
            _vistos.add(_nombre)
            revisados += 1
            _vals = {}
            if 'partner_id' in _M._fields:
                _vals['partner_id'] = cliente.id
            try:
                getattr(_M.new(_vals), _nombre)()
            except AttributeError as _e:
                rotos.append('%s.%s -> %s' % (_modelo, _nombre, _e))
            except Exception:
                pass
paso(21, 'Los avisos de pantalla no apuntan a campos que ya no existen',
     not rotos,
     ('%d onchange propios revisados' % revisados) if not rotos
     else ' | '.join(rotos)[:150])

# --- Resultado --------------------------------------------------------------
print("\n" + "=" * 78)
correctos = sum(1 for _, _, v in R if v)
print(f"RESULTADO: {correctos}/{len(R)} pasos correctos")
fallos = [f"{n}. {t}" for n, t, v in R if not v]
if fallos:
    print("Fallan: " + " | ".join(fallos))
else:
    print("El criterio de aceptacion se cumple de punta a punta.")
print("=" * 78)

env.cr.rollback()
print("Prueba revertida: la base queda como estaba.")
