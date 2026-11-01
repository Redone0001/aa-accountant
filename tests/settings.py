"""Real AA apps with SQLite and no live SSO/broker. Never use in production."""

from pathlib import Path

from allianceauth.project_template.project_name.settings.base import *  # noqa: F403

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = "accountant-tests-only"
DEBUG = True
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
INSTALLED_APPS = [*INSTALLED_APPS, "accountant"]  # noqa: F405
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "demo.sqlite3"}}
ROOT_URLCONF = "tests.urls"
WSGI_APPLICATION = None
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "allianceauth.middleware.DeviceDetectionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
STATICFILES_DIRS = []
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
ESI_SSO_CLIENT_ID = "test-client"
ESI_SSO_CLIENT_SECRET = "test-secret"
ESI_SSO_CALLBACK_URL = "http://localhost:8000/sso/callback"
ESI_USER_CONTACT_EMAIL = "tests@example.invalid"
LOGIN_REDIRECT_URL = "/accountant/"
LOGIN_URL = "/login/"
ESI_DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "tests.cache.MemoryCache"}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
SITE_NAME = "Alliance Auth · Development"
SITE_URL = "http://localhost:8000"
CSRF_TRUSTED_ORIGINS = [SITE_URL]
ACCOUNTANT_RETENTION_MONTHS = 6
LOGGING = {"version": 1, "disable_existing_loggers": False, "root": {"level": "WARNING"}}
