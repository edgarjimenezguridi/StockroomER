
$ErrorActionPreference = "Stop"

# Ubicación del proyecto
$Proyecto = Split-Path -Parent $PSScriptRoot

# Python del entorno virtual
$Python = Join-Path $Proyecto ".venv\Scripts\python.exe"

# Archivo principal de Django
$Manage = Join-Path $Proyecto "manage.py"

# Carpeta para respaldos
$Backups = Join-Path $Proyecto "backups"

if (-not (Test-Path $Python)) {
    throw "No se encontró el entorno virtual de Python."
}

if (-not (Test-Path $Manage)) {
    throw "No se encontró manage.py."
}

New-Item -ItemType Directory -Force -Path $Backups |
    Out-Null

# Guardar fecha y hora de ejecución
$Fecha = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

$Registro = Join-Path $Backups "historial_respaldos.log"

Add-Content -Path $Registro -Value "[$Fecha] Iniciando respaldo"

# Ejecutar el comando Django
Push-Location $Proyecto

try {
    & $Python $Manage respaldo_almacen

    if ($LASTEXITCODE -ne 0) {
        throw "El comando de respaldo terminó con error."
    }
    # Verificar que el respaldo reciente sea legible
    # y que no tenga errores de integridad.
    & $Python $Manage verificar_respaldos --max-hours 26

    if ($LASTEXITCODE -ne 0) {
        throw "La verificacion del respaldo termino con error."
    }

    $FechaFin = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

    Add-Content -Path $Registro -Value "[$FechaFin] Respaldo correcto"

    Write-Host "Respaldo automático completado."

}
catch {
    $FechaError = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

    Add-Content -Path $Registro -Value (
        "[$FechaError] ERROR: $($_.Exception.Message)"
    )

    Write-Error $_
    exit 1
}
finally {
    Pop-Location
}
