from __future__ import annotations

from pathlib import Path
import tempfile
import time
import uuid

import fitz
import httpx
from django.conf import settings
from django.db import connection
from django.utils import timezone

from catalog.models import (
    Asset,
    Edition,
    PublicationEvent,
    PublicationState,
    RecommendationSnapshot,
)
from catalog.services.semantic_search import (
    current_semantic_runtime,
    semantic_model_health,
    semantic_search,
)
from ingestion.models import ProcessingJob
from ingestion.services.health import (
    cache_health,
    celery_broker_health,
    http_service_health,
    worker_runtime_status,
)
from ingestion.services.indexing import _headers, _wait_task
from ingestion.services.ocr_provider import ocr_runtime_config, parse_pdf_with_ocr
from ingestion.services.provider_gateway import provider_configuration_health


def _component(configured, available, *, last_success=None, last_error="", detail=""):
    return {
        "configured": bool(configured),
        "available": available,
        "last_successful_check": last_success,
        "last_error": last_error,
        "detail": detail,
    }


def system_health_snapshot() -> dict:
    checked_at = timezone.now()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        database = _component(True, True, last_success=checked_at)
    except Exception as exc:
        database = _component(True, False, last_error=str(exc)[:1000])

    asset = Asset.objects.filter(
        kind=Asset.Kind.ORIGINAL,
        status=Asset.Status.READY,
        is_current=True,
    ).order_by("-updated_at").first()
    storage_error = ""
    storage_available = None
    if asset is not None:
        try:
            with asset.file.open("rb") as handle:
                storage_available = handle.read(5) == b"%PDF-"
            if not storage_available:
                storage_error = "最近的原始文件没有有效 PDF 文件头。"
        except Exception as exc:
            storage_available = False
            storage_error = str(exc)[:1000]
    storage = _component(
        asset is not None,
        storage_available,
        last_success=checked_at if storage_available else None,
        last_error=storage_error,
        detail="只读抽查最近的原始 PDF。" if asset else "尚无可抽查的原始 PDF。",
    )

    cache = cache_health(probe_key="system-health:cache")
    broker = celery_broker_health()
    heartbeat = worker_runtime_status()
    worker = _component(
        True,
        heartbeat["online"],
        last_success=heartbeat["heartbeat_at"] or heartbeat["checked_at"] or None,
        last_error="" if heartbeat["online"] else heartbeat["detail"],
        detail=heartbeat,
    )

    ocr_config = ocr_runtime_config()
    ocr_http = http_service_health(ocr_config["nas_url"], "/ready", timeout=5)
    last_ocr = ProcessingJob.objects.filter(
        job_type=ProcessingJob.JobType.OCR,
    ).order_by("-created_at").first()
    ocr = _component(
        bool(ocr_config["nas_url"]),
        ocr_http.get("reachable", False),
        last_success=(
            last_ocr.finished_at
            if last_ocr and last_ocr.status == ProcessingJob.Status.SUCCEEDED
            else None
        ),
        last_error=(last_ocr.error_message if last_ocr else "")
        or ("" if ocr_http.get("reachable") else str(ocr_http.get("detail") or "")),
        detail=str(ocr_http.get("detail") or ""),
    )

    remote_complete = bool(
        ocr_config["remote_url"]
        and ocr_config["remote_model"]
        and ocr_config["remote_key_configured"]
    )
    remote_http = (
        http_service_health(ocr_config["remote_url"], "/health", timeout=3)
        if remote_complete
        else {"reachable": False, "detail": "远程 URL、API Key 或模型配置不完整。"}
    )
    remote_ocr = _component(
        remote_complete,
        remote_http.get("reachable", False),
        last_success=checked_at if remote_http.get("reachable") else None,
        last_error="" if remote_http.get("reachable") else str(remote_http.get("detail") or ""),
        detail=str(remote_http.get("detail") or ""),
    )

    meili_http = http_service_health(settings.MEILISEARCH_URL, "/health", timeout=3)
    meilisearch = _component(
        bool(settings.MEILISEARCH_URL),
        meili_http.get("reachable", False),
        last_success=checked_at if meili_http.get("reachable") else None,
        last_error="" if meili_http.get("reachable") else str(meili_http.get("detail") or ""),
        detail=str(meili_http.get("detail") or ""),
    )
    semantic_config = current_semantic_runtime()
    model_health = semantic_model_health(semantic_config)
    embedding = _component(
        model_health["configured"],
        model_health["available"],
        last_success=checked_at if model_health["available"] else None,
        last_error="" if model_health["available"] else model_health["reason"],
        detail=model_health,
    )
    provider_health = provider_configuration_health()
    enabled_providers = [value for value in provider_health if value["enabled"]]
    provider_errors = [
        f"{value['provider']}: {value['status']}"
        for value in enabled_providers
        if value["status"] != "configured"
    ]
    metadata_providers = _component(
        bool(enabled_providers),
        bool(enabled_providers) and not provider_errors,
        last_success=checked_at if enabled_providers and not provider_errors else None,
        last_error="；".join(provider_errors),
        detail={
            "check_kind": "configuration_only",
            "providers": provider_health,
            "note": "此项不发送网络请求；真实请求结果记录在 SourceRecord。",
        },
    )

    latest_publication = Edition.objects.filter(
        state=PublicationState.PUBLISHED,
    ).order_by("-last_published_at", "-published_at").first()
    latest_event = PublicationEvent.objects.filter(completed_at__isnull=False).order_by(
        "-completed_at"
    ).first()
    stale_search = Edition.objects.filter(
        state=PublicationState.PUBLISHED,
        search_indexed_at__isnull=True,
    ).count()
    current_recommendations = RecommendationSnapshot.objects.filter(is_current=True).count()
    catalog = _component(
        True,
        stale_search == 0,
        last_success=latest_event.completed_at if latest_event else None,
        last_error=(f"{stale_search} 个已发布版本没有全文索引时间。" if stale_search else ""),
        detail={
            "latest_publication": (
                latest_publication.last_published_at or latest_publication.published_at
                if latest_publication
                else None
            ),
            "latest_catalog_event": latest_event.completed_at if latest_event else None,
            "current_recommendation_snapshots": current_recommendations,
        },
    )

    return {
        "checked_at": checked_at,
        "components": {
            "database": database,
            "storage": storage,
            "cache": _component(
                True,
                cache.get("reachable", False),
                last_success=checked_at if cache.get("reachable") else None,
                last_error="" if cache.get("reachable") else str(cache.get("detail") or ""),
                detail=cache,
            ),
            "broker": _component(
                True,
                broker.get("reachable", False),
                last_success=checked_at if broker.get("reachable") else None,
                last_error="" if broker.get("reachable") else str(broker.get("detail") or ""),
                detail=broker,
            ),
            "worker": worker,
            "paddleocr": ocr,
            "remote_ocr": remote_ocr,
            "meilisearch": meilisearch,
            "embedding_model": embedding,
            "metadata_providers": metadata_providers,
            "public_catalog_freshness": catalog,
        },
    }


def _scanned_probe_pdf(path: Path) -> None:
    source = fitz.open()
    page = source.new_page(width=360, height=240)
    page.insert_text((32, 110), "System health OCR 2026", fontsize=18)
    pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
    image = pixmap.tobytes("png")
    source.close()
    scanned = fitz.open()
    target = scanned.new_page(width=360, height=240)
    target.insert_image(target.rect, stream=image)
    scanned.save(path)
    scanned.close()


def run_end_to_end_self_test() -> dict:
    started = time.monotonic()
    steps = {}
    with tempfile.TemporaryDirectory(prefix="library-system-health-") as temporary:
        path = Path(temporary) / "probe.pdf"
        _scanned_probe_pdf(path)
        document = fitz.open(path)
        steps["pdf_parse"] = {
            "available": document.page_count == 1,
            "page_count": document.page_count,
        }
        pixmap = document[0].get_pixmap(matrix=fitz.Matrix(0.5, 0.5), alpha=False)
        steps["page_retrieval"] = {
            "available": bool(pixmap.width and pixmap.height),
            "width": pixmap.width,
            "height": pixmap.height,
        }
        document.close()
        try:
            payload, provider = parse_pdf_with_ocr(path)
            steps["ocr"] = {
                "available": bool(payload.get("pages")),
                "engine": provider,
                "pages": len(payload.get("pages", [])),
            }
        except Exception as exc:
            steps["ocr"] = {"available": False, "error": str(exc)[:1000]}

    probe_index = f"system_health_probe_{uuid.uuid4().hex[:12]}"
    probe_id = str(uuid.uuid4())
    probe_created = False
    probe_result = {"available": False, "probe_cleaned": False}
    try:
        base = settings.MEILISEARCH_URL.rstrip("/")
        created = httpx.post(
            f"{base}/indexes",
            headers=_headers(),
            json={"uid": probe_index, "primaryKey": "id"},
            timeout=5,
        )
        created.raise_for_status()
        _wait_task(created.json(), timeout=20)
        probe_created = True
        written = httpx.post(
            f"{base}/indexes/{probe_index}/documents",
            headers=_headers(),
            json=[{"id": probe_id, "text": "system health probe"}],
            timeout=5,
        )
        written.raise_for_status()
        _wait_task(written.json(), timeout=20)
        searched = httpx.post(
            f"{base}/indexes/{probe_index}/search",
            headers=_headers(),
            json={"q": "health", "limit": 5},
            timeout=5,
        )
        searched.raise_for_status()
        found = any(str(hit.get("id")) == probe_id for hit in searched.json().get("hits", []))
        probe_result["available"] = found
    except Exception as exc:
        probe_result["error"] = str(exc)[:1000]
    finally:
        if probe_created:
            try:
                deleted = httpx.delete(
                    f"{settings.MEILISEARCH_URL.rstrip('/')}/indexes/{probe_index}",
                    headers=_headers(),
                    timeout=5,
                )
                deleted.raise_for_status()
                _wait_task(deleted.json(), timeout=20)
                probe_result["probe_cleaned"] = True
            except Exception as exc:
                probe_result["cleanup_error"] = str(exc)[:1000]
        steps["meilisearch_write_search"] = probe_result

    try:
        result = semantic_search(
            "社会理论",
            filters={},
            limit=1,
            max_per_work=1,
            debug=True,
            strategy="vector",
        )
        steps["embedding"] = {
            "available": result["engine"] == "hybrid",
            "fallback_used": result["fallback_used"],
            "fallback_reason": result["fallback_reason"],
        }
    except Exception as exc:
        steps["embedding"] = {"available": False, "error": str(exc)[:1000]}

    return {
        "started_at": timezone.now(),
        "duration_seconds": round(time.monotonic() - started, 3),
        "steps": steps,
        "all_available": all(bool(step.get("available")) for step in steps.values()),
    }
