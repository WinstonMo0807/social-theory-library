from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.http import JsonResponse
from django.urls import include, path

from .version import APP_VERSION


def health(request):
    return JsonResponse(
        {
            "status": "ok",
            "service": "social-theory-library-api",
            "version": APP_VERSION,
        }
    )


def readiness_state():
    """Return a minimal deployment readiness result without leaking schema details."""
    connection = connections["default"]
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        executor = MigrationExecutor(connection)
        pending_count = len(
            executor.migration_plan(executor.loader.graph.leaf_nodes())
        )
    except Exception:
        return {
            "status": "not_ready",
            "service": "social-theory-library-api",
            "version": APP_VERSION,
            "database": False,
            "pending_migrations": None,
        }

    return {
        "status": "ready" if pending_count == 0 else "not_ready",
        "service": "social-theory-library-api",
        "version": APP_VERSION,
        "database": True,
        "pending_migrations": pending_count,
    }


def ready(request):
    state = readiness_state()
    return JsonResponse(state, status=200 if state["status"] == "ready" else 503)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health),
    path("api/ready/", ready),
    path("api/auth/", include("accounts.urls")),
    path("api/catalog/", include("catalog.urls")),
    path("api/ingestion/", include("ingestion.urls")),
    path("api/reading/", include("reading.urls")),
    path("api/distribution/", include("distribution.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
