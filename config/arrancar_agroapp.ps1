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

Start-Process -FilePath "$RAIZ\.venv\Scripts\pythonw.exe" `
    -ArgumentList "$RAIZ\odoo-18.0\odoo-bin", "-c", "$RAIZ\config\odoo.conf", "-d", "agrogood_dev" `
    -WorkingDirectory $RAIZ -WindowStyle Hidden

Start-Sleep -Seconds 12
try {
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
