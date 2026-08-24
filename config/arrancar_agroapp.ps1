<#
    Arranca Agroapp en este equipo.

    Se instala como tarea programada al iniciar sesion, de modo que el servidor
    vuelva solo tras reiniciar o suspender el equipo. Sin esto hay que
    levantarlo a mano cada vez, y basta con olvidarse una manana para que el
    equipo crea que "el sistema no funciona".
#>
$RAIZ = "C:\dev\agrogood"

# Si ya hay uno corriendo, no se arranca otro: dos procesos sobre la misma base
# se pisan al escribir.
$vivo = Get-Process python -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -like "*agrogood*" }
if ($vivo) { Write-Host "Agroapp ya esta corriendo (PID $($vivo.Id -join ','))"; exit 0 }

# python.exe y NO pythonw.exe. pythonw no tiene flujos de salida, y Odoo
# escribe en ellos al arrancar: el proceso moria al instante sin dejar rastro
# ni en el log. Con -WindowStyle Hidden la consola existe pero no se ve.
Start-Process -FilePath "$RAIZ\.venv\Scripts\python.exe" `
    -ArgumentList "$RAIZ\odoo-18.0\odoo-bin", "-c", "$RAIZ\config\odoo.conf", "-d", "agrogood_dev" `
    -WorkingDirectory $RAIZ -WindowStyle Hidden

# Odoo tarda en cargar los 93 modulos; se espera hasta 60 s comprobando.
$arriba = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 3
    try {
        Invoke-WebRequest -Uri "http://localhost:8069/web/login" -TimeoutSec 4 -UseBasicParsing | Out-Null
        $arriba = $true; break
    } catch { }
}
try {
    if (-not $arriba) { throw "sin respuesta tras 60 segundos" }
    Invoke-WebRequest -Uri "http://localhost:8069/web/login" -TimeoutSec 10 -UseBasicParsing | Out-Null
    $ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
        (Get-NetAdapter -InterfaceIndex $_.InterfaceIndex -ErrorAction SilentlyContinue).Name -eq "Wi-Fi"
    }).IPAddress
    Write-Host "Agroapp arriba."
    Write-Host "  Escritorio : http://localhost:8069"
    if ($ip) { Write-Host "  Telefonos  : http://${ip}:8069/agrogood/app" }
} catch {
    Write-Host "Arranco pero aun no responde. Revisa C:\dev\agrogood\logs\odoo.log"
}
