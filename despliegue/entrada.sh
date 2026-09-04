#!/bin/bash
# ===========================================================================
# Arranque del contenedor de Odoo: primero rellena la config, luego arranca.
#
# Por que existe: Odoo NO expande variables en odoo.conf. Un
# `admin_passwd = ${ADMIN_PASSWD}` se queda con ese texto tal cual, y la clave
# que se puso en el .env no se usa nunca. La contrasena maestra quedaba siendo,
# literalmente, la cadena "${ADMIN_PASSWD}".
#
# Aca se genera la config de verdad -metiendo los secretos del entorno en la
# plantilla- y recien entonces se arranca Odoo apuntando a ella. El archivo con
# los secretos se escribe en /tmp, que no se versiona ni sobrevive al
# contenedor: los secretos viven en el .env y en la memoria, nunca en Git.
#
# El reemplazo lo hace Python -que el contenedor ya trae- con replace() literal,
# no sed: una clave con /, & o cualquier signo raro rompe una sustitucion de
# sed y no rompe esta. Las claves salen de `openssl rand -base64`, que mete de
# esos signos.
# ===========================================================================
set -euo pipefail

PLANTILLA="/etc/odoo/odoo.conf.plantilla"
RENDERIZADA="/tmp/odoo-agroapp.conf"

python3 - "$PLANTILLA" "$RENDERIZADA" <<'PY'
import os, sys, pathlib

origen, destino = sys.argv[1], sys.argv[2]
texto = pathlib.Path(origen).read_text()

# Solo estos huecos, y todos tienen que venir en el entorno: si falta uno, se
# para aca con un error claro, en vez de arrancar con una clave vacia y
# descubrirlo cuando algo no conecta.
faltan = []
for clave in ("ADMIN_PASSWD", "DB_USER", "DB_PASSWORD"):
    valor = os.environ.get(clave)
    if not valor:
        faltan.append(clave)
        continue
    texto = texto.replace("${%s}" % clave, valor)

if faltan:
    sys.exit("Faltan variables en el entorno (.env): " + ", ".join(faltan))

salida = pathlib.Path(destino)
salida.write_text(texto)
salida.chmod(0o600)   # la config con los secretos no la lee cualquiera
PY

# Se le pasa la config generada al arranque normal de la imagen oficial de
# Odoo, que ademas espera a que Postgres este listo antes de arrancar.
exec /entrypoint.sh odoo -c "$RENDERIZADA"
