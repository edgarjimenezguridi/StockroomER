# StockroomER - Fase 21E
# Uso:
#   .\programar_respaldo_diario.ps1 -Ejecutar   (crea y verifica un respaldo ahora)
#   .\programar_respaldo_diario.ps1 -Instalar   (registra una tarea diaria a las 19:00)
# La tarea instalada requiere una sesion iniciada. Se recomienda instalarla
# solamente en el servidor definitivo y revisar su ejecucion en Windows.
[CmdletBinding(DefaultParameterSetName = 'Ayuda')]
param(
    [Parameter(Mandatory = $true, ParameterSetName = 'Ejecutar')]
    [switch]$Ejecutar,
    [Parameter(Mandatory = $true, ParameterSetName = 'Instalar')]
    [switch]$Instalar
)

$ErrorActionPreference = 'Stop'
$proyecto = $PSScriptRoot
$python = Join-Path $proyecto '.venv\Scripts\python.exe'
$manage = Join-Path $proyecto 'manage.py'
$carpetaRespaldos = Join-Path $proyecto 'backups'
$carpetaLogs = Join-Path $carpetaRespaldos 'logs'
$nombreTarea = 'StockroomER - Respaldo local diario'

function Confirmar-Proyecto {
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw "No se encontro el Python del entorno virtual: $python"
    }
    if (-not (Test-Path -LiteralPath $manage -PathType Leaf)) {
        throw "No se encontro manage.py: $manage"
    }
}

function Ejecutar-ComandoDjango {
    param(
        [Parameter(Mandatory = $true)][string]$Comando,
        [Parameter(Mandatory = $true)][string]$RutaLog
    )

    # No usamos una tuberia que pueda ocultar el codigo de salida de Python.
    $salida = Join-Path $carpetaLogs ([guid]::NewGuid().ToString('N') + '.stdout.tmp')
    $errores = Join-Path $carpetaLogs ([guid]::NewGuid().ToString('N') + '.stderr.tmp')
    try {
        $proceso = Start-Process -FilePath $python `
            -ArgumentList ('"' + $manage + '" ' + $Comando) `
            -WorkingDirectory $proyecto `
            -RedirectStandardOutput $salida `
            -RedirectStandardError $errores `
            -Wait -PassThru -NoNewWindow

        if (Test-Path -LiteralPath $salida) {
            Get-Content -LiteralPath $salida -Encoding UTF8 | Out-File -LiteralPath $RutaLog -Append -Encoding UTF8
        }
        if (Test-Path -LiteralPath $errores) {
            Get-Content -LiteralPath $errores -Encoding UTF8 | Out-File -LiteralPath $RutaLog -Append -Encoding UTF8
        }
        if ($proceso.ExitCode -ne 0) {
            throw "El comando '$Comando' termino con codigo $($proceso.ExitCode)."
        }
    }
    finally {
        Remove-Item -LiteralPath $salida, $errores -Force -ErrorAction SilentlyContinue
    }
}

if ($Ejecutar) {
    Confirmar-Proyecto
    New-Item -ItemType Directory -Path $carpetaLogs -Force | Out-Null
    $marca = Get-Date -Format 'yyyyMMdd_HHmmss_fffffff'
    $log = Join-Path $carpetaLogs "respaldo_$marca.log"
    $ultimoExito = Join-Path $carpetaRespaldos 'ultimo_respaldo_correcto.txt'
    $ultimoError = Join-Path $carpetaRespaldos 'ultimo_error_respaldo.txt'
    "Inicio: $(Get-Date -Format o)" | Out-File -LiteralPath $log -Encoding UTF8
    try {
        'Ejecutando: respaldo_almacen' | Out-File -LiteralPath $log -Append -Encoding UTF8
        Ejecutar-ComandoDjango -Comando 'respaldo_almacen' -RutaLog $log
        'Ejecutando: verificar_respaldos --max-hours 26' | Out-File -LiteralPath $log -Append -Encoding UTF8
        Ejecutar-ComandoDjango -Comando 'verificar_respaldos --max-hours 26' -RutaLog $log

        "Ultimo respaldo correcto: $(Get-Date -Format o)`nRegistro: $log" |
            Out-File -LiteralPath $ultimoExito -Encoding UTF8
        if (Test-Path -LiteralPath $ultimoError) {
            Remove-Item -LiteralPath $ultimoError -Force
        }
        "RESULTADO: CORRECTO - $(Get-Date -Format o)" | Out-File -LiteralPath $log -Append -Encoding UTF8
        Write-Host "Respaldo creado y verificado. Registro: $log"
        exit 0
    }
    catch {
        $detalle = $_.Exception.Message
        "ERROR: $detalle`nFecha: $(Get-Date -Format o)`nRegistro: $log" |
            Out-File -LiteralPath $ultimoError -Encoding UTF8
        "RESULTADO: ERROR - $detalle" | Out-File -LiteralPath $log -Append -Encoding UTF8
        Write-Error "Fallo el respaldo. Consulte el registro: $log. $detalle"
        exit 1
    }
}

if ($Instalar) {
    Confirmar-Proyecto
    if (-not (Get-Command Get-ScheduledTask -ErrorAction SilentlyContinue)) {
        throw 'El Programador de tareas de Windows no esta disponible.'
    }
    if (Get-ScheduledTask -TaskName $nombreTarea -ErrorAction SilentlyContinue) {
        throw "Ya existe la tarea '$nombreTarea'. No se modifico."
    }
    # Usa la misma edicion de PowerShell desde la que se instala.
    $shell = (Get-Process -Id $PID).Path
    if (-not (Test-Path -LiteralPath $shell -PathType Leaf)) {
        throw 'No se pudo identificar el ejecutable de PowerShell.'
    }
    $argumentos = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -Ejecutar'
    $accion = New-ScheduledTaskAction -Execute $shell -Argument $argumentos -WorkingDirectory $proyecto
    $inicio = New-ScheduledTaskTrigger -Daily -At '19:00'
    $config = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew
    $usuario = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $usuario -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $nombreTarea -Action $accion -Trigger $inicio -Settings $config -Principal $principal | Out-Null
    Write-Host "Tarea creada: $nombreTarea"
    Write-Host 'Horario: todos los dias a las 19:00.'
    Write-Host 'IMPORTANTE: esta version requiere sesion de Windows iniciada.'
    Write-Host "Registros: $carpetaLogs"
    exit 0
}

Write-Host 'StockroomER - respaldo local diario'
Write-Host '  .\programar_respaldo_diario.ps1 -Ejecutar  # respaldo de prueba ahora'
Write-Host '  .\programar_respaldo_diario.ps1 -Instalar  # solo en el servidor definitivo'
