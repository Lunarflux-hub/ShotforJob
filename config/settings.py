"""
Настройки Django-проекта photostudio.
"""
import mimetypes
from datetime import timedelta
from pathlib import Path

import environ

# На Windows Python берёт MIME-типы статики из системного реестра, а он часто
# содержит некорректные записи (например, .js -> text/plain из-за стороннего
# софта). Задаём явно, не полагаясь на реестр — иначе браузер может ругаться
# или (в строгих сценариях вроде <script type="module">) вообще отказаться
# выполнять скрипт.
mimetypes.add_type("application/javascript", ".js", True)
mimetypes.add_type("text/css", ".css", True)

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, True),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-secret-key-change-me")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",

    "apps.accounts",
    "apps.photos",
    "apps.social_auth",
    "apps.support",
    "apps.billing",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],  # <-- добавлено: папка с index.html
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- База данных -----------------------------------------------------------
# Для MVP можно быстро стартовать на SQLite, для прод — Postgres из .env
if env.bool("USE_SQLITE", default=False):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB", default="photostudio"),
            "USER": env("POSTGRES_USER", default="photostudio"),
            "PASSWORD": env("POSTGRES_PASSWORD", default="photostudio"),
            "HOST": env("POSTGRES_HOST", default="db"),
            "PORT": env("POSTGRES_PORT", default="5432"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]  # <-- добавлено: static/js/main.js, static/css/style.css
STATIC_ROOT = BASE_DIR / "staticfiles"  # сюда collectstatic складывает файлы для nginx/whitenoise
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- DRF / JWT ---------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    # Разрешаем анонимный доступ по умолчанию: конкретные view сами решают,
    # какая часть функционала требует авторизации (например, история заказов)
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.AllowAny",
    ),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        # Ограничиваем анонимные генерации, чтобы не разорить бюджет на Polza.ai
        "anon": "20/day",
        "user": "100/day",
        # Защита формы поддержки от спама: не больше 5 обращений в час с одного IP
        "support": "5/hour",
        # Отдельный, щедрый лимит для «читающих» эндпоинтов (баланс, статус
        # заказа, история), которые фронт дергает часто (поллинг раз в 3с +
        # виджет баланса в шапке и в форме). Раньше они делили общий лимит
        # "user": 100/day с созданием заказов — быстро упирались в 429 во
        # время обычного тестирования, из-за чего баланс показывал "—", а
        # поллинг статуса генерации решал, что запрос упал.
        "polling": "3000/day",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_LIFETIME_MIN", default=60)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_LIFETIME_DAYS", default=14)),
}

CORS_ALLOW_ALL_ORIGINS = env.bool("CORS_ALLOW_ALL_ORIGINS", default=DEBUG)
# На проде (CORS_ALLOW_ALL_ORIGINS=False) обязательно задайте конкретные домены:
# CORS_ALLOWED_ORIGINS=https://shotforjob.ru,https://www.shotforjob.ru
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

# --- OAuth 2.0 (Google / Yandex ID) ---------------------------------------
# GOOGLE_OAUTH_CLIENT_ID нужен и на бэкенде (проверка audience у ID token),
# и на фронтенде (инициализация Google Identity Services) — используйте одно
# и то же значение из Google Cloud Console (OAuth Client ID, тип Web).
GOOGLE_OAUTH_CLIENT_ID = env("GOOGLE_OAUTH_CLIENT_ID", default="")
# YANDEX_OAUTH_CLIENT_ID нужен только фронтенду (для ссылки авторизации);
# бэкенд проверяет токен напрямую через Yandex API, id клиента ему не нужен.
YANDEX_OAUTH_CLIENT_ID = env("YANDEX_OAUTH_CLIENT_ID", default="")

# --- Celery --------------------------------------------------------------
CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_TIME_LIMIT = 5 * 60  # 5 минут на генерацию — с запасом

# --- Polza.ai --------------------------------------------------------------
POLZA_BASE_URL = env("POLZA_BASE_URL", default="https://polza.ai/api/v1")
POLZA_API_KEY = env("POLZA_API_KEY", default="")
POLZA_IMAGE_MODEL = env(
    "POLZA_IMAGE_MODEL", default="google/gemini-3.1-flash-lite-image"
)
# Сила трансформации для image-to-image (0-1). Ниже — ближе к исходному фото
# (меньше искажений лица), выше — больше свободы у модели менять сцену.
POLZA_IMG2IMG_STRENGTH = env.float("POLZA_IMG2IMG_STRENGTH", default=0.4)

# --- Yandex Cloud Object Storage ------------------------------------------
YC_S3_ENDPOINT_URL = env("YC_S3_ENDPOINT_URL", default="https://storage.yandexcloud.net")
YC_S3_ACCESS_KEY_ID = env("YC_S3_ACCESS_KEY_ID", default="")
YC_S3_SECRET_ACCESS_KEY = env("YC_S3_SECRET_ACCESS_KEY", default="")
YC_S3_BUCKET_NAME = env("YC_S3_BUCKET_NAME", default="photostudio-results")
YC_S3_REGION = env("YC_S3_REGION", default="ru-central1")

# Ограничения на загрузку фото пользователем
MAX_UPLOAD_PHOTOS = 3
MAX_UPLOAD_SIZE_MB = 15

# Сколько часов хранить исходные фото пользователя (media/uploads/...) после
# того, как заказ пришёл в финальный статус (done/failed). Держим их не
# нулевое время, а не удаляем сразу же после генерации, потому что кнопка
# «Попробовать снова» (retry) переиспользует те же файлы без повторной
# загрузки. По истечении этого окна periodic task cleanup_expired_uploads
# (apps.photos.tasks) удаляет файлы с диска и записи UploadedPhoto/
# background_image — фото не нужны для показа результата (он лежит в S3) и
# не должны лежать на бэкенде бессрочно.
UPLOAD_RETENTION_HOURS = env.int("UPLOAD_RETENTION_HOURS", default=24)

# --- Почта (форма поддержки /support) --------------------------------------
# EMAIL_BACKEND по умолчанию — SMTP. Для локальной разработки без реального
# SMTP-сервера можно поставить в .env:
#   EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
# тогда письма будут просто печататься в консоль воркера.
EMAIL_BACKEND = env(
    "EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = env("SMTP_HOST", default="smtp.yandex.ru")
EMAIL_PORT = env.int("SMTP_PORT", default=587)
EMAIL_HOST_USER = env("SMTP_USER", default="")
EMAIL_HOST_PASSWORD = env("SMTP_PASSWORD", default="")
# SMTP_SECURE=true -> STARTTLS (порт 587). Для SSL/порта 465 используйте
# EMAIL_USE_SSL=true в .env вместо EMAIL_USE_TLS.
EMAIL_USE_TLS = env.bool("SMTP_SECURE", default=True)
EMAIL_USE_SSL = env.bool("SMTP_USE_SSL", default=False)
EMAIL_TIMEOUT = 15

# Адрес "от кого" уходят письма (обычно совпадает с SMTP_USER)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default=EMAIL_HOST_USER or "noreply@shotforjob.ru")

# Почта поддержки, на которую падают обращения из формы /support
SUPPORT_EMAIL = env("SUPPORT_EMAIL", default="support@shotforjob.ru")

# --- Frontend ---------------------------------------------------------------
# Используется billing-приложением для редиректа после оплаты
# (success/fail страницы). Без слэша на конце.
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:8000")

# --- Robokassa (оплата пополнения баланса) ----------------------------------
ROBOKASSA_MERCHANT_LOGIN = env("ROBOKASSA_MERCHANT_LOGIN", default="")
ROBOKASSA_TEST_MODE = env.bool("ROBOKASSA_TEST_MODE", default=True)
# В тестовом режиме (IsTest=1) Robokassa подписывает запросы отдельной парой
# тестовых паролей из ЛК (раздел "Тестовая среда"), а не боевыми — поэтому
# пароли выбираются в зависимости от режима.
if ROBOKASSA_TEST_MODE:
    ROBOKASSA_PASSWORD_1 = env("ROBOKASSA_TEST_PASSWORD_1", default="")
    ROBOKASSA_PASSWORD_2 = env("ROBOKASSA_TEST_PASSWORD_2", default="")
else:
    ROBOKASSA_PASSWORD_1 = env("ROBOKASSA_PASSWORD_1", default="")
    ROBOKASSA_PASSWORD_2 = env("ROBOKASSA_PASSWORD_2", default="")
# Система налогообложения и ставка НДС для чеков
ROBOKASSA_SNO = env("ROBOKASSA_SNO", default="usn_income")
ROBOKASSA_TAX = env("ROBOKASSA_TAX", default="none")

# --- Продакшн-безопасность ---------------------------------------------
# Активны только когда DEBUG=False (т.е. на проде, см. .env на сервере).
# Ничего не включаем через DEBUG=True, чтобы не мешать локальной разработке
# по http://localhost.
if not DEBUG:
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 30)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    # Приложение стоит за nginx-прокси — доверяем заголовку от него, чтобы
    # Django правильно определял https-запросы (иначе SECURE_SSL_REDIRECT
    # уйдёт в бесконечный редирект).
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# CSRF должен явно знать домен(ы), с которых приходят формы/запросы (Django
# по умолчанию доверяет только ALLOWED_HOSTS для http, а не для https-схемы).
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])