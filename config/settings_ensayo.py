"""Entorno de ensayo aislado. NUNCA apunta a db.sqlite3 del taller."""
from .settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "ensayo" / "db.sqlite3",
    }
}

# Ensayo exclusivamente en la computadora donde se ejecuta.
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
SESSION_COOKIE_NAME = "stockroom_ensayo_sessionid"
CSRF_COOKIE_NAME = "stockroom_ensayo_csrftoken"
DEBUG = True
