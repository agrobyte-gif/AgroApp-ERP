"""Prueba de la pantalla de Logistica: repartir y armar rutas.

    odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/prueba_logistica.py

Termina con rollback: no deja nada.

Comprueba que las dos acciones de Felipe -asignar Picker y armar la ruta- se
apoyan en los asistentes que ya existen y heredan sus guardias, en vez de
duplicar la logica en el controlador. Esas guardias son las que impiden asignar
dos veces el mismo albaran y cargar en el camion algo que aun no se ha
preparado.
"""

from odoo import fields
from odoo.exceptions import UserError, ValidationError

R = []
def paso(t, ok, det=""):
    R.append(ok); print("  [%s] %s" % ("OK " if ok else "FALLA", t))
    if det: print("        %s" % det)

print("=" * 74)
print("PANTALLA DE LOGISTICA - con el usuario real")
print("=" * 74)

felipe = env['res.users'].search([('login','=','felipe@agrogood.cl')], limit=1)
E = env(user=felipe)
paso("Felipe tiene el rol de Logistica",
     felipe.has_group('agrogood_base.group_agrogood_logistics_manager'))

# --- un pedido preparable ---
linea = env.ref('agrogood_base.business_line_horeca')
cliente = env['res.partner'].create({
    'name': 'CLIENTE PRUEBA LOGISTICA', 'is_company': True,
    'street': 'Barros Arana 100', 'city': 'CONCEPCION',
    'country_id': env.ref('base.cl').id,
    'vat': '76593894-5',
    'l10n_latam_identification_type_id': env.ref('l10n_cl.it_RUT').id,
    'l10n_cl_sii_taxpayer_type': '1', 'customer_rank': 1,
    'agrogood_business_line_id': linea.id,
    'property_product_pricelist': linea.pricelist_id.id,
})
prod = env['product.product'].search(
    [('is_storable','=',True),('tracking','=','none')], limit=1)
alm = env['stock.warehouse'].search([], limit=1)
q = env['stock.quant'].with_context(inventory_mode=True).create({
    'product_id': prod.id, 'location_id': alm.lot_stock_id.id,
    'inventory_quantity': 50.0})
q._apply_inventory()
pedido = env['sale.order'].create({
    'partner_id': cliente.id,
    'order_line': [(0, 0, {'product_id': prod.id, 'product_uom_qty': 5.0})]})
pedido.action_confirm()
alb = pedido.picking_ids[0]
paso("Hay un albaran de salida listo", alb.state == 'assigned', alb.name)

# --- asignar Picker ---
picker = env['res.users'].search([('login','=','picker.demo@agrogood.cl')], limit=1)
asis = E['agrogood.assign.picker'].create({
    'picking_ids': [(6, 0, alb.ids)], 'picker_id': picker.id})
asis.action_assign()
alb.invalidate_recordset()
paso("Logistica asigna el Picker", bool(alb.agrogood_session_id),
     "%s -> %s" % (alb.name, picker.name))

# asignar dos veces se rechaza: la guardia vive en el asistente
try:
    E['agrogood.assign.picker'].create({
        'picking_ids': [(6, 0, alb.ids)], 'picker_id': picker.id}).action_assign()
    doble = False
except (UserError, ValidationError):
    doble = True
paso("Asignarlo dos veces se rechaza", doble,
     "la guardia del asistente sigue actuando desde la pantalla nueva")

# --- una ruta no admite lo que no esta preparado ---
ruta = env['agrogood.route'].create({
    'driver_id': env['res.users'].search([('login','=','chofer.demo@agrogood.cl')], limit=1).id,
    'vehicle_id': env['fleet.vehicle'].search([], limit=1).id,
    'date': fields.Date.context_today(env.user)})
try:
    E['agrogood.route.add.pickings'].create({
        'route_id': ruta.id, 'picking_ids': [(6, 0, alb.ids)]}).action_add()
    sin_preparar = False
except (UserError, ValidationError):
    sin_preparar = True
paso("Un pedido a medio preparar NO entra en la ruta", sin_preparar,
     "cargarlo mandaria al conductor a buscar una caja que no existe")

# --- se prepara y ahora si ---
sesion = alb.agrogood_session_id[0]
sesion.action_start()
alb.move_ids.write({'agrogood_line_status': 'confirmed'})
for m in alb.move_ids:
    m.quantity = m.product_uom_qty
sesion.action_finish()
paso("El Picker termina la preparacion", sesion.state == 'done')

E['agrogood.route.add.pickings'].create({
    'route_id': ruta.id, 'picking_ids': [(6, 0, alb.ids)]}).action_add()
ruta.invalidate_recordset()
paso("Ya preparado, entra en la ruta", len(ruta.stop_ids) == 1,
     "%s con %s parada(s)" % (ruta.name, len(ruta.stop_ids)))

ruta.action_plan()
paso("La ruta calcula peso y ocupacion del camion", ruta.vehicle_capacity > 0,
     "%.0f kg de %.0f (%.0f%%)" % (ruta.estimated_weight, ruta.vehicle_capacity,
                                   ruta.capacity_usage))

# --- y sigue sin poder salir sin revisar el vehiculo ---
try:
    ruta.action_start()
    bloquea = False
except UserError:
    bloquea = True
paso("Sin revisar el vehiculo la ruta no arranca", bloquea,
     "la guardia de la revision tambien aplica desde la pantalla nueva")

print()
print("=" * 74)
print("RESULTADO: %d/%d" % (sum(1 for x in R if x), len(R)))
print("=" * 74)
env.cr.rollback()
print("Revertido.")
