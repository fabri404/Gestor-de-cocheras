"""
Django settings para Forin Cars / Gestor de Cocheras.

Todas las opciones sensibles se leen de variables de entorno.
En desarrollo: crear forin_cars/.env con DJANGO_DEBUG=1 y DATABASE_URL=sqlite:///db.sqlite3.
En producción (Docker): el entrypoint inyecta las variables desde .env.parking-N.
"""

import os
from pathlib import Path

import dj_database_url

# ─── Rutas ────────────────────────────────────────────────────────────────────
# BASE_DIR apunta a forin_cars/ (el directorio con manage.py)
BASE_DIR = Path(__file__).resolve().parent.parent

# ─── Carga .env local (si existe) ─────────────────────────────────────────────
# Solo activo en desarrollo; en Docker las vars vienen de --env-file.
_env_path = BASE_DIR / ".env"
if _env_path.exists():
    from pathlib import Path as _Path  # noqa: F811 (re-import para claridad)
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _key, _, _val = _line.partition("=")
        os.environ.setdefault(_key.strip(), _val.strip())


# ─── Seguridad ────────────────────────────────────────────────────────────────
# Nunca tiene default: si no está en el entorno la app no arranca (fail-fast).
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"

ALLOWED_HOSTS = os.environ.get(
    "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1"
).split(",")

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

# ─── Identidad del negocio ────────────────────────────────────────────────────
BUSINESS_NAME = os.environ.get("BUSINESS_NAME", "Forin Cars")


# ─── Aplicaciones instaladas ─────────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_extensions",
    "users",
    "parking",
    "qrform",
]


# ─── Middleware ───────────────────────────────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",   # sirve static files sin nginx
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ─── URLs y WSGI/ASGI ────────────────────────────────────────────────────────
ROOT_URLCONF = "forin_cars.urls"
WSGI_APPLICATION = "forin_cars.wsgi.application"
ASGI_APPLICATION = "forin_cars.asgi.application"


# ─── Templates ───────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "users.context_processors.role_flags",
                # Expone BUSINESS_NAME a todos los templates
                "forin_cars.context_processors.business_settings",
            ],
        },
    },
]


# ─── Base de datos ────────────────────────────────────────────────────────────
# En dev usar DATABASE_URL=sqlite:///db.sqlite3
# En prod usar DATABASE_URL=postgres://user:pass@db:5432/parking_b1
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ─── Validadores de contraseña ────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ─── Internacionalización ─────────────────────────────────────────────────────
LANGUAGE_CODE = "es-ar"
TIME_ZONE = os.environ.get("BUSINESS_TIMEZONE", "America/Argentina/Buenos_Aires")
USE_I18N = True
USE_TZ = True


# ─── Archivos estáticos y media ──────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "staticfiles": {
        # Comprime y cachea con hash de contenido — ideal para whitenoise en prod
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
}


# ─── Auth / redirecciones ─────────────────────────────────────────────────────
LOGIN_URL = "login/"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"


# ─── Email (opcional) ─────────────────────────────────────────────────────────
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@parking.local")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "0") == "1"


# ─── Hardening para producción (cuando DEBUG=False) ──────────────────────────
if not DEBUG:
    # HTTPS y cookies seguras
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000          # 1 año
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Anti-clickjacking
    X_FRAME_OPTIONS = "DENY"
