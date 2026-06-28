"""
iSell — Main Settings
Mobile-first housing marketplace for Tanzania.
"""

import os
from pathlib import Path
from decouple import config
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    raw_value = config(name, default=None)
    if raw_value is None:
        return default
    if isinstance(raw_value, bool):
        return raw_value

    normalized = str(raw_value).strip().lower()
    if normalized in {'1', 'true', 'yes', 'on'}:
        return True
    if normalized in {'0', 'false', 'no', 'off', ''}:
        return False
    if normalized in {'release', 'production', 'prod'}:
        return False
    return default

SECRET_KEY = config('SECRET_KEY')
DEBUG = env_bool('DEBUG', default=False)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='192.168.3.10').split(',')

CSRF_TRUSTED_ORIGINS = [
    "https://iselltz.com",
    "https://www.iselltz.com",
    "https://iselltz.onrender.com",
]

# ─── Applications ─────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',

    # Third party
    'cloudinary_storage',
    'cloudinary',
    'django_htmx',
    'crispy_forms',
    'crispy_tailwind',
    'phonenumber_field',

    # Local apps
    'apps.core',
    'apps.accounts',
    'apps.listings',
    'apps.subscriptions',
    'apps.notifications',
    'apps.search',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
    'apps.core.middleware.ActiveSubscriptionMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.global_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ─── Database ─────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='nyumbahub'),
        'USER': config('DB_USER', default='postgres'),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

# DATABASES = {
#     "default": dj_database_url.config(
#         default=os.getenv("DATABASE_URL"),
#         conn_max_age=600,
#     )
# }

# ─── Auth ─────────────────────────────────────────────────
AUTH_USER_MODEL = 'accounts.CustomUser'
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ─── Cache / Redis ────────────────────────────────────────
# Falls back to local memory cache if Redis is not running (safe for dev)
REDIS_URL = config('REDIS_URL', default='')

if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            }
        }
    }
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SESSION_CACHE_ALIAS = 'default'
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }
    SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# ─── Celery ───────────────────────────────────────────────
CELERY_BROKER_URL = config('REDIS_URL', default='memory://')
CELERY_RESULT_BACKEND = config('REDIS_URL', default='cache+memory://')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_TASK_ALWAYS_EAGER = not bool(config('REDIS_URL', default=''))  # run tasks inline if no Redis

# ─── Cloudinary ───────────────────────────────────────────
import cloudinary
cloudinary.config(
    cloud_name=config('CLOUDINARY_CLOUD_NAME', default=''),
    api_key=config('CLOUDINARY_API_KEY', default=''),
    api_secret=config('CLOUDINARY_API_SECRET', default=''),
)

# DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
# Using local storage in development, switch to Cloudinary in production
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
CLOUDINARY_STORAGE = {
    "CLOUD_NAME": os.getenv("CLOUDINARY_CLOUD_NAME"),
    "API_KEY": os.getenv("CLOUDINARY_API_KEY"),
    "API_SECRET": os.getenv("CLOUDINARY_API_SECRET"),
}

# ─── Static & Media ───────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ─── Localisation ─────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Dar_es_Salaam'
USE_I18N = True
USE_TZ = True

# ─── Email ────────────────────────────────────────────────
DEFAULT_SMTP_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
CONSOLE_EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
LOCAL_MEMORY_EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
DUMMY_EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', default=True)
EMAIL_USE_SSL = env_bool('EMAIL_USE_SSL', default=False)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_TIMEOUT = int(os.getenv('EMAIL_TIMEOUT', '10'))
EMAIL_BACKEND = os.getenv(
    'EMAIL_BACKEND',
    DEFAULT_SMTP_BACKEND if EMAIL_HOST and EMAIL_HOST_USER and EMAIL_HOST_PASSWORD else CONSOLE_EMAIL_BACKEND,
)
NON_DELIVERING_EMAIL_BACKENDS = {
    CONSOLE_EMAIL_BACKEND,
    LOCAL_MEMORY_EMAIL_BACKEND,
    DUMMY_EMAIL_BACKEND,
}
EMAIL_DELIVERY_ENABLED = EMAIL_BACKEND not in NON_DELIVERING_EMAIL_BACKENDS and bool(EMAIL_HOST)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default=EMAIL_HOST_USER or 'genienewworld@outlook.com')
SERVER_EMAIL = config('SERVER_EMAIL', default=DEFAULT_FROM_EMAIL)
PASSWORD_RESET_TIMEOUT = config('PASSWORD_RESET_TIMEOUT', default=60 * 60 * 24, cast=int)

# ─── Crispy Forms ─────────────────────────────────────────
CRISPY_ALLOWED_TEMPLATE_PACKS = 'tailwind'
CRISPY_TEMPLATE_PACK = 'tailwind'

# ─── Phone Numbers ────────────────────────────────────────
PHONENUMBER_DEFAULT_REGION = 'TZ'

# ─── App Settings ─────────────────────────────────────────
SITE_NAME = config('SITE_NAME', default='iSell')
SITE_URL = config('SITE_URL', default='http://localhost:8000')
PAYMENTS_ENABLED = env_bool('PAYMENTS_ENABLED', default=False)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─── Subscription Plan Limits ─────────────────────────────
PLAN_LIMITS = {
    'basic': {
        'listings': 3,
        'images_per_listing': 3,
        'featured': False,
        'price_tzs': 15000,
    },
    'standard': {
        'listings': 10,
        'images_per_listing': 8,
        'featured': False,
        'price_tzs': 35000,
    },
    'premium': {
        'listings': 999,
        'images_per_listing': 20,
        'featured': True,
        'price_tzs': 70000,
    },
}
