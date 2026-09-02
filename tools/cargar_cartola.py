"""Carga una cartola del banco desde la linea de ordenes.

    AGROGOOD_CARTOLA="C:/ruta/cartola.xlsx" odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/cargar_cartola.py

Por defecto SOLO INFORMA. Para escribir:  AGROGOOD_CARTOLA_MODO=escribir

Hace exactamente lo mismo que el boton "Cargar cartola del banco" de la
pantalla, porque usa el mismo asistente: si algo funciona aqui y falla alli, la
diferencia esta en la pantalla y no en el lector. Existe para la primera carga
-la del historico, que es grande y conviene lanzar de noche- y para poder
repetirla sin depender del navegador.

El archivo vive FUERA del repositorio. Lleva RUT, montos y numeros de cuenta de
terceros, y no se versiona nunca.
"""

import base64
import os
import time

RUTA = os.environ.get("AGROGOOD_CARTOLA", "")
ESCRIBIR = os.environ.get("AGROGOOD_CARTOLA_MODO") == "escribir"

print("=" * 74)
print("CARGA DE CARTOLA" + ("  [ESCRIBIENDO]" if ESCRIBIR else "  [SOLO INFORME]"))
print("=" * 74)

if not RUTA:
    print("Falta decir que archivo. Ejemplo:")
    print('   AGROGOOD_CARTOLA="C:/dev/cartola.xlsx" odoo-bin shell ...')
elif not os.path.exists(RUTA):
    print("No existe el archivo: %s" % RUTA)
else:
    print("Archivo: %s  (%.1f MB)" % (RUTA, os.path.getsize(RUTA) / 1048576.0))
    inicio = time.time()
    asistente = env['agrogood.bank.import'].create({
        'file': base64.b64encode(open(RUTA, "rb").read()),
        'filename': os.path.basename(RUTA),
    })
    asistente.action_cargar()
    print()
    print(asistente.result)
    print()
    print("Tardo %.0f segundos." % (time.time() - inicio))

    Mov = env['agrogood.bank.movement']
    pendientes = Mov.search([('state', 'in', ('unknown', 'doubtful'))])
    pagadores = {}
    for m in pendientes:
        clave = m.payer_rut or m.payer_alias or "(sin pagador)"
        pagadores.setdefault(clave, 0.0)
        pagadores[clave] += m.amount
    if pagadores:
        total = sum(pagadores.values())
        veinte = sorted(pagadores.values(), reverse=True)[:20]
        print()
        print("Quedan %d abonos sin identificar, de %d pagadores distintos."
              % (len(pendientes), len(pagadores)))
        print("Los 20 de mas monto concentran el %.0f%% de lo pendiente."
              % (100.0 * sum(veinte) / max(total, 1)))
        print("Enlazar esos veinte es la tarde mejor invertida del mes.")

    if not ESCRIBIR:
        env.cr.rollback()
        print()
        print("=" * 74)
        print("SOLO INFORME. Nada se ha guardado.")
        print("Para aplicar:  AGROGOOD_CARTOLA_MODO=escribir")
        print("=" * 74)
    else:
        env.cr.commit()
        print()
        print("=" * 74)
        print("Guardado. Los abonos estan en Paneles > Cobranza.")
        print("=" * 74)
