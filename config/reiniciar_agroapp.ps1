<#
    Reinicia Agroapp y AVISA si el servidor esta sirviendo codigo viejo.

        powershell -ExecutionPolicy Bypass -File C:\dev\agrogood\config\reiniciar_agroapp.ps1

    Por que existe: el recargador automatico de Odoo no recogio un cambio en un
    controlador y el servidor siguio sirviendo el codigo de dos horas antes
    contra las plantillas nuevas. La pagina daba error 500 y todo parecia estar
    al dia: los archivos estaban bien, la base estaba bien, y no habia forma de
    verlo sin mirar la hora del proceso.

    Por eso este script compara la hora de arranque del servidor con la del
    archivo de codigo mas reciente. Es la comprobacion que habria ahorrado esa
    tarde.

        -Comprobar   solo informa, no reinicia nada.
#>

param([switch]$Comprobar)

$ErrorActionPreference = 'Stop'
$RAIZ = "C:\dev\agrogood"

function Servidores {
    Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
        Where-Object { $_.CommandLine -like "*odoo-bin*" }
}

# El archivo de codigo propio mas reciente. Las plantillas XML no cuentan: esas
# se recargan con -u y no necesitan reinicio.
$masNuevo = Get-ChildItem "$RAIZ\addons_agrogood" -Recurse -Filter *.py |
            Where-Object { $_.FullName -notlike "*__pycache__*" } |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1

$vivos = Servidores
if ($vivos) {
    $arranque = ($vivos | Sort-Object CreationDate | Select-Object -First 1).CreationDate
    Write-Host "Servidor arrancado : $arranque"
    Write-Host "Codigo mas reciente: $($masNuevo.LastWriteTime)  ($($masNuevo.Name))"
    if ($masNuevo.LastWriteTime -gt $arranque) {
        Write-Host ""
        Write-Host "  EL SERVIDOR ESTA SIRVIENDO CODIGO VIEJO." -ForegroundColor Yellow
        Write-Host "  Hay codigo mas nuevo que el proceso. Hay que reiniciar."
    } else {
        Write-Host "  El servidor tiene el codigo actual."
    }
} else {
    Write-Host "No hay ningun servidor corriendo."
}

if ($Comprobar) { exit 0 }

if ($vivos) {
    Write-Host ""
    Write-Host "Deteniendo $($vivos.Count) proceso(s)..."
    $vivos | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 3
    if (Servidores) { Write-Error "No se pudieron detener todos los procesos"; exit 1 }
}

Write-Host "Arrancando..."
Start-Process -FilePath "$RAIZ\.venv\Scripts\python.exe" `
    -ArgumentList "$RAIZ\odoo-18.0\odoo-bin", "-c", "$RAIZ\config\odoo.conf" `
    -WindowStyle Hidden

# Se espera a que RESPONDA, no a que el proceso exista. Un proceso arrancado no
# es lo mismo que un servidor listo, y dar por bueno lo primero manda a la
# gente a una pagina que todavia no esta.
$listo = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 2
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8069/web/login" -TimeoutSec 5 `
             -UseBasicParsing -ErrorAction Stop
        if ($r.StatusCode -eq 200) { $listo = $true; break }
    } catch { }
}

if ($listo) {
    Write-Host ""
    Write-Host "Listo. Agroapp responde en:"
    Write-Host "   http://$env:COMPUTERNAME.local:8069/agrogood/app"
} else {
    Write-Host "El servidor no respondio en 80 segundos. Mirar logs\odoo.log"
    exit 1
}
