# Ejecutar en la carpeta principal de StockroomER con .venv activado.
$ErrorActionPreference = "Stop"
if (-not (Test-Path ".\manage.py")) {
    throw "Ejecuta el script desde C:\Users\Edgar\StockroomER (donde está manage.py)."
}
if (-not (Test-Path ".\db.sqlite3")) {
    throw "No se encontró db.sqlite3. Se detiene el proceso sin cambios."
}
if (Test-Path ".\ensayo\db.sqlite3") {
    throw "Ya existe ensayo\db.sqlite3. Por seguridad NO se sobrescribe. Usa la copia existente o renómbrala manualmente si deseas empezar de nuevo."
}

@'
import sqlite3
from pathlib import Path
from datetime import datetime

origen = Path('db.sqlite3')
carpeta = Path('ensayo')
carpeta.mkdir(exist_ok=True)
fecha = datetime.now().strftime('%Y%m%d_%H%M%S')
respaldo = carpeta / f'respaldo_taller_{fecha}.sqlite3'
prueba = carpeta / 'db.sqlite3'

# Copia transaccional: no se copian archivos SQLite a mano.
with sqlite3.connect(f'file:{origen.resolve().as_posix()}?mode=ro', uri=True) as fuente:
    with sqlite3.connect(respaldo) as destino:
        fuente.backup(destino)

with sqlite3.connect(respaldo) as fuente:
    with sqlite3.connect(prueba) as destino:
        fuente.backup(destino)

for archivo in (respaldo, prueba):
    with sqlite3.connect(f'file:{archivo.resolve().as_posix()}?mode=ro', uri=True) as db:
        estado = db.execute('PRAGMA integrity_check').fetchone()[0]
    print(f'{archivo}: integridad = {estado}')
    if estado != 'ok':
        raise SystemExit('Respaldo no validado. NO continuar.')

print('Ensayo preparado. El archivo original db.sqlite3 NO fue modificado.')
'@ | python
if ($LASTEXITCODE -ne 0) { throw "Falló la creación del ensayo." }

python manage.py check --settings=config.settings_ensayo
if ($LASTEXITCODE -ne 0) { throw "Falló Django check del entorno de ensayo." }
Write-Host "Abre http://127.0.0.1:8001/ (solo en esta computadora)" -ForegroundColor Green
Write-Host "Inicia el servidor con: python manage.py runserver 127.0.0.1:8001 --settings=config.settings_ensayo" -ForegroundColor Cyan
