
# Verificador de prestamos - StockroomER 1.0
# No modifica la base de datos real.

$ErrorActionPreference = "Stop"

$raiz = Split-Path $PSScriptRoot -Parent
Set-Location $raiz

$python = ".\.venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    $python = "python"
}

function Ejecutar-Prueba {
    param(
        [string]$Titulo,
        [string[]]$Argumentos
    )

    Write-Host ""
    Write-Host "===================================" -ForegroundColor Cyan
    Write-Host $Titulo -ForegroundColor Cyan
    Write-Host "===================================" -ForegroundColor Cyan

    & $python @Argumentos

    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "ERROR EN: $Titulo" -ForegroundColor Red
        exit 1
    }

    Write-Host "CORRECTO" -ForegroundColor Green
}

# 1. Comprobar Django
Ejecutar-Prueba "1. Configuracion Django" @(
    "manage.py", "check"
)


# 2. Comprobar las rutas existentes
Write-Host ""
Write-Host "===================================" -ForegroundColor Cyan
Write-Host "2. Rutas del sistema" -ForegroundColor Cyan
Write-Host "===================================" -ForegroundColor Cyan

$codigoRutas = @'
from django.urls import resolve, reverse

rutas = [
    "/trabajadores/duplicados/solicitar/",
    "/jefe/panel/",
    "/jefe/autorizaciones/1/resolver/",
    "/trabajadores/panel/",
    "/almacen/panel/",
]

for ruta in rutas:
    vista = resolve(ruta)
    print("OK:", ruta, "->", vista.url_name)

assert reverse("panel_jefe") == "/jefe/panel/"
assert reverse(
    "resolver_autorizacion_jefe", args=[1]
) == "/jefe/autorizaciones/1/resolver/"

print("Todas las rutas estan disponibles.")
'@

$archivoTemporal = Join-Path $env:TEMP "stockroom_verificar_rutas.py"

try {
    Set-Content `
        -Path $archivoTemporal `
        -Value $codigoRutas `
        -Encoding UTF8

    # Django ejecuta el script desde entrada estandar
    Get-Content $archivoTemporal -Raw |
        & $python manage.py shell --no-startup

    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR EN: Rutas del sistema" -ForegroundColor Red
        exit 1
    }

    Write-Host "CORRECTO" -ForegroundColor Green
}
finally {
    Remove-Item $archivoTemporal -ErrorAction SilentlyContinue
}


# 3. Pruebas especificas de restricciones
Ejecutar-Prueba "3. Bloqueo de prestamos" @(
    "manage.py", "test",
    "stockroom.tests.test_loan_rules"
)

# 4. Pruebas de autorizaciones
Ejecutar-Prueba "4. Autorizaciones de duplicados" @(
    "manage.py", "test",
    "stockroom.tests.test_duplicate_authorizations"
)

# 5. Pruebas del panel del jefe
Ejecutar-Prueba "5. Permisos del jefe" @(
    "manage.py", "test",
    "stockroom.tests.test_boss_panel"
)

# 6. Pruebas de peticiones del trabajador
Ejecutar-Prueba "6. Peticiones del trabajador" @(
    "manage.py", "test",
    "stockroom.tests.test_worker_exceptions"
)

# 7. Pruebas completas del sistema
Ejecutar-Prueba "7. Pruebas generales" @(
    "manage.py", "test",
    "stockroom.tests"
)

# 8. Comprobar migraciones
Ejecutar-Prueba "8. Migraciones pendientes" @(
    "manage.py",
    "makemigrations",
    "--check",
    "--dry-run"
)

Write-Host ""
Write-Host "===================================" -ForegroundColor Green
Write-Host "VERIFICACION COMPLETADA" -ForegroundColor Green
Write-Host "===================================" -ForegroundColor Green
Write-Host "No se modifico el inventario real."
