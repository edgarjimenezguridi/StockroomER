
"""
Configuracion de produccion de StockroomER.

Uso futuro:
DJANGO_SETTINGS_MODULE=config.production_settings

No utilizar para el desarrollo local.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .settings import *


def required_env(name):
    value = os.environ.get(name, "").strip()

    if not value:
        raise ImproperlyConfigured(
            f"Falta la variable de entorno obligatoria: {name}"
        )

    return value


DEBUG = False

SECRET_KEY = required_env("STOCKROOM_SECRET_KEY")

ALLOWED_HOSTS = [
    host.strip()
    for host in required_env("STOCKROOM_ALLOWED_HOSTS").split(",")
    if host.strip()
]

if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "Debes configurar al menos un host autorizado."
    )


# Base de datos PostgreSQL del servidor local.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": required_env("STOCKROOM_DB_NAME"),
        "USER": required_env("STOCKROOM_DB_USER"),
        "PASSWORD": required_env("STOCKROOM_DB_PASSWORD"),
        "HOST": os.environ.get("STOCKROOM_DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("STOCKROOM_DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}


# Archivos estaticos para servir mediante Nginx.
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"


# Protecciones generales.
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"


# HTTPS se activara al instalar el certificado
# y configurar correctamente el servidor web.
HTTPS_ENABLED = (
    os.environ.get("STOCKROOM_HTTPS_ENABLED", "false").lower()
    == "true"
)

SESSION_COOKIE_SECURE = HTTPS_ENABLED
CSRF_COOKIE_SECURE = HTTPS_ENABLED
SECURE_SSL_REDIRECT = HTTPS_ENABLED

if HTTPS_ENABLED:
    CSRF_TRUSTED_ORIGINS = [
        origin.strip()
        for origin in required_env(
            "STOCKROOM_CSRF_TRUSTED_ORIGINS"
        ).split(",")
        if origin.strip()
    ]
