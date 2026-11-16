import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DEBUG = os.getenv("APP_ENV", "development") == "development"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY") or ("dev-only-rovuma-" * 4 if DEBUG else "")
if not DEBUG and len(SECRET_KEY) < 50:
    raise RuntimeError("Defina DJANGO_SECRET_KEY com pelo menos 50 caracteres.")
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
INSTALLED_APPS = [
    "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions",
    "django.contrib.messages", "django.contrib.staticfiles", "django.contrib.postgres",
    "accounts", "catalog", "documents", "reading", "audit",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounts.middleware.SessionVersion", "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "rovuma.urls"
WSGI_APPLICATION = "rovuma.wsgi.application"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE / "templates"], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request", "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages", "accounts.access.navigation",
    ]},
}]
if os.getenv("POSTGRES_HOST"):
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql", "HOST": os.environ["POSTGRES_HOST"],
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
        "NAME": os.getenv("POSTGRES_DB", "rovuma"), "USER": os.getenv("POSTGRES_USER", "rovuma"),
        "PASSWORD": os.environ["POSTGRES_PASSWORD"],
    }}
elif DEBUG:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE / "db.sqlite3"}}
else:
    raise RuntimeError("Defina a ligação PostgreSQL para produção.")
AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation." + name}
    for name in ("UserAttributeSimilarityValidator", "MinimumLengthValidator",
                 "CommonPasswordValidator", "NumericPasswordValidator")
]
LANGUAGE_CODE = "pt-pt"
TIME_ZONE = "Africa/Maputo"
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE / "static-build"
STATICFILES_DIRS = [BASE / "static"]
# Railway runs pre-deploy commands in a separate container. Serve assets from the application image too.
WHITENOISE_USE_FINDERS = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"
SESSION_COOKIE_AGE = 43200
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False  # É gerido apenas o host da biblioteca.
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin"
X_FRAME_OPTIONS = "DENY"
PASSWORD_RESET_TIMEOUT = 1800
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.locmem.EmailBackend" if DEBUG
                         else "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "1") == "1"
EMAIL_TIMEOUT = 8
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "biblioteca@example.invalid")
PRIVATE_ROOT = Path(os.getenv("PRIVATE_ROOT", BASE / "var/private"))
SPOOL_ROOT = Path(os.getenv("SPOOL_ROOT", BASE / "var/spool"))
UPLOAD_MAX_BYTES = int(os.getenv("UPLOAD_MAX_BYTES", 1024**3))
UPLOAD_CHUNK_BYTES = 1024**2
DISK_RESERVE_BYTES = int(os.getenv("DISK_RESERVE_BYTES", 256 * 1024**2))
FILE_UPLOAD_MAX_MEMORY_SIZE = 0
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024**2

# Evita registar caminhos que contenham ligações temporárias.
LOGGING = {"version": 1, "disable_existing_loggers": False, "handlers": {"quiet": {"class": "logging.NullHandler"}},
           "loggers": {name: {"handlers": ["quiet"], "propagate": False}
                       for name in ("django.server", "django.request", "django.security.csrf")}}
