#!/bin/bash
# Respaldo diario de Agroapp: base de datos y archivos adjuntos.
#
# Se instala en cron:
#   0 3 * * * /opt/agroapp/despliegue/respaldar.sh >> /var/log/agroapp-respaldo.log 2>&1
#
# Guarda 14 dias en el servidor. Eso cubre el error humano -alguien borro algo
# el lunes y se dio cuenta el viernes- pero NO cubre que el servidor se pierda.
# Para eso hace falta copiar fuera, y por eso existe la seccion del final.

set -euo pipefail
cd "$(dirname "$0")"

FECHA=$(date +%Y%m%d-%H%M)
DESTINO="./respaldos"
DIAS=14

mkdir -p "$DESTINO"

echo "[$(date '+%F %T')] Iniciando respaldo $FECHA"

# 1. La base. Formato custom: comprime y permite restaurar tablas sueltas.
docker compose exec -T db pg_dump -U "${DB_USER:-odoo}" -Fc agroapp \
    > "$DESTINO/agroapp-$FECHA.dump"
echo "  base: $(du -h "$DESTINO/agroapp-$FECHA.dump" | cut -f1)"

# 2. Los adjuntos. Sin esto se restauraria una base que apunta a fotos de
#    entrega, firmas y PDF que ya no existen.
docker run --rm \
    -v agroapp_odoo-datos:/datos:ro \
    -v "$(pwd)/$DESTINO":/salida \
    alpine tar czf "/salida/adjuntos-$FECHA.tar.gz" -C /datos .
echo "  adjuntos: $(du -h "$DESTINO/adjuntos-$FECHA.tar.gz" | cut -f1)"

# 3. Rotacion
find "$DESTINO" -name "agroapp-*.dump" -mtime +$DIAS -delete
find "$DESTINO" -name "adjuntos-*.tar.gz" -mtime +$DIAS -delete

echo "[$(date '+%F %T')] Respaldo terminado. Copias guardadas: $(ls -1 "$DESTINO"/agroapp-*.dump 2>/dev/null | wc -l)"

# 4. FUERA DEL SERVIDOR.
#    Un respaldo que vive en la misma maquina que los datos no es un respaldo:
#    es una copia. Si el disco falla o el proveedor pierde la maquina, se
#    pierden los dos a la vez.
#
#    Se sube a Firebase Storage. La herramienta vuelve a leer el archivo del
#    bucket y compara tamano y hash, en vez de dar por hecho que llego: subir y
#    confiar es la forma habitual de descubrir el dia malo que el respaldo
#    estaba a medias. Comprueba ademas que no se pueda descargar sin
#    credenciales, porque el dump lleva los RUT, telefonos y deudas de toda la
#    cartera.
#
#    Hace falta config/firebase-clave.json. Ver docs/RESPALDO-FIREBASE.md.
#    Si falla, el respaldo local ya esta hecho: se avisa y se sigue.

CLAVE_FIREBASE="${AGROGOOD_FIREBASE_CLAVE:-../config/firebase-clave.json}"
if [ -f "$CLAVE_FIREBASE" ]; then
    AGROGOOD_FIREBASE=subir \
    AGROGOOD_RESPALDOS="$DESTINO" \
    AGROGOOD_FIREBASE_CLAVE="$CLAVE_FIREBASE" \
    python3 ../tools/subir_respaldo.py || \
        echo "  AVISO: no subio a Firebase. La copia del servidor si esta."
else
    echo "  Firebase: sin configurar (falta $CLAVE_FIREBASE)"
fi
