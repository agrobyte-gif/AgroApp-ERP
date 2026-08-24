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
#    pierden los dos a la vez. Descomentar una de estas lineas.
#
# rclone copy "$DESTINO" remoto:agroapp-respaldos --max-age 25h
# aws s3 sync "$DESTINO" s3://agroapp-respaldos/ --exclude "*" --include "*$FECHA*"
