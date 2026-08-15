from __future__ import annotations

import json
import time
import uuid

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from catalog.models import SemanticIndexJob
from ingestion.models import UploadItem
from ingestion.services.health import (
    cache_health,
    celery_broker_health,
    http_service_health,
    safe_service_error,
    worker_runtime_status,
)
from ingestion.tasks import record_ingestion_worker_probe


def run_worker_task_probe(*, timeout_seconds: int = 20) -> dict:
    """Publish a fresh task and wait for the worker's cache acknowledgement."""

    probe_id = str(uuid.uuid4())
    cache_key = f"ingestion:pipeline-probe:{probe_id}"
    try:
        cache.delete(cache_key)
        record_ingestion_worker_probe.apply_async(
            args=[probe_id],
            ignore_result=True,
        )
    except Exception as exc:
        return {
            "executed": False,
            "probe_id": probe_id,
            "detail": safe_service_error(exc),
        }

    deadline = time.monotonic() + max(1, timeout_seconds)
    while time.monotonic() < deadline:
        try:
            marker = cache.get(cache_key)
        except Exception as exc:
            return {
                "executed": False,
                "probe_id": probe_id,
                "detail": safe_service_error(exc),
            }
        if isinstance(marker, dict) and marker.get("probe_id") == probe_id:
            cache.delete(cache_key)
            return {
                "executed": True,
                "probe_id": probe_id,
                "executed_at": marker.get("executed_at", ""),
                "detail": "新任务已由 Worker 执行",
            }
        time.sleep(0.25)

    return {
        "executed": False,
        "probe_id": probe_id,
        "detail": f"{max(1, timeout_seconds)} 秒内未收到 Worker 执行确认",
    }


def pipeline_status() -> dict:
    now = timezone.now()
    result = {
        "checked_at": now.isoformat(),
        "database": False,
        "cache": False,
        "broker": False,
        "worker": False,
    }
    try:
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        result["database"] = True
    except Exception as exc:
        result["database_error"] = str(exc)[:500]

    cache_status = cache_health(probe_key="ingestion:management-health-probe")
    broker_status = celery_broker_health()
    worker_status = worker_runtime_status(max_age_seconds=180)
    result["cache"] = cache_status["reachable"]
    result["cache_detail"] = cache_status["detail"]
    result["broker"] = broker_status["reachable"]
    result["broker_detail"] = broker_status["detail"]
    result["worker"] = worker_status["online"]
    result["worker_heartbeat_at"] = worker_status["heartbeat_at"]
    result["worker_detail"] = worker_status["detail"]
    result["ocr"] = http_service_health(settings.PADDLEOCR_SERVICE_URL, "/ready")
    result["search"] = http_service_health(settings.MEILISEARCH_URL, "/health")
    result["ingestion_pending"] = UploadItem.objects.filter(
        dispatch_status__in=[
            UploadItem.DispatchStatus.PENDING,
            UploadItem.DispatchStatus.FAILED,
        ]
    ).exclude(
        status__in=[
            UploadItem.Status.PUBLISHED,
            UploadItem.Status.WITHDRAWN,
            UploadItem.Status.DELETED,
            UploadItem.Status.NEEDS_REVIEW,
            UploadItem.Status.FAILED,
        ]
    ).count()
    result["semantic_pending"] = SemanticIndexJob.objects.filter(
        status__in=[
            SemanticIndexJob.Status.QUEUED,
            SemanticIndexJob.Status.RUNNING,
            SemanticIndexJob.Status.FAILED,
        ]
    ).count()
    required = [result["database"], result["cache"], result["broker"], result["worker"]]
    if settings.PADDLEOCR_SERVICE_URL:
        required.append(result["ocr"]["reachable"])
    if settings.USE_EXTERNAL_SEARCH or settings.SEMANTIC_SEARCH_ENABLED:
        required.append(result["search"]["reachable"])
    result["healthy"] = all(required)
    return result


class Command(BaseCommand):
    help = "检查数据库、Redis、Celery worker、OCR 和搜索服务是否共同可用。"

    def add_arguments(self, parser):
        parser.add_argument("--wait", type=int, default=0, help="等待服务恢复的秒数。")
        parser.add_argument("--json", action="store_true", help="输出 JSON。")
        parser.add_argument("--strict", action="store_true", help="任一必需服务异常时返回失败。")
        parser.add_argument(
            "--task-probe",
            action="store_true",
            help="投递一个新任务并确认 Worker 实际执行。严格模式会自动启用。",
        )
        parser.add_argument(
            "--task-probe-timeout",
            type=int,
            default=20,
            help="等待新任务执行确认的秒数。",
        )

    def handle(self, *args, **options):
        deadline = time.monotonic() + max(0, options["wait"])
        status = pipeline_status()
        while not status["healthy"] and time.monotonic() < deadline:
            time.sleep(min(3, max(0.2, deadline - time.monotonic())))
            status = pipeline_status()
        if status["healthy"] and (options["task_probe"] or options["strict"]):
            task_probe = run_worker_task_probe(
                timeout_seconds=max(1, options["task_probe_timeout"]),
            )
            status["task_probe"] = task_probe
            status["healthy"] = bool(status["healthy"] and task_probe["executed"])
        else:
            status["task_probe"] = {
                "executed": False,
                "detail": "基础服务尚未就绪" if not status["healthy"] else "未执行",
            }
        if options["json"]:
            self.stdout.write(json.dumps(status, ensure_ascii=False, indent=2, default=str))
        else:
            self.stdout.write(
                "数据库 {database}，缓存 {cache}，任务队列 {broker}，Worker {worker}，OCR {ocr}，搜索 {search}".format(
                    database="正常" if status["database"] else "异常",
                    cache="正常" if status["cache"] else "异常",
                    broker="正常" if status["broker"] else "异常",
                    worker="正常" if status["worker"] else "异常",
                    ocr="正常" if status["ocr"]["reachable"] else "异常",
                    search="正常" if status["search"]["reachable"] else "异常",
                )
            )
            self.stdout.write(
                "任务执行探针：{detail}。".format(
                    detail=status["task_probe"]["detail"],
                )
            )
            self.stdout.write(
                f"待派发入库 {status['ingestion_pending']}，待处理语义任务 {status['semantic_pending']}。"
            )
        if options["strict"] and not status["healthy"]:
            raise CommandError("书库后台处理服务尚未全部就绪。")
