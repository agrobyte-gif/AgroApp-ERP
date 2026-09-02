<#
    Respaldo local de Agroapp mientras se trabaja en este equipo.

    Guarda base de datos Y archivos adjuntos. Sin los adjuntos se restauraria
    una base que apunta a fotos de entrega, firmas y logos que ya no existen.

    Se instala como tarea programada con: config\instalar_tareas.ps1
    O se ejecuta a mano cuando se quiera:
        powershell -ExecutionPolicy Bypass -File C:\dev\agrogood\config\respaldar_local.ps1
#>

$ErrorActionPreference = 'Stop'

$RAIZ      = "C:\dev\agrogood"
$DESTINO   = "$RAIZ\respaldos"
$PSQL_BIN  = "C:\Program Files\PostgreSQL\17\bin"
$BASE      = "agrogood_dev"
$DIAS      = 21

New-Item -ItemType Directory -Force $DESTINO | Out-Null
$FECHA = Get-Date -Format "yyyyMMdd-HHmm"

# La clave se lee de odoo.conf, que es donde ya vive. Asi no hay una segunda
# copia de la contrasena en otro archivo que alguien tenga que mantener.
$conf = Get-Content "$RAIZ\config\odoo.conf" -Raw
$usuario = ([regex]::Match($conf, '(?m)^db_user\s*=\s*(.+)$')).Groups[1].Value.Trim()
$clave   = ([regex]::Match($conf, '(?m)^db_password\s*=\s*(.+)$')).Groups[1].Value.Trim()

if (-not $clave) { Write-Error "No se pudo leer db_password de odoo.conf"; exit 1 }

Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Respaldando $BASE..."

# --- 1. Base de datos ---------------------------------------------------
$env:PGPASSWORD = $clave
$dump = "$DESTINO\agrogood-$FECHA.dump"
& "$PSQL_BIN\pg_dump.exe" -U $usuario -h localhost -Fc $BASE -f $dump
$env:PGPASSWORD = $null

if (-not (Test-Path $dump)) { Write-Error "El respaldo de la base fallo"; exit 1 }
"  base     : {0:N1} MB" -f ((Get-Item $dump).Length / 1MB) | Write-Host

# --- 2. Adjuntos --------------------------------------------------------
# El filestore guarda fotos de entrega, firmas y logos. Restaurar sin el deja
# una base llena de enlaces rotos.
$zip = "$DESTINO\adjuntos-$FECHA.zip"
if (Test-Path "$RAIZ\filestore") {
    Compress-Archive -Path "$RAIZ\filestore\*" -DestinationPath $zip -Force -ErrorAction SilentlyContinue
    if (Test-Path $zip) { "  adjuntos : {0:N1} MB" -f ((Get-Item $zip).Length / 1MB) | Write-Host }
} else {
    Write-Host "  adjuntos : sin filestore todavia"
}

# --- 3. Rotacion --------------------------------------------------------
$limite = (Get-Date).AddDays(-$DIAS)
Get-ChildItem $DESTINO -Filter "agrogood-*.dump" | Where-Object { $_.LastWriteTime -lt $limite } | Remove-Item
Get-ChildItem $DESTINO -Filter "adjuntos-*.zip"  | Where-Object { $_.LastWriteTime -lt $limite } | Remove-Item

$n = (Get-ChildItem $DESTINO -Filter "agrogood-*.dump").Count
Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Listo. $n copias guardadas (se conservan $DIAS dias)."

# --- 4. Copia fuera del equipo -----------------------------------------
# Un respaldo en el mismo disco que los datos no es un respaldo: si el disco
# falla, se pierden los dos. OneDrive ya esta en este equipo y sincroniza solo,
# asi que basta con dejar ahi la copia mas reciente.
$NUBE = "$env:USERPROFILE\OneDrive\Respaldos Agroapp"
if (Test-Path "$env:USERPROFILE\OneDrive") {
    New-Item -ItemType Directory -Force $NUBE | Out-Null
    Copy-Item $dump "$NUBE\" -Force
    if (Test-Path $zip) { Copy-Item $zip "$NUBE\" -Force }
    # En la nube se guardan menos copias: es red de seguridad, no archivo.
    Get-ChildItem $NUBE -Filter "*.dump" | Sort-Object LastWriteTime -Descending |
        Select-Object -Skip 7 | Remove-Item -ErrorAction SilentlyContinue
    Get-ChildItem $NUBE -Filter "*.zip" | Sort-Object LastWriteTime -Descending |
        Select-Object -Skip 7 | Remove-Item -ErrorAction SilentlyContinue
    Write-Host "  copiado a OneDrive (7 copias mas recientes)"
} else {
    Write-Host "  AVISO: sin OneDrive. El respaldo vive en el mismo disco que los datos."
}

# --- 5. Copia en Firebase ----------------------------------------------
# OneDrive cuelga de la cuenta personal de quien tiene el equipo: si esa
# persona se va, cambia de cuenta o llena su espacio, los respaldos se van con
# ella y nadie se entera. El bucket de Firebase es del proyecto.
#
# Si esto falla NO se cae el respaldo local, que ya esta hecho y es lo que
# importa. Pero se dice fuerte: un respaldo remoto que lleva semanas sin subir
# es la forma silenciosa de no tener respaldo remoto.
if (Test-Path "$RAIZ\config\firebase-clave.json") {
    $env:AGROGOOD_FIREBASE = "subir"
    & "$RAIZ\.venv\Scripts\python.exe" "$RAIZ\tools\subir_respaldo.py"
    $env:AGROGOOD_FIREBASE = $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  AVISO: el respaldo NO subio a Firebase. La copia local si esta."
    }
} else {
    Write-Host "  Firebase: sin configurar (falta config\firebase-clave.json)"
}
