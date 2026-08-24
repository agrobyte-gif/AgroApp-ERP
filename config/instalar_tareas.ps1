<#
    Instala las dos tareas programadas que hacen que el sistema aguante solo
    mientras se trabaja en este equipo:

      1. Arrancar Agroapp al iniciar sesion.
      2. Respaldar todos los dias a las 20:00.

    Ejecutar UNA VEZ, como administrador:
       powershell -ExecutionPolicy Bypass -File C:\dev\agrogood\config\instalar_tareas.ps1
#>
$ErrorActionPreference = 'Stop'
$RAIZ = "C:\dev\agrogood"
$PS   = "powershell.exe"

# --- Arranque automatico ---
$a1 = New-ScheduledTaskAction -Execute $PS `
      -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$RAIZ\config\arrancar_agroapp.ps1`""
$t1 = New-ScheduledTaskTrigger -AtLogOn
$s1 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
      -StartWhenAvailable -ExecutionTimeLimit 0
Register-ScheduledTask -TaskName "Agroapp - arrancar" -Action $a1 -Trigger $t1 -Settings $s1 `
    -Description "Levanta el servidor de Agroapp al iniciar sesion" -Force | Out-Null
Write-Host "1. Tarea de arranque instalada (al iniciar sesion)"

# --- Respaldo diario ---
# A las 20:00 y no de madrugada: el equipo suele estar apagado por la noche, y
# un respaldo programado a una hora en que la maquina duerme no se hace nunca.
$a2 = New-ScheduledTaskAction -Execute $PS `
      -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$RAIZ\config\respaldar_local.ps1`""
$t2 = New-ScheduledTaskTrigger -Daily -At 20:00
$s2 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
      -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "Agroapp - respaldo diario" -Action $a2 -Trigger $t2 -Settings $s2 `
    -Description "Respalda base y adjuntos, y copia a OneDrive" -Force | Out-Null
Write-Host "2. Tarea de respaldo instalada (todos los dias a las 20:00)"
Write-Host ""
Write-Host "   StartWhenAvailable esta activo: si el equipo estaba apagado a esa"
Write-Host "   hora, el respaldo se hace en cuanto se encienda."
Write-Host ""
Get-ScheduledTask -TaskName "Agroapp - *" | Select-Object TaskName, State | Format-Table -AutoSize
