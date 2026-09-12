"""Aggregate legacy table reads, without storing SQL, values or user identity."""
from collections import Counter
from datetime import timedelta
import logging
import re

from django.core.cache import cache
from django.db import connection
from django.utils import timezone

log = logging.getLogger("library.legacy_reads")
LEGACY_TABLES = {"catalog_theoryschool": "TheorySchool", "catalog_concept": "Concept",
                 "catalog_workknowledgerelation": "WorkKnowledgeRelation", "catalog_personknowledgerelation": "PersonKnowledgeRelation",
                 "ingestion_metadatacandidate": "MetadataCandidate", "ingestion_entityresolutioncandidate": "EntityResolutionCandidate"}
TABLE_PATTERN = re.compile(r'\b(?:FROM|JOIN)\s+["`]?(' + "|".join(LEGACY_TABLES) + r')["`]?\b', re.I)
RETENTION_SECONDS = 8 * 86400


def record_legacy_reads(counts):
    day = timezone.now().date().isoformat()
    try:
        cache.add(f"legacy-read:{day}:started_at", timezone.now().isoformat(), RETENTION_SECONDS)
        for name, count in counts.items():
            if name not in LEGACY_TABLES.values() or count < 1:
                continue
            key = f"legacy-read:{day}:{name}"
            cache.add(key, 0, RETENTION_SECONDS)
            cache.incr(key, count)
        if counts:
            log.info("legacy_read_counts date=%s counts=%s", day, dict(counts))
    except Exception:
        # Telemetry does not grant access or disguise the business response.
        log.warning("legacy_read_telemetry_unavailable", exc_info=False)


def legacy_read_snapshot(days=7):
    days = min(7, max(1, int(days)))
    today = timezone.now().date()
    try:
        readings = []
        for offset in range(days):
            day = (today - timedelta(days=offset)).isoformat()
            started = cache.get(f"legacy-read:{day}:started_at")
            readings.append({"date": day, "observed_from": started,
                             "counts": {name: cache.get(f"legacy-read:{day}:{name}", 0) for name in LEGACY_TABLES.values()}})
        return {"available": True, "scope": "synchronous_catalog_http_sql", "days": readings,
                "retirement_proven": False, "note": "Unobserved days, background tasks and raw SQL outside this scope are not proof of zero reads."}
    except Exception:
        return {"available": False, "scope": "synchronous_catalog_http_sql", "days": [], "retirement_proven": False}


class LegacyReadTelemetryMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(("/api/catalog/", "/api/ingestion/")):
            return self.get_response(request)
        counts = Counter()
        def capture(execute, sql, params, many, context):
            result = execute(sql, params, many, context)
            if sql.lstrip().upper().startswith(("SELECT", "WITH")):
                counts.update(LEGACY_TABLES[name.lower()] for name in set(TABLE_PATTERN.findall(sql)))
            return result
        with connection.execute_wrapper(capture):
            response = self.get_response(request)
        # Even zero-read requests establish the measurement start, not a
        # retroactive clean observation window. Streaming is out of scope.
        record_legacy_reads(counts)
        return response
