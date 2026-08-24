<#
    Arranca Agroapp en este equipo.

    Se instala como tarea programada al iniciar sesion, de modo que el servidor
    vuelva solo tras reiniciar o suspender el equipo. Sin esto hay que
    levantarlo a mano cada vez, y basta con olvidarse una manana para que el
    equipo crea que "el sistema no funciona".
#>
$RAIZ = "C:\dev\agrogood"

# Si ya hay uno corriendo, no se arranca otro: dos procesos sobre la misma base
# se pisan al escribir y duplican las acciones programadas.
#
# Se mira la LINEA DE COMANDOS, no la ruta del ejecutable. La version anterior
# comparaba $_.Path contra "*agrogood*", y eso solo reconoce al Odoo lanzado
# con el Python del entorno virtual. Un Odoo arrancado a mano con el Python del
# sistema ("C:\Program Files\Python312\python.exe") pasaba desapercibido, y la
# tarea programada levantaba un segundo servidor encima. Ocurrio de verdad.
$vivo = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
        Where-Object { $_.CommandLine -like "*odoo-bin*" }
if ($vivo) { Write-Host "Agroapp ya esta corriendo (PID $($vivo.ProcessId -join ','))"; exit 0 }

# python.exe y NO pythonw.exe. pythonw no tiene flujos de salida, y Odoo
# escribe en ellos al arrancar: el proceso moria al instante sin dejar rastro
# ni en el log. Con -WindowStyle Hidden la consola existe pero no se ve.
Start-Process -FilePath "$RAIZ\.venv\Scripts\python.exe" `
    -ArgumentList "$RAIZ\odoo-18.0\odoo-bin", "-c", "$RAIZ\config\odoo.conf", "-d", "agrogood_dev" `
    -WorkingDirectory $RAIZ -WindowStyle Hidden

# Odoo tarda en cargar sus modulos; se espera hasta 60 s comprobando.
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
    # El nombre del equipo va PRIMERO y la IP como respaldo. El router reparte
    # las direcciones por DHCP y las cambia solas: el equipo paso de
    # 192.168.1.5 a 192.168.0.19 en un mismo dia, y con ello dejaron de
    # funcionar todos los telefonos a la vez sin que nadie hubiera tocado nada.
    # Windows publica su nombre por mDNS y Android lo resuelve, asi que
    # AGROGOOD.local sigue valiendo aunque cambie la IP.
    Write-Host "  Telefonos  : http://$env:COMPUTERNAME.local:8069/agrogood/app"
    if ($ip) { Write-Host "  Si el nombre falla, por IP: http://${ip}:8069/agrogood/app" }
} catch {
    Write-Host "Arranco pero aun no responde. Revisa C:\dev\agrogood\logs\odoo.log"
}
