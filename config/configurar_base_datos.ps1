<#
    Agrogood - configuracion de la base de datos
    -------------------------------------------------------------------------
    Crea el rol 'odoo' y la base 'agrogood_dev' en PostgreSQL, y deja
    odoo.conf listo para arrancar.

    Solo se te preguntan DOS cosas:
      1. La clave del superusuario 'postgres' (la que definiste al instalar
         PostgreSQL 17). Se usa una vez y no se guarda en ningun sitio.
      2. La clave que quieras para el rol 'odoo' (la eliges tu ahora).

    Es seguro ejecutarlo varias veces: si el rol o la base ya existen, no los
    duplica ni los pisa.

    Uso:  powershell -ExecutionPolicy Bypass -File C:\dev\agrogood\config\configurar_base_datos.ps1
#>

$ErrorActionPreference = 'Stop'

# --- Parametros del proyecto -------------------------------------------------
$PsqlExe  = 'C:\Program Files\PostgreSQL\17\bin\psql.exe'
$DbHost   = 'localhost'
$DbPort   = '5432'
$RoleName = 'odoo'
$DbName   = 'agrogood_dev'
$ConfFile = 'C:\dev\agrogood\config\odoo.conf'

function Write-Paso  { param($m) Write-Host "`n==> $m" -ForegroundColor Cyan }
function Write-Ok    { param($m) Write-Host "    OK   $m" -ForegroundColor Green }
function Write-Aviso { param($m) Write-Host "    !    $m" -ForegroundColor Yellow }
function Write-Malo  { param($m) Write-Host "    X    $m" -ForegroundColor Red }

function ConvertFrom-SecureStringPlain {
    param([System.Security.SecureString]$Secure)
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try   { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

# Ejecuta SQL como 'postgres'. Devuelve la salida; lanza excepcion si falla.
function Invoke-Psql {
    param([string]$Sql, [string]$Database = 'postgres')
    $salida = & $PsqlExe -U postgres -h $DbHost -p $DbPort -d $Database `
                         -v ON_ERROR_STOP=1 -t -A -c $Sql
    if ($LASTEXITCODE -ne 0) { throw "psql fallo: $salida" }
    return ($salida | Out-String).Trim()
}

Write-Host ""
Write-Host "  Agrogood - configuracion de la base de datos" -ForegroundColor White
Write-Host "  ---------------------------------------------"

# --- 0. Comprobaciones previas ----------------------------------------------
Write-Paso "Comprobando el entorno"

if (-not (Test-Path $PsqlExe)) {
    Write-Malo "No encuentro psql en: $PsqlExe"
    Write-Host "    Revisa la version de PostgreSQL instalada y ajusta la ruta arriba."
    exit 1
}
Write-Ok "psql encontrado"

$svc = Get-Service -Name 'postgresql-17' -ErrorAction SilentlyContinue
if (-not $svc) { Write-Malo "El servicio postgresql-17 no existe."; exit 1 }
if ($svc.Status -ne 'Running') {
    Write-Aviso "El servicio esta detenido. Intentando iniciarlo..."
    try { Start-Service postgresql-17; Write-Ok "Servicio iniciado" }
    catch { Write-Malo "No se pudo iniciar. Abre PowerShell como administrador."; exit 1 }
} else {
    Write-Ok "Servicio postgresql-17 en ejecucion"
}

if (-not (Test-Path $ConfFile)) { Write-Malo "No encuentro $ConfFile"; exit 1 }
Write-Ok "odoo.conf encontrado"

# --- 1. Clave del superusuario ----------------------------------------------
Write-Paso "Clave del superusuario 'postgres'"
Write-Host "    Es la que definiste al INSTALAR PostgreSQL 17."
Write-Host "    No es la del rol 'odoo': esa te la pido despues."
Write-Host "    Se usa solo para esta operacion y no se guarda."

$intentos = 0
while ($true) {
    $intentos++
    $secPostgres = Read-Host "    Clave de 'postgres'" -AsSecureString
    $env:PGPASSWORD = ConvertFrom-SecureStringPlain $secPostgres
    try {
        $v = Invoke-Psql "SELECT version();"
        Write-Ok "Conexion correcta"
        Write-Host "         $($v.Substring(0, [Math]::Min(60, $v.Length)))..."
        break
    } catch {
        $env:PGPASSWORD = $null
        Write-Malo "No se pudo conectar. Clave incorrecta o servidor inaccesible."
        if ($intentos -ge 3) {
            Write-Host ""
            Write-Host "    Si no recuerdas la clave de 'postgres', hay que restablecerla" -ForegroundColor Yellow
            Write-Host "    editando pg_hba.conf. Dimelo y te guio paso a paso." -ForegroundColor Yellow
            exit 1
        }
    }
}

# --- 2. Clave para el rol odoo ----------------------------------------------
Write-Paso "Clave NUEVA para el rol 'odoo'"
Write-Host "    La eliges tu ahora. Se guardara en odoo.conf para que Odoo la use."

while ($true) {
    $sec1 = Read-Host "    Clave para 'odoo'" -AsSecureString
    $sec2 = Read-Host "    Repitela" -AsSecureString
    $p1 = ConvertFrom-SecureStringPlain $sec1
    $p2 = ConvertFrom-SecureStringPlain $sec2
    if ($p1 -ne $p2)      { Write-Malo "No coinciden. Prueba otra vez."; continue }
    if ($p1.Length -lt 8) { Write-Malo "Usa al menos 8 caracteres."; continue }
    $OdooPassword = $p1
    break
}
Write-Ok "Clave aceptada"

# --- 3. Clave maestra de Odoo -----------------------------------------------
Write-Paso "Clave maestra de Odoo (admin_passwd)"
Write-Host "    Protege crear, duplicar y borrar bases desde el navegador."
Write-Host "    No tiene relacion con PostgreSQL. Pulsa Enter para generarla."

$secMaster = Read-Host "    Clave maestra (Enter = generar)" -AsSecureString
$MasterPassword = ConvertFrom-SecureStringPlain $secMaster
if ([string]::IsNullOrWhiteSpace($MasterPassword)) {
    Add-Type -AssemblyName System.Web
    $MasterPassword = [System.Web.Security.Membership]::GeneratePassword(20, 4)
    Write-Ok "Generada automaticamente y guardada en odoo.conf"
} else {
    Write-Ok "Clave maestra aceptada"
}

# --- 4. Crear el rol ---------------------------------------------------------
Write-Paso "Creando el rol '$RoleName'"

# Las comillas simples se duplican para que la clave sea un literal SQL valido.
$sqlPass = $OdooPassword.Replace("'", "''")

$existeRol = Invoke-Psql "SELECT 1 FROM pg_roles WHERE rolname = '$RoleName';"
if ($existeRol -eq '1') {
    Write-Aviso "El rol ya existia. Actualizo su clave para que coincida con odoo.conf."
    Invoke-Psql "ALTER ROLE $RoleName WITH LOGIN CREATEDB PASSWORD '$sqlPass';" | Out-Null
    Write-Ok "Clave del rol actualizada"
} else {
    # CREATEDB es necesario porque Odoo crea y restaura bases desde su gestor.
    # No se concede SUPERUSER: Odoo no lo requiere y limitarlo acota el dano
    # si esta credencial se filtra.
    Invoke-Psql "CREATE ROLE $RoleName WITH LOGIN CREATEDB PASSWORD '$sqlPass';" | Out-Null
    Write-Ok "Rol '$RoleName' creado con permiso CREATEDB, sin SUPERUSER"
}

# --- 5. Crear la base --------------------------------------------------------
Write-Paso "Creando la base '$DbName'"

$existeDb = Invoke-Psql "SELECT 1 FROM pg_database WHERE datname = '$DbName';"
if ($existeDb -eq '1') {
    Write-Aviso "La base '$DbName' ya existia. No se toca."
} else {
    # CREATE DATABASE no puede ir dentro de una transaccion, por eso va en su
    # propia llamada y no agrupada con las anteriores.
    Invoke-Psql "CREATE DATABASE $DbName OWNER $RoleName ENCODING 'UTF8' TEMPLATE template0;" | Out-Null
    Write-Ok "Base '$DbName' creada, propiedad de '$RoleName'"
}

$env:PGPASSWORD = $null

# --- 6. Actualizar odoo.conf -------------------------------------------------
Write-Paso "Actualizando odoo.conf"

Copy-Item $ConfFile "$ConfFile.bak" -Force
Write-Ok "Copia de seguridad en odoo.conf.bak"

$conf = Get-Content $ConfFile -Raw
$conf = [regex]::Replace($conf, '(?m)^admin_passwd\s*=.*$', "admin_passwd = $MasterPassword")
$conf = [regex]::Replace($conf, '(?m)^db_password\s*=.*$',  "db_password = $OdooPassword")
Set-Content -Path $ConfFile -Value $conf -Encoding UTF8 -NoNewline
Write-Ok "admin_passwd y db_password escritos"

# --- 7. Verificacion final ---------------------------------------------------
Write-Paso "Verificando que Odoo podra conectarse"

$env:PGPASSWORD = $OdooPassword
$prueba = & $PsqlExe -U $RoleName -h $DbHost -p $DbPort -d $DbName -t -A -c "SELECT current_user, current_database();"
$codigo = $LASTEXITCODE
$env:PGPASSWORD = $null

if ($codigo -ne 0) {
    Write-Malo "El rol '$RoleName' no pudo conectarse a '$DbName'."
    Write-Host "    $prueba"
    exit 1
}
Write-Ok "Conectado como: $prueba"

Write-Host ""
Write-Host "  LISTO. La base de datos esta configurada." -ForegroundColor Green
Write-Host ""
Write-Host "  Vuelve a la conversacion y escribe 'listo'." -ForegroundColor White
Write-Host "  Yo instalo los modulos y verifico que cargan bien."
Write-Host ""
