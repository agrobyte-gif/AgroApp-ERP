#!/bin/bash
# Restaura Agroapp desde un respaldo.
#
#   ./restaurar.sh respaldos/agroapp-20260824-0300.dump
#
# SOBRESCRIBE la base actual. Pide confirmacion escribiendo el nombre, no un
# "s/n": teclear "si" por inercia a las tres de la manana es demasiado facil.

set -euo pipefail
cd "$(dirname "$0")"

DUMP="${1:-}"
[ -z "$DUMP" ] && { echo "Uso: ./restaurar.sh respaldos/agroapp-FECHA.dump"; exit 1; }
[ -f "$DUMP" ] || { echo "No existe: $DUMP"; exit 1; }

ADJUNTOS="${DUMP/agroapp-/adjuntos-}"; ADJUNTOS="${ADJUNTOS/.dump/.tar.gz}"

echo "Se va a restaurar:"
echo "  base     : $DUMP"
echo "  adjuntos : $([ -f "$ADJUNTOS" ] && echo "$ADJUNTOS" || echo 'NO ENCONTRADOS - las fotos y firmas se perderan')"
echo
echo "Esto BORRA la base actual y todo lo hecho desde ese respaldo."
read -rp "Escribe   agroapp   para continuar: " CONF
[ "$CONF" = "agroapp" ] || { echo "Cancelado."; exit 1; }

echo "Parando Odoo para que no escriba durante la restauracion..."
docker compose stop odoo

docker compose exec -T db dropdb -U "${DB_USER:-odoo}" --if-exists agroapp
docker compose exec -T db createdb -U "${DB_USER:-odoo}" agroapp
docker compose exec -T db pg_restore -U "${DB_USER:-odoo}" -d agroapp --no-owner < "$DUMP"
echo "  base restaurada"

if [ -f "$ADJUNTOS" ]; then
    docker run --rm -v agroapp_odoo-datos:/datos \
        -v "$(pwd)/$(dirname "$ADJUNTOS")":/entrada \
        alpine sh -c "rm -rf /datos/* && tar xzf /entrada/$(basename "$ADJUNTOS") -C /datos"
    echo "  adjuntos restaurados"
fi

docker compose start odoo
echo "Listo. Comprueba en el navegador antes de dar por bueno."
