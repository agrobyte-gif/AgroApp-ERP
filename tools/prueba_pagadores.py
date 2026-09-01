"""Prueba de las identidades de pago.

    odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/prueba_pagadores.py

Termina con rollback: no deja nada.

Un cliente no paga siempre desde la misma identidad -otra sociedad, el RUT del
dueno, o solo un nombre corto si el banco no publica el RUT-. Se comprueba que
el cruce reconoce todas ellas, que normaliza el RUT venga como venga, y que NO
se puede asignar la misma identidad a dos clientes: eso repartiria los cobros
al azar entre los dos.
"""

from odoo.exceptions import ValidationError
from psycopg2 import IntegrityError

R = []
def paso(t, ok, det=""):
    R.append(ok); print("  [%s] %s" % ("OK " if ok else "FALLA", t))
    if det: print("        %s" % det)

print("=" * 74)
print("IDENTIDADES DE PAGO")
print("=" * 74)

P = env['agrogood.payer']
linea = env.ref('agrogood_base.business_line_horeca')
cli = env['res.partner'].create({
    'name': 'CLIENTE PRUEBA PAGADORES', 'is_company': True,
    'agrogood_business_line_id': linea.id, 'customer_rank': 1,
    'vat': '76593894-5',
    'l10n_latam_identification_type_id': env.ref('l10n_cl.it_RUT').id,
    'l10n_cl_sii_taxpayer_type': '1',
})
otro = env['res.partner'].create({
    'name': 'OTRO CLIENTE PRUEBA', 'is_company': True,
    'agrogood_business_line_id': linea.id, 'customer_rank': 1,
})

# --- el RUT de la ficha cruza sin registrar nada ---
paso("El RUT de la ficha cruza sin configurar nada",
     P.buscar_cliente(rut='76593894-5') == cli)

# --- venga como venga ---
formas = ['76593894-5', '765938945', '76.593.894-5', ' 76593894 - 5 ']
paso("El RUT cruza escrito de cualquier forma",
     all(P.buscar_cliente(rut=f) == cli for f in formas),
     " / ".join(formas))

# --- un RUT que NO es el de su ficha ---
paso("Un RUT ajeno no cruza todavia",
     not P.buscar_cliente(rut='77253562-7'))
ident = P.create({'partner_id': cli.id, 'kind': 'rut', 'value': '77.253.562-7',
                  'bank': 'Scotiabank', 'note': 'Paga desde su otra sociedad'})
paso("Se guarda normalizado", ident.value == '77253562-7', ident.value)
paso("Y ahora si cruza", P.buscar_cliente(rut='772535627') == cli,
     "el mismo negocio pagando desde otro RUT")

# --- alias, para el banco que no publica RUT ---
P.create({'partner_id': cli.id, 'kind': 'alias', 'value': ' bar callejon ',
          'bank': 'Santander'})
paso("El alias del banco cruza", P.buscar_cliente(alias='BAR CALLEJON') == cli)
paso("Y no distingue mayusculas ni espacios",
     P.buscar_cliente(alias='  bar callejon  ') == cli)

# --- un RUT invalido no se admite ---
# Ojo al elegir el ejemplo: 11111111-1 SI es un RUT valido -su digito
# verificador da 1- y sirve de nada como caso negativo. Se usa el mismo RUT del
# cliente con el verificador cambiado, que es el error real que comete la gente.
try:
    P.create({'partner_id': cli.id, 'kind': 'rut', 'value': '76593894-9'})
    malo = False
except ValidationError:
    malo = True
paso("Un RUT con digito verificador malo se rechaza", malo,
     "76593894-9 cuando el correcto es -5")

# --- la misma identidad no puede ser de dos clientes ---
try:
    with env.cr.savepoint():
        P.create({'partner_id': otro.id, 'kind': 'rut', 'value': '77253562-7'})
    duplicada = False
except (IntegrityError, ValidationError):
    duplicada = True
paso("La misma identidad no puede apuntar a dos clientes", duplicada,
     "repartiria los cobros al azar entre los dos")

# --- se registra el uso ---
ident.registrar_uso()
paso("Se anota cada vez que se ve", ident.times_seen == 1 and bool(ident.last_seen),
     "visto %s vez, el %s" % (ident.times_seen, ident.last_seen))

print()
print("=" * 74)
print("RESULTADO: %d/%d" % (sum(1 for x in R if x), len(R)))
print("=" * 74)
env.cr.rollback()
print("Revertido.")
