<#
    Simulacro de restauracion: comprueba que el respaldo SIRVE.

        powershell -ExecutionPolicy Bypass -File C:\dev\agrogood\config\simulacro_restauracion.ps1

    Un respaldo que nadie ha restaurado nunca no es un respaldo: es un archivo
    del que se supone algo. Y el dia que haga falta es el peor dia posible para
    descubrir que no servia.

    Lo que hace, en orden, porque cada paso puede fallar sin que falle el
    anterior:

      1. Restaura el ultimo respaldo en una base APARTE. Nunca toca la real.
      2. Compara el contenido tabla por tabla contra la base viva.
      3. Comprueba que los archivos adjuntos -fotos de entrega, firmas- estan
         de verdad en el zip. Restaurar la base sin ellos deja un sistema
         lleno de enlaces rotos, y es el fallo mas habitual.
      4. Arranca Odoo contra la base restaurada. Una base que se restaura pero
         no levanta sigue siendo inutil.
      5. Borra la base del simulacro.

    Conviene correrlo despues de cada cambio grande, y una vez al mes sin
    excusa.
#>

$ErrorActionPreference = 'Stop'

$RAIZ  = "C:\dev\agrogood"
$PRUEBA = "agrogood_simulacro"
$VIVA   = "agrogood_dev"

$conf = Get-Content "$RAIZ\config\odoo.conf" -Raw
$usuario = ([regex]::Match($conf, '(?m)^db_user\s*=\s*(.+)$')).Groups[1].Value.Trim()
$clave   = ([regex]::Match($conf, '(?m)^db_password\s*=\s*(.+)$')).Groups[1].Value.Trim()
if (-not $clave) { Write-Error "No se pudo leer db_password de odoo.conf"; exit 1 }

$dump = (Get-ChildItem "$RAIZ\respaldos" -Filter "agrogood-*.dump" |
         Sort-Object LastWriteTime -Descending | Select-Object -First 1)
$zip  = (Get-ChildItem "$RAIZ\respaldos" -Filter "adjuntos-*.zip" |
         Sort-Object LastWriteTime -Descending | Select-Object -First 1)
if (-not $dump) { Write-Error "No hay ningun respaldo en $RAIZ\respaldos"; exit 1 }

Write-Host "=========================================================="
Write-Host "SIMULACRO DE RESTAURACION"
Write-Host "=========================================================="
Write-Host "  base    : $($dump.Name)  ($([math]::Round($dump.Length/1MB,1)) MB)"
if ($zip) { Write-Host "  adjuntos: $($zip.Name)  ($([math]::Round($zip.Length/1MB,1)) MB)" }
else { Write-Host "  adjuntos: NO HAY ZIP. Las fotos de entrega no estan respaldadas." }

# El trabajo pesado lo hace Python: comparar tablas y mirar dentro del zip es
# mas fiable ahi que encadenando psql en PowerShell.
& "$RAIZ\.venv\Scripts\python.exe" "$RAIZ\tools\simulacro_restauracion.py" `
    $dump.FullName $(if ($zip) { $zip.FullName } else { "" }) $PRUEBA $VIVA
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "EL SIMULACRO FALLO. El respaldo NO sirve tal cual esta."
    exit 1
}

Write-Host ""
Write-Host "Arrancando Odoo contra la base restaurada..."
& "$RAIZ\.venv\Scripts\python.exe" "$RAIZ\odoo-18.0\odoo-bin" `
    -c "$RAIZ\config\odoo.conf" -d $PRUEBA --stop-after-init --no-http --log-level=warn
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Odoo NO pudo arrancar contra la base restaurada."
    exit 1
}
Write-Host "  Odoo arranca correctamente."

& "$RAIZ\.venv\Scripts\python.exe" "$RAIZ\tools\simulacro_restauracion.py" --limpiar $PRUEBA

Write-Host ""
Write-Host "=========================================================="
Write-Host "EL RESPALDO SIRVE. Base del simulacro eliminada."
Write-Host "=========================================================="
