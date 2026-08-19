from datetime import timedelta
from pathlib import Path
import os

import dj_database_url
from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "dev-only-social-theory-library-secret-change-before-production",
)
DEBUG = env_bool("DJANGO_DEBUG", True)
PUBLIC_DEPLOYMENT_MODE = env_bool("PUBLIC_DEPLOYMENT_MODE", False)
ALLOWED_HOSTS = [host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",") if host.strip()]
LAN_HOST = os.getenv("LAN_HOST", "").strip()
LAN_PROXY_TOKEN = os.getenv("LAN_PROXY_TOKEN", "").strip()
LAN_HTTP_TRUSTED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv("LAN_HTTP_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
if LAN_HOST and LAN_HOST not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(LAN_HOST)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "accounts",
    "catalog",
    "ingestion",
    "reading",
    "distribution",
]

MIDDLEWARE = [
    "common.middleware.TrustedLanHttpMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=60,
        conn_health_checks=True,
    )
}

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = os.getenv("TZ", "Asia/Shanghai")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.getenv("NAS_LIBRARY_ROOT", BASE_DIR / "data"))
NAS_INCOMING_ROOT = Path(os.getenv("NAS_INCOMING_ROOT", MEDIA_ROOT / "incoming"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        os.getenv(
            "DJANGO_CORS_ALLOWED_ORIGINS",
            "http://localhost:3000,http://localhost:3100,http://127.0.0.1:3000,http://127.0.0.1:3100",
        ),
    ).split(",")
    if origin.strip()
]
for origin in LAN_HTTP_TRUSTED_ORIGINS:
    if origin not in CORS_ALLOWED_ORIGINS:
        CORS_ALLOWED_ORIGINS.append(origin)
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "range",
]
CORS_EXPOSE_HEADERS = [
    "Accept-Ranges",
    "Content-Disposition",
    "Content-Length",
    "Content-Range",
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        ",".join(CORS_ALLOWED_ORIGINS),
    ).split(",")
    if origin.strip()
]
for origin in LAN_HTTP_TRUSTED_ORIGINS:
    if origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(origin)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "accounts.authentication.VersionedJWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticatedOrReadOnly",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 24,
    "EXCEPTION_HANDLER": "config.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": (
        "config.throttling.InternalAwareAnonRateThrottle",
        "config.throttling.InternalAwareUserRateThrottle",
        "config.throttling.InternalAwareScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.getenv("API_ANON_RATE", "120/min"),
        "user": os.getenv("API_USER_RATE", "600/min"),
        "login": os.getenv("AUTH_LOGIN_RATE", "12/min"),
        "register": os.getenv("AUTH_REGISTER_RATE", "8/hour"),
        "password_reset": os.getenv("AUTH_PASSWORD_RESET_RATE", "6/hour"),
        "token_refresh": os.getenv("AUTH_TOKEN_REFRESH_RATE", "60/hour"),
        "exact_search_anon": os.getenv("EXACT_SEARCH_ANON_RATE", "60/min"),
        "exact_search_user": os.getenv("EXACT_SEARCH_USER_RATE", "240/min"),
        "semantic_search_anon": os.getenv("SEMANTIC_SEARCH_ANON_RATE", os.getenv("SEMANTIC_SEARCH_RATE", "30/min")),
        "semantic_search_user": os.getenv("SEMANTIC_SEARCH_USER_RATE", "120/min"),
        "library_qa": os.getenv("LIBRARY_QA_RATE", "30/hour"),
        "public_usage_event": os.getenv("PUBLIC_USAGE_EVENT_RATE", "120/min"),
    },
}

# Used only by the Web container when it renders public pages on the server.
# Browser requests never receive this value. Short or empty values cannot bypass throttling.
INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN", "")

CACHE_URL = os.getenv("CACHE_URL", "")
CACHES = {
    "default": (
        {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": CACHE_URL,
            "KEY_PREFIX": "social-theory-library",
        }
        if CACHE_URL
        else {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "social-theory-library-local",
        }
    )
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=20),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": env_bool("JWT_BLACKLIST_AFTER_ROTATION", True),
    "UPDATE_LAST_LOGIN": True,
}
JWT_COOKIE_AUTH_ENABLED = env_bool("JWT_COOKIE_AUTH_ENABLED", True)
JWT_RETURN_TOKENS_IN_BODY = env_bool(
    "JWT_RETURN_TOKENS_IN_BODY",
    not PUBLIC_DEPLOYMENT_MODE,
)
JWT_ACCESS_COOKIE_NAME = os.getenv("JWT_ACCESS_COOKIE_NAME", "stl_access")
JWT_REFRESH_COOKIE_NAME = os.getenv("JWT_REFRESH_COOKIE_NAME", "stl_refresh")

CELERY_BROKER_URL = os.getenv(
    "CELERY_BROKER_URL",
    os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "").strip() or None
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_STORE_ERRORS_EVEN_IF_IGNORED = False
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 60 * 60
INGESTION_TASK_QUEUE = os.getenv("INGESTION_TASK_QUEUE", "ingestion").strip() or "ingestion"
SEARCH_EVALUATION_TASK_QUEUE = os.getenv("SEARCH_EVALUATION_TASK_QUEUE", "celery").strip() or "celery"
QUERY_LEXICON_TASK_QUEUE = os.getenv("QUERY_LEXICON_TASK_QUEUE", "celery").strip() or "celery"
CELERY_TASK_ROUTES = {
    "ingestion.tasks.process_upload_item": {"queue": INGESTION_TASK_QUEUE},
    "ingestion.tasks.process_reviewed_upload_item": {"queue": INGESTION_TASK_QUEUE},
    "ingestion.tasks.process_query_lexicon_candidate_job": {
        "queue": INGESTION_TASK_QUEUE
    },
    "ingestion.tasks.process_r2_staging_job": {"queue": INGESTION_TASK_QUEUE},
    "catalog.tasks.run_search_evaluation": {"queue": SEARCH_EVALUATION_TASK_QUEUE},
    "catalog.tasks.process_query_lexicon_events": {"queue": QUERY_LEXICON_TASK_QUEUE},
    "catalog.tasks.recover_query_lexicon_events": {"queue": QUERY_LEXICON_TASK_QUEUE},
}
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_CONNECTION_MAX_RETRIES = None
CELERY_BROKER_HEARTBEAT = 20
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "visibility_timeout": 2 * 60 * 60,
    "socket_connect_timeout": 5,
    "socket_timeout": 10,
    "retry_on_timeout": True,
}
CELERY_BEAT_SCHEDULE = {
    "rotate-due-recommendations-hourly": {
        "task": "catalog.tasks.rotate_due_recommendations",
        "schedule": 60 * 60,
    },
    "recover-ingestion-queue-every-minute": {
        "task": "ingestion.tasks.recover_ingestion_queue",
        "schedule": 60,
    },
    "record-ingestion-worker-heartbeat": {
        "task": "ingestion.tasks.record_ingestion_worker_heartbeat",
        "schedule": 30,
    },
    "recover-semantic-index-queue": {
        "task": "catalog.tasks.recover_semantic_index_queue",
        "schedule": 120,
    },
    "recover-query-lexicon-events": {
        "task": "catalog.tasks.recover_query_lexicon_events",
        "schedule": max(
            1,
            int(os.getenv("QUERY_LEXICON_RECOVERY_INTERVAL_SECONDS", "60")),
        ),
    },
    "aggregate-anonymous-searches-hourly": {
        "task": "catalog.tasks.aggregate_anonymous_searches",
        "schedule": 60 * 60,
    },
}
PROCESS_INGESTION_INLINE = env_bool("PROCESS_INGESTION_INLINE", DEBUG)
CELERY_TASK_ALWAYS_EAGER = env_bool(
    "CELERY_TASK_ALWAYS_EAGER",
    PROCESS_INGESTION_INLINE,
)
QUERY_LEXICON_EVENT_BATCH_SIZE = max(
    1,
    min(500, int(os.getenv("QUERY_LEXICON_EVENT_BATCH_SIZE", "100"))),
)
QUERY_LEXICON_EVENT_LEASE_SECONDS = max(
    5,
    int(os.getenv("QUERY_LEXICON_EVENT_LEASE_SECONDS", "300")),
)
QUERY_LEXICON_EVENT_MAX_ATTEMPTS = max(
    1,
    int(os.getenv("QUERY_LEXICON_EVENT_MAX_ATTEMPTS", "8")),
)
QUERY_LEXICON_EVENT_RETRY_BASE_SECONDS = max(
    1,
    int(os.getenv("QUERY_LEXICON_EVENT_RETRY_BASE_SECONDS", "30")),
)
QUERY_LEXICON_EVENT_RETRY_MAX_SECONDS = max(
    QUERY_LEXICON_EVENT_RETRY_BASE_SECONDS,
    int(os.getenv("QUERY_LEXICON_EVENT_RETRY_MAX_SECONDS", "3600")),
)
QUERY_LEXICON_RESOLVER_MAX_RESULTS = max(
    1,
    min(500, int(os.getenv("QUERY_LEXICON_RESOLVER_MAX_RESULTS", "100"))),
)
QUERY_LEXICON_SEARCH_CACHE_SECONDS = max(
    1,
    min(3600, int(os.getenv("QUERY_LEXICON_SEARCH_CACHE_SECONDS", "300"))),
)
INGESTION_QUEUE_STALLED_SECONDS = int(
    os.getenv("INGESTION_QUEUE_STALLED_SECONDS", "180")
)
INGESTION_STAGE_STALLED_SECONDS = int(
    os.getenv("INGESTION_STAGE_STALLED_SECONDS", "1800")
)
INGESTION_TASK_LOCK_SECONDS = max(
    300,
    int(os.getenv("INGESTION_TASK_LOCK_SECONDS", str(2 * 60 * 60))),
)

MEILISEARCH_URL = os.getenv("MEILISEARCH_URL", "http://localhost:7700")
MEILISEARCH_MASTER_KEY = os.getenv("MEILISEARCH_MASTER_KEY", "")
# Evaluation commands are deliberately inert unless all three values are set.
# The service-level guard also requires PostgreSQL plus an evaluation-shaped
# database name, host and Meilisearch endpoint before it permits any write.
SEMANTIC_SEARCH_EVALUATION_MODE = env_bool(
    "SEMANTIC_SEARCH_EVALUATION_MODE",
    False,
)
SEMANTIC_SEARCH_EVALUATION_DATABASE_NAME = os.getenv(
    "SEMANTIC_SEARCH_EVALUATION_DATABASE_NAME",
    "",
).strip()
SEMANTIC_SEARCH_EVALUATION_MEILISEARCH_URL = os.getenv(
    "SEMANTIC_SEARCH_EVALUATION_MEILISEARCH_URL",
    "",
).strip()
USE_EXTERNAL_SEARCH = env_bool("USE_EXTERNAL_SEARCH", not DEBUG)
SEMANTIC_EMBEDDING_API_KEY = os.getenv("SEMANTIC_EMBEDDING_API_KEY", "")
SEMANTIC_SEARCH_ENABLED = env_bool("SEMANTIC_SEARCH_ENABLED", True)
SEMANTIC_SEARCH_PROVIDER = os.getenv("SEMANTIC_SEARCH_PROVIDER", "huggingFace")
SEMANTIC_SEARCH_MODEL = os.getenv(
    "SEMANTIC_SEARCH_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)
SEMANTIC_SEARCH_MODEL_REVISION = os.getenv("SEMANTIC_SEARCH_MODEL_REVISION", "main")
SEMANTIC_SEARCH_MODEL_POOLING = os.getenv("SEMANTIC_SEARCH_MODEL_POOLING", "useModel")
SEMANTIC_SEARCH_RERANKER = os.getenv("SEMANTIC_SEARCH_RERANKER", "rules")
SEMANTIC_SEARCH_RATIO = min(1.0, max(0.0, float(os.getenv("SEMANTIC_SEARCH_RATIO", "0.72"))))
SEMANTIC_SEARCH_MAX_RESULTS_PER_WORK = max(
    1,
    min(int(os.getenv("SEMANTIC_SEARCH_MAX_RESULTS_PER_WORK", "3")), 20),
)
SEMANTIC_SEARCH_QUERY_REWRITE_ENABLED = env_bool(
    "SEMANTIC_SEARCH_QUERY_REWRITE_ENABLED",
    False,
)
SEMANTIC_SEARCH_REQUIRED = env_bool("SEMANTIC_SEARCH_REQUIRED", False)
SEMANTIC_SEARCH_INDEX_CONCURRENCY = max(
    1,
    min(int(os.getenv("SEMANTIC_SEARCH_INDEX_CONCURRENCY", "1")), 4),
)
SEMANTIC_INDEX_QUEUE_STALLED_SECONDS = max(
    60,
    int(os.getenv("SEMANTIC_INDEX_QUEUE_STALLED_SECONDS", "300")),
)
SEMANTIC_INDEX_RUNNING_STALLED_SECONDS = max(
    900,
    int(os.getenv("SEMANTIC_INDEX_RUNNING_STALLED_SECONDS", str(2 * 60 * 60))),
)
SEMANTIC_INDEX_RECOVERY_BATCH_SIZE = max(
    1,
    min(int(os.getenv("SEMANTIC_INDEX_RECOVERY_BATCH_SIZE", "20")), 100),
)
SEMANTIC_INDEX_STAGE_BATCH_SIZE = max(
    1,
    min(int(os.getenv("SEMANTIC_INDEX_STAGE_BATCH_SIZE", "1")), 20),
)
SEMANTIC_INDEX_DOCUMENT_BATCH_SIZE = max(
    1,
    min(int(os.getenv("SEMANTIC_INDEX_DOCUMENT_BATCH_SIZE", "128")), 1000),
)
SEMANTIC_INDEX_TASK_TIMEOUT_SECONDS = max(
    180,
    min(int(os.getenv("SEMANTIC_INDEX_TASK_TIMEOUT_SECONDS", "1800")), 3500),
)
SEMANTIC_SEARCH_MODEL_CACHE = os.getenv("SEMANTIC_SEARCH_MODEL_CACHE", "/models")
SEMANTIC_SEARCH_OFFLINE_MODE = env_bool("SEMANTIC_SEARCH_OFFLINE_MODE", True)
SEMANTIC_SEARCH_TIMEOUT_SECONDS = max(
    3,
    min(int(os.getenv("SEMANTIC_SEARCH_TIMEOUT_SECONDS", "30")), 180),
)
SEMANTIC_SEARCH_MAX_CONCURRENT = max(
    1,
    min(int(os.getenv("SEMANTIC_SEARCH_MAX_CONCURRENT", "2")), 16),
)
# Viewpoint search V2 is additive and remains behind a feature flag until the
# library-specific relevance set has been judged.  Candidate counts are kept
# deliberately bounded because the production target is a small NAS.
SEMANTIC_SEARCH_V2_ENABLED = env_bool("SEMANTIC_SEARCH_V2_ENABLED", False)
SEMANTIC_SEARCH_PROFILE = os.getenv("SEMANTIC_SEARCH_PROFILE", "precision").strip().casefold()
if SEMANTIC_SEARCH_PROFILE not in {"fast", "balanced", "precision"}:
    SEMANTIC_SEARCH_PROFILE = "precision"
SEMANTIC_SEARCH_DENSE_TOP_K = max(
    8,
    min(int(os.getenv("SEMANTIC_SEARCH_DENSE_TOP_K", "50")), 200),
)
SEMANTIC_SEARCH_SPARSE_TOP_K = max(
    8,
    min(int(os.getenv("SEMANTIC_SEARCH_SPARSE_TOP_K", "50")), 200),
)
SEMANTIC_SEARCH_FUSION_TOP_K = max(
    8,
    min(int(os.getenv("SEMANTIC_SEARCH_FUSION_TOP_K", "24")), 100),
)
SEMANTIC_SEARCH_RERANK_TOP_K = max(
    0,
    min(int(os.getenv("SEMANTIC_SEARCH_RERANK_TOP_K", "24")), 64),
)
SEMANTIC_SEARCH_FINAL_TOP_K = max(
    1,
    min(int(os.getenv("SEMANTIC_SEARCH_FINAL_TOP_K", "10")), 40),
)
SEMANTIC_SEARCH_QUERY_EXPANSION_MAX = max(
    0,
    min(int(os.getenv("SEMANTIC_SEARCH_QUERY_EXPANSION_MAX", "3")), 5),
)
SEMANTIC_SEARCH_V2_MAX_MATCHED_ENTITIES = max(
    1,
    min(int(os.getenv("SEMANTIC_SEARCH_V2_MAX_MATCHED_ENTITIES", "4")), 8),
)
SEMANTIC_SEARCH_V2_MAX_TERMS_PER_ENTITY = max(
    1,
    min(int(os.getenv("SEMANTIC_SEARCH_V2_MAX_TERMS_PER_ENTITY", "4")), 8),
)
SEMANTIC_SEARCH_V2_MAX_EXPANSION_CHARACTERS = max(
    80,
    min(int(os.getenv("SEMANTIC_SEARCH_V2_MAX_EXPANSION_CHARACTERS", "600")), 1200),
)
SEMANTIC_SEARCH_V2_MAX_RECOGNITION_SPANS = max(
    64,
    min(int(os.getenv("SEMANTIC_SEARCH_V2_MAX_RECOGNITION_SPANS", "512")), 1024),
)
SEMANTIC_SEARCH_V2_QUERY_EXPANSION_ENABLED = env_bool(
    "SEMANTIC_SEARCH_V2_QUERY_EXPANSION_ENABLED",
    True,
)
SEMANTIC_SEARCH_V2_RERANK_PROVIDER = os.getenv(
    "SEMANTIC_SEARCH_V2_RERANK_PROVIDER",
    "rules",
).strip().casefold()
if SEMANTIC_SEARCH_V2_RERANK_PROVIDER not in {"rules", "local_http"}:
    SEMANTIC_SEARCH_V2_RERANK_PROVIDER = "rules"
SEMANTIC_SEARCH_V2_RERANK_URL = os.getenv("SEMANTIC_SEARCH_V2_RERANK_URL", "").strip()
SEMANTIC_SEARCH_V2_RERANK_MODEL = os.getenv(
    "SEMANTIC_SEARCH_V2_RERANK_MODEL",
    "Qwen/Qwen3-Reranker-0.6B",
).strip()
SEMANTIC_SEARCH_V2_RERANK_API_KEY = os.getenv(
    "SEMANTIC_SEARCH_V2_RERANK_API_KEY",
    "",
)
SEMANTIC_SEARCH_V2_RERANK_ALLOWED_HOSTS = os.getenv(
    "SEMANTIC_SEARCH_V2_RERANK_ALLOWED_HOSTS",
    "reranker,localhost,127.0.0.1",
)
SEMANTIC_SEARCH_V2_RERANK_TIMEOUT_SECONDS = max(
    2,
    min(int(os.getenv("SEMANTIC_SEARCH_V2_RERANK_TIMEOUT_SECONDS", "15")), 60),
)
SEMANTIC_SEARCH_V2_RERANK_MAX_TEXT_CHARS = max(
    500,
    min(int(os.getenv("SEMANTIC_SEARCH_V2_RERANK_MAX_TEXT_CHARS", "4000")), 8000),
)
AI_PROVIDER = os.getenv("AI_PROVIDER", "none")
AI_BASE_URL = os.getenv("AI_BASE_URL", "")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_METADATA_MODEL = os.getenv("AI_METADATA_MODEL", "")
AI_CLASSIFIER_MODEL = os.getenv("AI_CLASSIFIER_MODEL", "")
AI_VISION_MODEL = os.getenv("AI_VISION_MODEL", "")
AI_LIBRARY_MODEL = os.getenv("AI_LIBRARY_MODEL", "")
AI_LIBRARY_TEMPERATURE = min(
    2.0,
    max(0.0, float(os.getenv("AI_LIBRARY_TEMPERATURE", "0.2"))),
)
AI_LIBRARY_MAX_CONCURRENCY = max(
    1,
    min(int(os.getenv("AI_LIBRARY_MAX_CONCURRENCY", "2")), 8),
)
AI_LIBRARY_MAX_OUTPUT_TOKENS = max(
    128,
    min(int(os.getenv("AI_LIBRARY_MAX_OUTPUT_TOKENS", "2048")), 8192),
)
AI_LIBRARY_MAX_OUTPUT_CHARS = max(
    1000,
    min(int(os.getenv("AI_LIBRARY_MAX_OUTPUT_CHARS", "12000")), 50000),
)
LIBRARY_QA_MAX_QUESTION_CHARS = max(
    200,
    min(int(os.getenv("LIBRARY_QA_MAX_QUESTION_CHARS", "4000")), 8000),
)
LIBRARY_QA_MAX_HISTORY_MESSAGES = max(
    0,
    min(int(os.getenv("LIBRARY_QA_MAX_HISTORY_MESSAGES", "8")), 20),
)
LIBRARY_RAG_MAX_PASSAGES = max(
    1,
    min(int(os.getenv("LIBRARY_RAG_MAX_PASSAGES", "8")), 16),
)
LIBRARY_RAG_MAX_EVIDENCE_CHARS = max(
    1000,
    min(int(os.getenv("LIBRARY_RAG_MAX_EVIDENCE_CHARS", "9000")), 24000),
)
LIBRARY_RAG_PER_WORK_CAP = max(
    1,
    min(int(os.getenv("LIBRARY_RAG_PER_WORK_CAP", "2")), 6),
)
LIBRARY_RAG_COMPARISON_PER_ANCHOR = max(
    1,
    min(int(os.getenv("LIBRARY_RAG_COMPARISON_PER_ANCHOR", "2")), 4),
)
LIBRARY_RAG_MAX_ENTITY_BRANCHES = max(
    1,
    min(int(os.getenv("LIBRARY_RAG_MAX_ENTITY_BRANCHES", "3")), 4),
)
AI_TIMEOUT = max(3, min(int(os.getenv("AI_TIMEOUT", "60")), 600))
AI_MAX_CONCURRENCY = max(1, min(int(os.getenv("AI_MAX_CONCURRENCY", "1")), 8))
AI_MAX_INPUT_CHARS = max(1000, min(int(os.getenv("AI_MAX_INPUT_CHARS", "16000")), 100000))
AI_ALLOWED_HOSTS = tuple(
    value.strip()
    for value in os.getenv("AI_ALLOWED_HOSTS", "localhost,127.0.0.1,ollama,vllm").split(",")
    if value.strip()
)
AI_AUTHORITY_RERANK_ENABLED = os.getenv("AI_AUTHORITY_RERANK_ENABLED", "false").lower() == "true"
AUTHORITY_PROVIDER_ENABLED = os.getenv(
    "AUTHORITY_PROVIDER_ENABLED",
    "wikidata,viaf,loc,openalex",
)
AUTHORITY_PROVIDER_ALLOWED_HOSTS = os.getenv(
    "AUTHORITY_PROVIDER_ALLOWED_HOSTS",
    "www.wikidata.org,viaf.org,id.loc.gov,api.openalex.org",
)
AUTHORITY_PROVIDER_TIMEOUT_SECONDS = max(
    2,
    min(int(os.getenv("AUTHORITY_PROVIDER_TIMEOUT_SECONDS", "8")), 30),
)
AUTHORITY_PROVIDER_RETRIES = max(
    0,
    min(int(os.getenv("AUTHORITY_PROVIDER_RETRIES", "1")), 2),
)
AUTHORITY_PROVIDER_MIN_INTERVAL_MS = max(
    0,
    min(int(os.getenv("AUTHORITY_PROVIDER_MIN_INTERVAL_MS", "200")), 5000),
)
AUTHORITY_PROVIDER_VERIFY_DNS = os.getenv(
    "AUTHORITY_PROVIDER_VERIFY_DNS",
    "true",
).lower() == "true"
METADATA_PROVIDER_TIMEOUT_SECONDS = max(
    3,
    min(int(os.getenv("METADATA_PROVIDER_TIMEOUT_SECONDS", "12")), 120),
)
METADATA_PROVIDER_RETRIES = max(
    0,
    min(int(os.getenv("METADATA_PROVIDER_RETRIES", "1")), 3),
)
METADATA_PROVIDER_CACHE_SECONDS = max(
    60,
    min(int(os.getenv("METADATA_PROVIDER_CACHE_SECONDS", "86400")), 2592000),
)
METADATA_PROVIDER_CIRCUIT_FAILURES = max(
    1,
    min(int(os.getenv("METADATA_PROVIDER_CIRCUIT_FAILURES", "3")), 10),
)
METADATA_PROVIDER_CIRCUIT_SECONDS = max(
    10,
    min(int(os.getenv("METADATA_PROVIDER_CIRCUIT_SECONDS", "300")), 3600),
)
METADATA_PROVIDER_MIN_INTERVAL_MS = max(
    0,
    min(int(os.getenv("METADATA_PROVIDER_MIN_INTERVAL_MS", "150")), 5000),
)
METADATA_PROVIDER_MAX_RESPONSE_BYTES = max(
    16384,
    min(int(os.getenv("METADATA_PROVIDER_MAX_RESPONSE_BYTES", "1048576")), 5242880),
)
METADATA_PROVIDER_ENABLED = os.getenv(
    "METADATA_PROVIDER_ENABLED",
    "crossref,openlibrary,google_books",
)
METADATA_PROVIDER_ALLOWED_HOSTS = os.getenv(
    "METADATA_PROVIDER_ALLOWED_HOSTS",
    "api.crossref.org,openlibrary.org,www.googleapis.com,api.openalex.org",
)
FIELD_ENRICHMENT_WEB_SEARCH_ADAPTER = os.getenv(
    "FIELD_ENRICHMENT_WEB_SEARCH_ADAPTER",
    "searxng",
).strip().lower()
FIELD_ENRICHMENT_SEARXNG_URL = os.getenv("FIELD_ENRICHMENT_SEARXNG_URL", "").strip()
FIELD_ENRICHMENT_SEARCH_ALLOWED_HOSTS = os.getenv(
    "FIELD_ENRICHMENT_SEARCH_ALLOWED_HOSTS",
    "",
)
FIELD_ENRICHMENT_SEARCH_TIMEOUT_SECONDS = max(
    2,
    min(int(os.getenv("FIELD_ENRICHMENT_SEARCH_TIMEOUT_SECONDS", "8")), 30),
)
FIELD_ENRICHMENT_SEARCH_RETRIES = max(
    0,
    min(int(os.getenv("FIELD_ENRICHMENT_SEARCH_RETRIES", "1")), 2),
)
FIELD_ENRICHMENT_SEARCH_MIN_INTERVAL_MS = max(
    0,
    min(int(os.getenv("FIELD_ENRICHMENT_SEARCH_MIN_INTERVAL_MS", "200")), 5000),
)
FIELD_ENRICHMENT_SEARCH_MAX_BYTES = max(
    16384,
    min(int(os.getenv("FIELD_ENRICHMENT_SEARCH_MAX_BYTES", "524288")), 2097152),
)
FIELD_ENRICHMENT_SEARCH_CACHE_SECONDS = max(
    60,
    min(int(os.getenv("FIELD_ENRICHMENT_SEARCH_CACHE_SECONDS", "86400")), 2592000),
)
FIELD_ENRICHMENT_FETCH_TIMEOUT_SECONDS = max(
    2,
    min(int(os.getenv("FIELD_ENRICHMENT_FETCH_TIMEOUT_SECONDS", "10")), 30),
)
FIELD_ENRICHMENT_FETCH_RETRIES = max(
    0,
    min(int(os.getenv("FIELD_ENRICHMENT_FETCH_RETRIES", "1")), 2),
)
FIELD_ENRICHMENT_FETCH_MAX_BYTES = max(
    16384,
    min(int(os.getenv("FIELD_ENRICHMENT_FETCH_MAX_BYTES", "1048576")), 5242880),
)
FIELD_ENRICHMENT_FETCH_TEXT_CHARS = max(
    4000,
    min(int(os.getenv("FIELD_ENRICHMENT_FETCH_TEXT_CHARS", "120000")), 500000),
)
FIELD_ENRICHMENT_FETCH_REDIRECT_LIMIT = max(
    0,
    min(int(os.getenv("FIELD_ENRICHMENT_FETCH_REDIRECT_LIMIT", "3")), 5),
)
FIELD_ENRICHMENT_FETCH_MIN_INTERVAL_MS = max(
    0,
    min(int(os.getenv("FIELD_ENRICHMENT_FETCH_MIN_INTERVAL_MS", "250")), 5000),
)
FIELD_ENRICHMENT_FETCH_CACHE_SECONDS = max(
    60,
    min(int(os.getenv("FIELD_ENRICHMENT_FETCH_CACHE_SECONDS", "86400")), 2592000),
)
FIELD_ENRICHMENT_MAX_SEARCH_QUERIES = max(
    1,
    min(int(os.getenv("FIELD_ENRICHMENT_MAX_SEARCH_QUERIES", "8")), 16),
)
FIELD_ENRICHMENT_SEARCH_RESULTS_PER_QUERY = max(
    1,
    min(int(os.getenv("FIELD_ENRICHMENT_SEARCH_RESULTS_PER_QUERY", "5")), 10),
)
FIELD_ENRICHMENT_MAX_FETCHED_DOCUMENTS = max(
    1,
    min(int(os.getenv("FIELD_ENRICHMENT_MAX_FETCHED_DOCUMENTS", "12")), 24),
)
ANONYMOUS_EVENT_RETENTION_DAYS = max(
    7,
    min(int(os.getenv("ANONYMOUS_EVENT_RETENTION_DAYS", "90")), 365),
)
PADDLEOCR_SERVICE_URL = os.getenv("PADDLEOCR_SERVICE_URL", "")
OCR_REMOTE_API_URL = os.getenv("OCR_REMOTE_API_URL", "")
OCR_REMOTE_API_KEY = os.getenv("OCR_REMOTE_API_KEY", "")
OCR_REMOTE_MODEL = os.getenv("OCR_REMOTE_MODEL", "")
OCR_REQUEST_TIMEOUT_SECONDS = int(os.getenv("OCR_REQUEST_TIMEOUT_SECONDS", str(60 * 60)))
OCR_PAGE_BATCH_SIZE = max(
    1,
    min(int(os.getenv("OCR_PAGE_BATCH_SIZE", "4")), 50),
)
COVER_SCAN_MAX_PAGES = max(4, min(int(os.getenv("COVER_SCAN_MAX_PAGES", "12")), 24))
COVER_AUTO_SELECT_THRESHOLD = float(os.getenv("COVER_AUTO_SELECT_THRESHOLD", "0.52"))
GROBID_SERVICE_URL = os.getenv("GROBID_SERVICE_URL", "")
GOOGLE_BOOKS_API_KEY = os.getenv("GOOGLE_BOOKS_API_KEY", "").strip()
OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY", "").strip()

NAS_ORIGINAL_ROOT = Path(os.getenv("NAS_ORIGINAL_ROOT", MEDIA_ROOT / "originals"))
NAS_PUBLIC_ROOT = Path(os.getenv("NAS_PUBLIC_ROOT", MEDIA_ROOT / "public"))
NAS_BACKUP_ROOT = Path(os.getenv("NAS_BACKUP_ROOT", MEDIA_ROOT / "backups"))
PUBLIC_WEB_URL = os.getenv("PUBLIC_WEB_URL", "http://localhost:3000")
PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "http://localhost:8000")
REQUIRE_CLOUD_FOR_PUBLICATION = env_bool("REQUIRE_CLOUD_FOR_PUBLICATION", False)
ALLOW_LOCAL_PUBLIC_ASSET_ACCESS = env_bool("ALLOW_LOCAL_PUBLIC_ASSET_ACCESS", DEBUG)
X_ACCEL_REDIRECT_ENABLED = env_bool("X_ACCEL_REDIRECT_ENABLED", False)
X_ACCEL_REDIRECT_PREFIX = os.getenv("X_ACCEL_REDIRECT_PREFIX", "/__protected_assets/")
HEAVY_TASK_WINDOW_START = max(0, min(int(os.getenv("HEAVY_TASK_WINDOW_START", "1")), 23))
HEAVY_TASK_WINDOW_END = max(0, min(int(os.getenv("HEAVY_TASK_WINDOW_END", "7")), 23))
AUTO_PUBLISH_MIN_CONFIDENCE = float(os.getenv("AUTO_PUBLISH_MIN_CONFIDENCE", "0.88"))
REQUIRE_EXTERNAL_SEARCH = env_bool("REQUIRE_EXTERNAL_SEARCH", False)
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(1024 * 1024 * 1024)))
MAX_UPLOAD_CHUNK_BYTES = max(
    1024 * 1024,
    min(int(os.getenv("MAX_UPLOAD_CHUNK_BYTES", str(8 * 1024 * 1024))), 32 * 1024 * 1024),
)
R2_UPLOAD_STAGING_ENABLED = env_bool("R2_UPLOAD_STAGING_ENABLED", False)
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "").strip()
R2_ENDPOINT = os.getenv(
    "R2_ENDPOINT",
    f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com" if R2_ACCOUNT_ID else "",
).strip().rstrip("/")
R2_BUCKET = os.getenv("R2_BUCKET", "").strip()
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_REGION = os.getenv("R2_REGION", "auto").strip() or "auto"
R2_UPLOAD_PART_SIZE = max(
    5 * 1024 * 1024,
    min(int(os.getenv("R2_UPLOAD_PART_SIZE", str(8 * 1024 * 1024))), 512 * 1024 * 1024),
)
R2_PRESIGNED_URL_TTL_SECONDS = max(
    300,
    min(int(os.getenv("R2_PRESIGNED_URL_TTL_SECONDS", "900")), 3600),
)
R2_MAX_ACTIVE_UPLOADS_PER_USER = max(
    1,
    min(int(os.getenv("R2_MAX_ACTIVE_UPLOADS_PER_USER", "5")), 20),
)
R2_SIGN_PART_BATCH_SIZE = max(
    1,
    min(int(os.getenv("R2_SIGN_PART_BATCH_SIZE", "12")), 24),
)
R2_IMPORT_CHUNK_BYTES = max(
    1024 * 1024,
    min(int(os.getenv("R2_IMPORT_CHUNK_BYTES", str(8 * 1024 * 1024))), 64 * 1024 * 1024),
)
R2_CLEANUP_MAX_ATTEMPTS = max(
    1,
    min(int(os.getenv("R2_CLEANUP_MAX_ATTEMPTS", "12")), 48),
)
R2_UPLOAD_CORS_ALLOWED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "R2_UPLOAD_CORS_ALLOWED_ORIGINS",
        ",".join(
            [
                os.getenv("PUBLIC_WEB_URL", "http://localhost:3000"),
                "http://localhost:3000",
                "http://127.0.0.1:3000",
            ]
        ),
    ).split(",")
    if origin.strip()
]
FILE_UPLOAD_MAX_MEMORY_SIZE = min(
    max(
        int(os.getenv("FILE_UPLOAD_MAX_MEMORY_SIZE", str(10 * 1024 * 1024))),
        MAX_UPLOAD_CHUNK_BYTES + 512 * 1024,
    ),
    64 * 1024 * 1024,
)
MAX_PDF_PAGES = int(os.getenv("MAX_PDF_PAGES", "5000"))
THEORY_SYSTEM_ENABLED = env_bool("THEORY_SYSTEM_ENABLED", True)

EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "console").strip().lower()
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "common.email_backend.BrevoEmailBackend"
    if EMAIL_PROVIDER == "brevo"
    else "django.core.mail.backends.console.EmailBackend",
)
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL",
    os.getenv("EMAIL_FROM_ADDRESS", "noreply@example.invalid"),
)
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "社会理论书库")
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
READER_SUBMISSION_EMAIL = os.getenv("READER_SUBMISSION_EMAIL", "")
LIBRARY_OWNER_EMAIL = os.getenv("LIBRARY_OWNER_EMAIL", "owner@example.com").strip().lower()
PRIVATE_DATA_ENCRYPTION_KEY = os.getenv("PRIVATE_DATA_ENCRYPTION_KEY", "")
S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID", "")
S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY", "")
S3_SESSION_TOKEN = os.getenv("S3_SESSION_TOKEN", "")
S3_SIGNED_URL_TTL_SECONDS = max(
    300,
    min(int(os.getenv("S3_SIGNED_URL_TTL_SECONDS", "900")), 86400),
)

if os.getenv("INTAKE_STORAGE_BACKEND", "filesystem").strip().lower() == "s3":
    STORAGES["intake"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": os.getenv("INTAKE_S3_BUCKET", ""),
            "endpoint_url": os.getenv("INTAKE_S3_ENDPOINT_URL") or None,
            "region_name": os.getenv("INTAKE_S3_REGION") or None,
            "access_key": os.getenv("INTAKE_S3_ACCESS_KEY_ID") or None,
            "secret_key": os.getenv("INTAKE_S3_SECRET_ACCESS_KEY") or None,
            "security_token": os.getenv("INTAKE_S3_SESSION_TOKEN") or None,
            "location": os.getenv("INTAKE_S3_PREFIX", "private-intake"),
            "default_acl": None,
            "querystring_auth": True,
            "file_overwrite": False,
        },
    }
else:
    STORAGES["intake"] = {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {},
    }

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", False)
SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", not DEBUG)
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = os.getenv(
    "DJANGO_X_FRAME_OPTIONS",
    "DENY" if PUBLIC_DEPLOYMENT_MODE else "SAMEORIGIN",
)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_HSTS_PRELOAD", False)
USE_X_FORWARDED_HOST = env_bool("DJANGO_USE_X_FORWARDED_HOST", PUBLIC_DEPLOYMENT_MODE)


if PUBLIC_DEPLOYMENT_MODE:
    production_errors = []
    lowered_secret = SECRET_KEY.lower()
    if DEBUG:
        production_errors.append("DJANGO_DEBUG 必须为 false")
    if len(SECRET_KEY) < 50 or any(marker in lowered_secret for marker in ("dev-only", "change", "replace")):
        production_errors.append("DJANGO_SECRET_KEY 必须是至少 50 位的随机值")
    if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
        production_errors.append("DJANGO_ALLOWED_HOSTS 不能使用通配符")
    invalid_csrf_origins = [
        origin
        for origin in CSRF_TRUSTED_ORIGINS
        if not origin.startswith("https://") and origin not in LAN_HTTP_TRUSTED_ORIGINS
    ]
    invalid_cors_origins = [
        origin
        for origin in CORS_ALLOWED_ORIGINS
        if not origin.startswith("https://") and origin not in LAN_HTTP_TRUSTED_ORIGINS
    ]
    if not CSRF_TRUSTED_ORIGINS or invalid_csrf_origins:
        production_errors.append("CSRF 信任来源必须使用 HTTPS，或属于明确配置的局域网入口")
    if invalid_cors_origins:
        production_errors.append("CORS 来源必须使用 HTTPS，或属于明确配置的局域网入口")
    if LAN_HTTP_TRUSTED_ORIGINS and (not LAN_HOST or len(LAN_PROXY_TOKEN) < 32):
        production_errors.append("启用局域网 HTTP 管理时必须配置 LAN_HOST 和至少 32 位的 LAN_PROXY_TOKEN")
    if not SECURE_SSL_REDIRECT or not SESSION_COOKIE_SECURE or not CSRF_COOKIE_SECURE:
        production_errors.append("必须启用 HTTPS 重定向和安全 Cookie")
    if not JWT_COOKIE_AUTH_ENABLED or JWT_RETURN_TOKENS_IN_BODY:
        production_errors.append("公网模式必须使用 HttpOnly Cookie，且不得在响应正文返回登录令牌")
    if len(INTERNAL_API_TOKEN) < 32 or any(
        marker in INTERNAL_API_TOKEN.lower()
        for marker in ("change", "replace", "example")
    ):
        production_errors.append("INTERNAL_API_TOKEN 必须使用至少 32 位的独立随机值")
    if SECURE_HSTS_SECONDS < 86400:
        production_errors.append("DJANGO_HSTS_SECONDS 至少应为 86400")
    if not PUBLIC_WEB_URL.startswith("https://") or not PUBLIC_API_URL.startswith("https://"):
        production_errors.append("PUBLIC_WEB_URL 与 PUBLIC_API_URL 必须使用 HTTPS")
    if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
        production_errors.append("公网模式必须使用 PostgreSQL")
    if not CACHE_URL:
        production_errors.append("公网模式必须配置受保护的 Redis 缓存")
    if len(MEILISEARCH_MASTER_KEY) < 16:
        production_errors.append("MEILISEARCH_MASTER_KEY 至少需要 16 位")
    if not PRIVATE_DATA_ENCRYPTION_KEY or any(
        marker in PRIVATE_DATA_ENCRYPTION_KEY.lower()
        for marker in ("change", "replace")
    ):
        production_errors.append("PRIVATE_DATA_ENCRYPTION_KEY 必须使用稳定的独立密钥")
    if not REQUIRE_CLOUD_FOR_PUBLICATION and not ALLOW_LOCAL_PUBLIC_ASSET_ACCESS:
        production_errors.append("未启用云端强制发布时，必须允许 Nginx 读取本地公开副本")
    if ALLOW_LOCAL_PUBLIC_ASSET_ACCESS and not X_ACCEL_REDIRECT_ENABLED:
        production_errors.append("公网开放本地 PDF 时必须启用 X-Accel-Redirect")
    if (
        not X_ACCEL_REDIRECT_PREFIX.startswith("/")
        or not X_ACCEL_REDIRECT_PREFIX.endswith("/")
        or ".." in X_ACCEL_REDIRECT_PREFIX
        or "//" in X_ACCEL_REDIRECT_PREFIX
    ):
        production_errors.append("X_ACCEL_REDIRECT_PREFIX 必须是安全的站内绝对路径并以 / 结尾")
    if production_errors:
        raise ImproperlyConfigured("公网安全配置不完整：" + "；".join(production_errors))
