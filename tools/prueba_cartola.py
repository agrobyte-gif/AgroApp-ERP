"""Prueba de la conciliacion de cobros.

    odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/prueba_cartola.py

Termina con rollback: no deja nada.

Se prueba con filas inventadas, no con la cartola real. La cartola lleva RUT,
montos y numeros de cuenta de terceros y vive fuera del repositorio; una prueba
que dependiera de ella no se podria ejecutar en otra maquina ni en un servidor.
Los RUT de aqui son validos pero de nadie: el digito verificador se
calculo, no se invento. Un RUT de prueba con el digito equivocado hace
fallar la prueba por el motivo equivocado, y se pierde media tarde
buscando el fallo en el codigo que si estaba bien.

Lo que se comprueba, en orden de lo que cuesta si falla:

 1. Que un cargo no entre nunca como cobro.
 2. Que el RUT relleno de ceros de Santander sea el mismo pagador que el
    escrito con puntos y guion.
 3. Que un pagador que ya se vio pagando por dos clientes deje de asignarse
    solo, en vez de repartir el cobro al azar entre los dos.
 4. Que enlazar uno a mano resuelva los demas del mismo pagador.
"""

from odoo.exceptions import ValidationError

import sys
sys.path.insert(0, "addons_agrogood/agrogood_bank/models")

R = []


def paso(t, ok, det=""):
    R.append(ok)
    print("  [%s] %s" % ("OK " if ok else "FALLA", t))
    if det:
        print("        %s" % det)


print("=" * 74)
print("CONCILIACION DE COBROS")
print("=" * 74)

cartola = __import__('odoo.addons.agrogood_bank.models.cartola',
                     fromlist=['cartola'])

# ---------------------------------------------------------------- 1. lector
print()
print("EL LECTOR")

paso("RUT relleno de ceros de Santander",
     cartola.leer_rut("00763341712") == "76334171-2",
     cartola.leer_rut("00763341712"))
paso("El mismo RUT con puntos y guion da lo mismo",
     cartola.leer_rut("76.334.171-2") == cartola.leer_rut("00763341712"))
paso("Un numero de cuenta no pasa por RUT",
     cartola.leer_rut("000000000") is None)
paso("Un RUT con digito verificador falso se rechaza",
     cartola.leer_rut("76334171-5") is None)
paso("Monto con signo peso y puntos",
     cartola.leer_monto("$ 49.000") == 49000.0)
paso("Fecha en los dos formatos",
     cartola.leer_fecha("22-06-2026") == cartola.leer_fecha("22/06/2026"))
paso("Una celda que no es fecha no revienta",
     cartola.leer_fecha("Saldo final") is None)

# Una hoja de Scotiabank: cabecera, filas en blanco, datos, y al final el
# bloque con las columnas corridas que trae el archivo de verdad.
hoja_scotia = [
    ("Fecha", "Tipo", "Cta. Abono", "Rut Origen", "Nombre", "Banco Origen",
     "Cta. Origen", "Monto", "ESTADO", "CLIENTE"),
    (None,) * 10,
    ("22-06-2026", "TRANSFERENCIA", "977117771", "783444062", "SOCIEDAD UNO",
     "BANCO X", "37251607", "$ 49.000", "rebajado", "LOCAL UNO"),
    ("22-06-2026", "TRANSFERENCIA", "977117771", "783444062", "SOCIEDAD UNO",
     "BANCO X", "37251607", "$ 49.000", "rebajado", "LOCAL UNO"),
    ("TOTALES", "", "", "", "", "", "", "$ 98.000", "", ""),
]
abonos, descartes = cartola.leer_hoja(hoja_scotia, "scotiabank")
paso("Scotiabank: se leen los abonos y se salta la fila de totales",
     len(abonos) == 2 and descartes['sin_fecha'] == 2,
     "abonos=%d sin_fecha=%d" % (len(abonos), descartes['sin_fecha']))
paso("Se reconoce el banco por la cabecera, no por el nombre de la hoja",
     abonos and abonos[0]['banco'] == 'scotiabank')
paso("Dos transferencias identicas el mismo dia no se pisan",
     len({a['clave'] for a in abonos}) == 2)

hoja_santander = [
    ("MONTO", "DESCRIPCION MOVIMIENTO", "FECHA", "SALDO", "N DOCUMENTO",
     "SUCURSAL", "CARGO/ABONO", "ESTADO", "CLIENTE"),
    (390000, "00763341712 Pago factura", "31/08/2026", 2542697, "000000000",
     "CENTRAL", "A", "REBAJADO", "LOCAL DOS"),
    (-100, "0165135253 Transf a proveedor", "31/08/2026", 164883, "000000000",
     "AGUSTINAS", "C", "CARGO", "CARGO"),
    (594563, "29/08/26 CIERRE ABONO", "31/08/2026", 2751733, "000000000",
     "RENACA", "A", "REBAJADO", "VENTA"),
]
abonos_s, descartes_s = cartola.leer_hoja(hoja_santander, "santander")
paso("Santander: el cargo no entra como cobro",
     len(abonos_s) == 2 and descartes_s['cargos'] == 1,
     "abonos=%d cargos=%d" % (len(abonos_s), descartes_s['cargos']))
paso("Santander: el RUT sale de la descripcion",
     abonos_s and abonos_s[0]['rut'] == "76334171-2")
paso("'VENTA' no se toma por el nombre de un cliente",
     len(abonos_s) > 1 and abonos_s[1]['alias'] == "")
paso("Un cierre de abono queda sin pagador, para que alguien lo mire",
     len(abonos_s) > 1 and abonos_s[1]['rut'] is None)

# ------------------------------------------------------- 2. identificacion
print()
print("QUIEN PAGO")

Identidad = env['agrogood.payer']
Socio = env['res.partner']
linea = env.ref('agrogood_base.business_line_horeca')

uno = Socio.create({'name': 'LOCAL UNO PRUEBA', 'is_company': True,
                    'customer_rank': 1, 'vat': '76593894-5',
                    'agrogood_business_line_id': linea.id})
dos = Socio.create({'name': 'LOCAL DOS PRUEBA', 'is_company': True,
                    'customer_rank': 1,
                    'agrogood_business_line_id': linea.id})

socio, motivo = Identidad.resolver(rut='76.593.894-5')
paso("El RUT de la ficha identifica sin configurar nada",
     socio == uno and motivo == 'rut_ficha', motivo)

Identidad.aprender(dos, rut='78344406-2', alias='LOCAL DOS', bank='santander')
socio, motivo = Identidad.resolver(rut='00783444062')
paso("Un RUT enlazado a mano identifica aunque venga relleno de ceros",
     socio == dos and motivo == 'rut_aprendido', motivo)
socio, motivo = Identidad.resolver(alias='local dos')
paso("El nombre del banco identifica sin importar mayusculas",
     socio == dos and motivo == 'alias_aprendido', motivo)

socio, motivo = Identidad.resolver(rut='76.593.894-5', alias='LOCAL DOS')
paso("Si el RUT dice uno y el nombre dice otro, no se elige ninguno",
     not socio and motivo == 'discrepan', motivo)

# El caso que aparecio en la cartola real: 108 de 523 RUT pagaron por mas de un
# negocio. El segundo enlace no roba la identidad ni crea una duplicada: la
# marca compartida, y desde entonces ese RUT espera a una persona.
Identidad.aprender(uno, rut='78344406-2', alias='LOCAL UNO', bank='santander')
compartida = Identidad.search([('kind', '=', 'rut'), ('value', '=', '78344406-2')])
paso("Un RUT que paga por dos clientes queda marcado como compartido",
     len(compartida) == 1 and compartida.is_shared,
     "identidades=%d compartida=%s" % (len(compartida), compartida.is_shared))
paso("La identidad compartida sigue siendo del primero, no se la roba el segundo",
     compartida.partner_id == dos)
socio, motivo = Identidad.resolver(rut='78344406-2')
paso("Un RUT compartido deja de asignar solo",
     not socio and motivo == 'compartida', motivo)
socio, motivo = Identidad.resolver(rut='78344406-2', alias='LOCAL UNO')
paso("...pero con el nombre delante ya no hay duda",
     socio == uno, motivo)

try:
    Identidad.create({'partner_id': uno.id, 'kind': 'rut', 'value': '11.111.111'})
    paso("Un RUT invalido se rechaza", False, "se acepto")
except ValidationError:
    paso("Un RUT invalido se rechaza", True)

# ------------------------------------------------------------ 3. los abonos
print()
print("LOS ABONOS")

Movimiento = env['agrogood.bank.movement']
lote = Movimiento.create([{
    'bank': 'santander', 'date': '2026-08-31', 'amount': m,
    'payer_rut': '77.716.841-K', 'payer_alias': 'LOCAL TRES',
    'unique_key': 'prueba|%d' % m,
} for m in (390000, 120000, 55000)])
lote._cruzar()
paso("Un pagador que nadie conoce queda sin identificar",
     all(m.state == 'unknown' for m in lote))

tres = Socio.create({'name': 'LOCAL TRES PRUEBA', 'is_company': True,
                     'customer_rank': 1,
                     'agrogood_business_line_id': linea.id})
lote[0].partner_id = tres
paso("Enlazar a mano deja el abono identificado",
     lote[0].state == 'identified' and 'persona' in (lote[0].match_reason or ''),
     lote[0].match_reason)
aprendidas = Identidad.search([('partner_id', '=', tres.id)])
paso("Enlazar a mano ensena el RUT y el nombre a la vez",
     len(aprendidas) == 2 and set(aprendidas.mapped('kind')) == {'rut', 'alias'},
     "identidades aprendidas: %d" % len(aprendidas))

cambiados = lote[1:]._cruzar()
paso("Volver a cruzar resuelve los demas abonos del mismo pagador",
     cambiados == 2 and all(m.partner_id == tres for m in lote[1:]),
     "cambiados=%d" % cambiados)

lote[2].action_descartar()
lote[2]._cruzar()
paso("Lo descartado a mano no vuelve a cruzarse solo",
     lote[2].state == 'discarded' and not lote[2].partner_id)

try:
    Movimiento.create({
        'bank': 'santander', 'date': '2026-08-31', 'amount': 390000,
        'unique_key': 'prueba|390000'})
    env.cr.flush()
    paso("El mismo abono no entra dos veces", False, "se acepto duplicado")
except Exception:
    env.cr.rollback()
    paso("El mismo abono no entra dos veces", True,
         "la comprobacion deshizo la transaccion; el resto ya se probo")

print()
print("=" * 74)
print("%d de %d comprobaciones" % (sum(1 for x in R if x), len(R)))
print("=" * 74)
if all(R):
    print("La conciliacion hace lo que dice.")
else:
    print("HAY FALLOS. Revisar arriba.")

env.cr.rollback()
