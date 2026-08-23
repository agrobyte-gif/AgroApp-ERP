"""Elimina de la base los rastros de las pruebas de desarrollo.

    AGROGOOD_LIMPIAR=si odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/limpiar_datos_prueba.py

Conserva intactos los datos maestros reales -clientes, productos, tarifas,
usuarios del equipo- y borra unicamente lo que crearon las pruebas: pedidos,
albaranes, rutas, solicitudes, seguimientos, usuarios y vehiculos de ensayo.

Por defecto solo informa. Para borrar de verdad hay que pasar la variable.
"""

import os

BORRAR = os.environ.get("AGROGOOD_LIMPIAR") == "si"

print("=" * 76)
print("LIMPIEZA DE DATOS DE PRUEBA" + ("  [BORRANDO]" if BORRAR else "  [SOLO INFORME]"))
print("=" * 76)

# El orden importa: primero lo que depende de otra cosa.
objetivos = [
    ("agrogood.followup", []),
    ("agrogood.route.stop", []),
    ("agrogood.route", []),
    ("agrogood.purchase.request", []),
    ("agrogood.picking.session", []),
]

# Documentos: hay que cancelarlos antes de poder borrarlos.
print("\nDOCUMENTOS")
facturas = env['account.move'].search([('move_type', '!=', 'entry')])
print(f"  facturas y notas       : {len(facturas)}")
compras = env['purchase.order'].search([])
print(f"  ordenes de compra      : {len(compras)}")
ventas = env['sale.order'].search([])
print(f"  pedidos de venta       : {len(ventas)}")
albaranes = env['stock.picking'].search([])
print(f"  albaranes              : {len(albaranes)}")

print("\nOPERACIONES AGROGOOD")
for modelo, dominio in objetivos:
    print(f"  {modelo:<28} : {env[modelo].search_count(dominio)}")

# Usuarios y maestros creados por las pruebas, reconocibles por su login o
# nombre. Los del equipo real (victor, felipe, matias, johan, yere, sebastian)
# no llevan estas marcas y se conservan.
marcas_login = ['test.', 'picker.demo', 'chofer.demo', 'picker.integral',
                'chofer.integral', 'prueba.']
usuarios = env['res.users'].search([]).filtered(
    lambda u: any(m in (u.login or '') for m in marcas_login))
socios_prueba = env['res.partner'].search([
    '|', '|', ('name', 'ilike', 'TEST '), ('name', 'ilike', 'PRUEBA'),
    ('name', 'ilike', 'Integral')])
productos_prueba = env['product.template'].search([
    '|', ('default_code', 'like', 'TEST-'), ('name', 'ilike', 'PRUEBA')])
vehiculos = env['fleet.vehicle'].search([
    ('license_plate', 'in', ['TEST-01', 'DEMO-01', 'INT-01'])])

print("\nMAESTROS DE PRUEBA")
print(f"  usuarios               : {len(usuarios)}  "
      f"{', '.join(usuarios.mapped('login'))[:60]}")
print(f"  contactos              : {len(socios_prueba)}  "
      f"{', '.join(socios_prueba.mapped('name'))[:60]}")
print(f"  productos              : {len(productos_prueba)}")
print(f"  vehiculos              : {len(vehiculos)}")

if not BORRAR:
    print("\n" + "=" * 76)
    print("Solo informe. Para borrar: AGROGOOD_LIMPIAR=si")
    print("=" * 76)
else:
    print("\nBORRANDO...")
    # Facturas: hay que revertir el asiento antes de eliminar.
    facturas.filtered(lambda f: f.state == 'posted').button_draft()
    facturas.filtered(lambda f: f.state != 'cancel').button_cancel()
    facturas.unlink()
    print("  facturas eliminadas")

    for modelo, dominio in objetivos:
        env[modelo].search(dominio).unlink()
    print("  operaciones Agrogood eliminadas")

    ventas.filtered(lambda o: o.state != 'cancel')._action_cancel()
    ventas.unlink()
    compras.filtered(lambda o: o.state not in ('cancel',)).button_cancel()
    compras.unlink()
    print("  pedidos y compras eliminados")

    albaranes = env['stock.picking'].search([])
    albaranes.filtered(lambda p: p.state != 'cancel').action_cancel()
    albaranes.unlink()
    # Los movimientos ya hechos no se pueden borrar sin romper la valoracion,
    # asi que el stock se deja en cero mediante un ajuste, que es lo que se
    # haria en la vida real.
    quants = env['stock.quant'].search([
        ('location_id.usage', '=', 'internal'), ('quantity', '!=', 0)])
    if quants:
        quants.with_context(inventory_mode=True).write({'inventory_quantity': 0})
        quants.with_context(inventory_mode=True)._apply_inventory()
    print("  albaranes eliminados y stock puesto a cero")

    vehiculos.unlink()
    productos_prueba.unlink()
    socios_prueba.unlink()
    usuarios.unlink()
    print("  maestros de prueba eliminados")

    env.cr.commit()
    print("\n" + "=" * 76)
    print("BASE LIMPIA")
    print(f"  clientes reales   : "
          f"{env['res.partner'].search_count([('agrogood_business_line_id', '!=', False)])}")
    print(f"  productos reales  : "
          f"{env['product.template'].search_count([('default_code', '!=', False)])}")
    print(f"  pedidos           : {env['sale.order'].search_count([])}")
    print(f"  usuarios del equipo: "
          f"{', '.join(env['res.users'].search([('login', 'like', '@agrogood.cl')]).mapped('login'))}")
    print("=" * 76)
