from django.db.backends.signals import connection_created

from .base import *  # noqa: F401,F403
from .base import BASE_DIR

DEBUG = True
ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {"timeout": 20},
    }
}

CORS_ALLOW_ALL_ORIGINS = True

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


def _sqlite_wal(sender, connection, **kwargs):
    if connection.vendor == "sqlite":
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA busy_timeout=20000;")


connection_created.connect(_sqlite_wal)
