"""Fase 22E: pruebas aisladas de configuración de producción.

No conecta PostgreSQL ni modifica la base de datos de desarrollo.
"""

import os
import subprocess
import sys
from pathlib import Path
from unittest import TestCase


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_VARIABLES = (
    "STOCKROOM_SECRET_KEY",
    "STOCKROOM_ALLOWED_HOSTS",
    "STOCKROOM_DB_NAME",
    "STOCKROOM_DB_USER",
    "STOCKROOM_DB_PASSWORD",
)


class ProductionSettingsTests(TestCase):
    def environment(self, *, https=True):
        env = os.environ.copy()
        for key in tuple(env):
            if key.startswith("STOCKROOM_"):
                env.pop(key)

        env.update(
            DJANGO_SETTINGS_MODULE="config.production_settings",
            STOCKROOM_SECRET_KEY="prueba-aislada-" + "X" * 60,
            STOCKROOM_ALLOWED_HOSTS="127.0.0.1,localhost",
            STOCKROOM_DB_NAME="base_ficticia",
            STOCKROOM_DB_USER="usuario_ficticio",
            STOCKROOM_DB_PASSWORD="contrasena_ficticia",
            STOCKROOM_HTTPS_ENABLED="true" if https else "false",
        )
        if https:
            env["STOCKROOM_CSRF_TRUSTED_ORIGINS"] = "https://localhost"
        return env

    def execute(self, env, code="import config.production_settings"):
        return subprocess.run(
            [sys.executable, "-c", code],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_produccion_segura_carga_con_variables_ficticias(self):
        code = """
from config import production_settings as s
assert s.DEBUG is False
assert s.DATABASES['default']['ENGINE'] == 'django.db.backends.postgresql'
assert s.ALLOWED_HOSTS == ['127.0.0.1', 'localhost']
assert bool(s.STATIC_ROOT)
assert s.SESSION_COOKIE_SECURE is True
assert s.CSRF_COOKIE_SECURE is True
assert s.SECURE_SSL_REDIRECT is True
assert 'https://localhost' in s.CSRF_TRUSTED_ORIGINS
"""
        result = self.execute(self.environment(), code)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rechaza_cada_variable_obligatoria_ausente(self):
        for variable in REQUIRED_VARIABLES:
            with self.subTest(variable=variable):
                env = self.environment()
                env.pop(variable)
                result = self.execute(env)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(variable, result.stderr)

    def test_https_exige_origen_csrf(self):
        env = self.environment()
        env.pop("STOCKROOM_CSRF_TRUSTED_ORIGINS")
        result = self.execute(env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("STOCKROOM_CSRF_TRUSTED_ORIGINS", result.stderr)

    def test_modo_sin_https_solo_para_validacion_aislada(self):
        env = self.environment(https=False)
        code = """
from config import production_settings as s
assert s.DEBUG is False
assert s.SESSION_COOKIE_SECURE is False
assert s.CSRF_COOKIE_SECURE is False
assert s.SECURE_SSL_REDIRECT is False
"""
        result = self.execute(env, code)
        self.assertEqual(result.returncode, 0, result.stderr)
