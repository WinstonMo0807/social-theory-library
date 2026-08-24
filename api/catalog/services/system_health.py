from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from hashlib import sha256
import json
import logging
import time
from typing import Any, Callable
from uuid import uuid4

from billiard.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from catalog.models import (
    Asset,
    Edition,
    HealthCheckRun,
    HealthIncident,
    PublicationState,
    QueryLexiconEntry,
    QueryLexiconState,
    RecoveryAction,
    ResearchRun,
    SemanticChunk,
    SemanticIndexVersion,
)
from catalog.services.research.recovery import (
    RESEARCH_RUN_TERMINAL_STATUSES,
    CeleryOwnershipSnapshot,
    celery_research_ownership_snapshot,
    recover_stale_research_runs,
    stale_research_run_inventory,
)
from ingestion.models import AuditEvent, ProcessingJob
from ingestion.services.health import (
    celery_broker_health,
    celery_worker_control_status,
    http_service_health,
    worker_heartbeat_status,
)
from ingestion.services.ocr_provider import ocr_runtime_config


logger = logging.getLogger(__name__)
HEALTH_REGISTRY_VERSION = "functional-health-registry-v1"
HEALTH_SCHEDULE_LEASE_KEY = "social-theory-library:functional-health:scheduled-probes"
HEALTH_SCHEDULE_LEASE_SECONDS = 15 * 60
RECOVERY_CLAIM_STALE_SECONDS = 15 * 60


@dataclass(frozen=True)
class ProbeResult:
    configured: bool | None
    reachable: bool | None
    functional: bool | None
    productive: bool | None
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    error_category: str = ""


@dataclass(frozen=True)
class HealthProbe:
    key: str
    capability: str
    label: str
    interval_seconds: int
    runner: Callable[[], ProbeResult]
    affected_features: tuple[str, ...] = ()
    probable_causes: tuple[str, ...] = ()
    safe_recovery_actions: tuple[str, ...] = ("rerun_probe",)
    critical: bool = False


class HealthCheckRegistry:
    def __init__(self):
        self._probes: dict[str, HealthProbe] = {}

    def register(self, probe: HealthProbe) -> HealthProbe:
        if probe.key in self._probes:
            raise RuntimeError(f"重复的 health probe：{probe.key}")
        self._probes[probe.key] = probe
        return probe

    def get(self, key: str) -> HealthProbe:
        try:
            return self._probes[str(key or "").strip()]
        except KeyError as exc:
            raise ValueError("未知 health probe。") from exc

    def all(self) -> tuple[HealthProbe, ...]:
        return tuple(self._probes.values())


HEALTH_CHECKS = HealthCheckRegistry()


def _status(result: ProbeResult) -> str:
    if result.configured is False:
        return HealthCheckRun.Status.PAUSED
    if result.reachable is False or result.functional is False:
        return HealthCheckRun.Status.FAILED
    if result.productive is False:
        return HealthCheckRun.Status.DEGRADED
    if None in {result.configured, result.reachable, result.functional, result.productive}:
        return HealthCheckRun.Status.UNKNOWN
    return HealthCheckRun.Status.HEALTHY


def _json_safe_details(value: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def _database_probe() -> ProbeResult:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return ProbeResult(True, True, True, True, "数据库连接与查询正常。", {"vendor": connection.vendor})


def _cache_probe() -> ProbeResult:
    key = f"health-registry:{uuid4()}"
    cache.set(key, "ok", timeout=10)
    productive = cache.get(key) == "ok"
    cache.delete(key)
    return ProbeResult(True, productive, productive, productive, "缓存读写正常。" if productive else "缓存写入后无法读取。")


def _worker_probe() -> ProbeResult:
    eager = bool(settings.CELERY_TASK_ALWAYS_EAGER)
    broker = {"reachable": True, "detail": "eager"} if eager else celery_broker_health()
    control = {"online": True, "workers": ["eager"]} if eager else celery_worker_control_status(timeout_seconds=2)
    heartbeat = worker_heartbeat_status()
    reachable = bool(broker.get("reachable"))
    functional = bool(control.get("online")) or eager
    productive = functional and (eager or bool(heartbeat.get("online")))
    return ProbeResult(
        True,
        reachable,
        functional,
        productive,
        "Broker、Worker 与 Beat 活动正常。" if productive else "Worker 或 Beat 尚未通过活动检查。",
        {"broker": broker, "control": control, "heartbeat": heartbeat, "eager": eager},
        error_code="worker_activity_missing" if not productive else "",
    )


def _storage_reader_probe() -> ProbeResult:
    asset = (
        Asset.objects.filter(
            edition__state=PublicationState.PUBLISHED,
            kind__in=[Asset.Kind.ORIGINAL, Asset.Kind.NORMALIZED],
            status=Asset.Status.READY,
            is_current=True,
        )
        .select_related("edition__work")
        .order_by("-updated_at")
        .first()
    )
    if asset is None:
        return ProbeResult(True, True, True, None, "没有可执行 Reader 合成读取的已发布 PDF。", error_code="reader_fixture_missing")
    try:
        with asset.file.open("rb") as handle:
            header = handle.read(5)
    except Exception as exc:
        return ProbeResult(True, False, False, False, "Reader 无法读取当前 PDF。", {"asset_id": str(asset.id)}, "reader_storage_unavailable", exc.__class__.__name__)
    valid = header == b"%PDF-"
    return ProbeResult(
        True,
        True,
        valid,
        valid,
        "Reader 合成读取通过。" if valid else "Reader 读取到的文件头不是 PDF。",
        {"asset_id": str(asset.id), "work_id": str(asset.edition.work_id), "bytes_checked": 5},
        error_code="invalid_pdf_header" if not valid else "",
    )


def _ocr_probe() -> ProbeResult:
    config = ocr_runtime_config()
    configured = bool(config.get("nas_url"))
    if not configured:
        return ProbeResult(False, False, False, False, "PaddleOCR 服务未配置。", {"mode": config.get("mode")})
    live = http_service_health(config["nas_url"], "/ready", timeout=5)
    reachable = bool(live.get("reachable"))
    latest = ProcessingJob.objects.filter(job_type=ProcessingJob.JobType.OCR).order_by("-created_at").first()
    last_success = ProcessingJob.objects.filter(
        job_type=ProcessingJob.JobType.OCR,
        status=ProcessingJob.Status.SUCCEEDED,
    ).order_by("-finished_at").first()
    productive = bool(last_success)
    return ProbeResult(
        True,
        reachable,
        reachable,
        productive if latest else None,
        "OCR 服务可达并有成功任务。" if reachable and productive else "OCR 服务可达，尚无近期成功任务。" if reachable else "OCR 服务不可达。",
        {
            "live": live,
            "latest_job_id": str(latest.id) if latest else None,
            "latest_job_status": latest.status if latest else None,
            "last_success_at": last_success.finished_at if last_success else None,
        },
        error_code="ocr_unreachable" if not reachable else "ocr_not_productive" if latest and not productive else "",
    )


def _semantic_probe() -> ProbeResult:
    live = http_service_health(settings.MEILISEARCH_URL, "/health", timeout=4)
    reachable = bool(live.get("reachable"))
    active = SemanticIndexVersion.objects.filter(status=SemanticIndexVersion.Status.ACTIVE).order_by("-activated_at", "-created_at").first()
    ready_chunks = SemanticChunk.objects.filter(index_status=SemanticChunk.IndexStatus.READY).count()
    productive = bool(active and active.document_count and ready_chunks)
    return ProbeResult(
        bool(settings.MEILISEARCH_URL),
        reachable,
        reachable and active is not None,
        productive,
        "语义与关键词索引可用。" if reachable and productive else "索引服务可达，但活动索引尚未证明可产出结果。" if reachable else "Meilisearch 不可达。",
        {
            "live": live,
            "active_index_id": str(active.id) if active else None,
            "uid": active.uid if active else "",
            "document_count": active.document_count if active else 0,
            "expected_document_count": active.expected_document_count if active else 0,
            "ready_chunks": ready_chunks,
        },
        error_code="semantic_not_productive" if reachable and not productive else "meilisearch_unreachable" if not reachable else "",
    )


def _query_lexicon_probe() -> ProbeResult:
    state = QueryLexiconState.objects.select_related("active_generation").first()
    entries = (
        QueryLexiconEntry.objects.filter(
            generation=state.active_generation,
            admin_resolvable=True,
        ).count()
        if state is not None
        else 0
    )
    productive = bool(state and entries)
    return ProbeResult(
        True,
        True,
        state is not None,
        productive,
        "QueryLexicon 已初始化并有可用词条。" if productive else "QueryLexicon 尚未形成可用投影。",
        {"state_id": state.pk if state else None, "admin_resolvable_entries": entries},
        error_code="query_lexicon_empty" if not productive else "",
    )


def _processing_probe() -> ProbeResult:
    now = timezone.now()
    stalled_before = now - timedelta(minutes=30)
    pending = ProcessingJob.objects.filter(status=ProcessingJob.Status.PENDING).count()
    running = ProcessingJob.objects.filter(status=ProcessingJob.Status.RUNNING).count()
    failed = ProcessingJob.objects.filter(status=ProcessingJob.Status.FAILED).count()
    stalled = ProcessingJob.objects.filter(
        status__in=[ProcessingJob.Status.PENDING, ProcessingJob.Status.RUNNING],
        updated_at__lt=stalled_before,
    ).count()
    functional = stalled == 0
    return ProbeResult(
        True,
        True,
        functional,
        functional,
        "处理队列没有停滞任务。" if functional else f"发现 {stalled} 个疑似停滞任务。",
        {"pending": pending, "running": running, "failed_total": failed, "stalled": stalled},
        error_code="processing_jobs_stalled" if stalled else "",
    )


def _public_catalog_probe() -> ProbeResult:
    published = Edition.objects.filter(state=PublicationState.PUBLISHED).count()
    missing_slug = Edition.objects.filter(state=PublicationState.PUBLISHED).filter(
        Q(public_slug__isnull=True) | Q(public_slug="")
    ).count()
    stale_index = Edition.objects.filter(state=PublicationState.PUBLISHED, search_indexed_at__isnull=True).count()
    functional = missing_slug == 0
    productive = published > 0 and stale_index == 0
    return ProbeResult(
        True,
        True,
        functional,
        productive,
        "公开目录状态一致。" if functional and productive else "公开目录存在待修复的一致性或索引问题。",
        {"published_editions": published, "missing_public_slug": missing_slug, "search_index_missing": stale_index},
        error_code="public_catalog_inconsistent" if not functional else "public_catalog_not_fresh" if not productive else "",
    )


def _research_contract_probe() -> ProbeResult:
    from catalog.services.research.orchestrator import ResearchOrchestrator

    coverage = ResearchOrchestrator._validate_runtime_contracts()
    healthy = bool(coverage.get("healthy"))
    return ProbeResult(True, True, healthy, healthy, "Research Field Contract 覆盖完整。" if healthy else "Research Field Contract 有缺失。", coverage, "contract_missing" if not healthy else "")


def _research_planner_probe() -> ProbeResult:
    from catalog.services.research.context import build_research_context
    from catalog.services.research.planner import ResearchPlanner

    edition = Edition.objects.select_related("work").order_by("-updated_at").first()
    if edition is None:
        return ProbeResult(True, True, True, None, "没有可用于 Research Planner 探测的 Edition。", error_code="planner_fixture_missing")
    context = build_research_context(edition, active_step="work", draft_data={}, changed_fields=[])
    context, plan = ResearchPlanner().plan(context)
    productive = bool(plan)
    return ProbeResult(True, True, True, productive, "Research Planner 能生成有界任务。" if productive else "Research Planner 没有生成任务。", {"edition_id": str(edition.id), "task_count": len(plan), "fingerprint": context.fingerprint}, "query_plan_empty" if not productive else "")


def _searxng_probe() -> ProbeResult:
    from catalog.services.field_enrichment.web import WebSearchError, configured_web_search_adapter

    configured = bool(str(getattr(settings, "FIELD_ENRICHMENT_SEARXNG_URL", "") or "").strip())
    if not configured:
        return ProbeResult(False, False, False, False, "SearXNG 未配置。")
    try:
        results, record = configured_web_search_adapter().search("George Herbert Mead sociology", limit=2)
    except WebSearchError as exc:
        return ProbeResult(True, False, False, False, "SearXNG 实际查询失败。", {}, getattr(exc, "code", "searxng_failed"), exc.__class__.__name__)
    productive = bool(results)
    return ProbeResult(True, True, True, productive, "SearXNG 实际查询返回结果。" if productive else "SearXNG 可调用，但本次查询没有结果。", {"result_count": len(results), "source_record_id": str(getattr(record, "id", "") or "")}, "web_search_zero_results" if not productive else "")


def _safe_fetcher_probe() -> ProbeResult:
    from catalog.services.field_enrichment.web import SafeWebFetcher, configured_web_search_adapter

    configured = bool(str(getattr(settings, "FIELD_ENRICHMENT_SEARXNG_URL", "") or "").strip())
    if not configured:
        return ProbeResult(False, False, False, False, "SafeWebFetcher 缺少可用 discovery 来源。")
    results, _record = configured_web_search_adapter().search("George Herbert Mead sociology", limit=2)
    if not results:
        return ProbeResult(True, True, True, False, "Discovery 没有为 SafeWebFetcher 提供可抓取页面。", error_code="fetch_no_candidate")
    last_error = ""
    for result in results[:2]:
        try:
            document = SafeWebFetcher().fetch(result.url)
            productive = len(document.text.strip()) >= 80
            if productive:
                return ProbeResult(True, True, True, True, "SafeWebFetcher 已安全打开公开页面并取得正文。", {"domain": document.domain, "text_length": len(document.text), "source_record_id": str(document.source_record_id or "")})
        except Exception as exc:
            last_error = exc.__class__.__name__
    return ProbeResult(True, True, False, False, "SafeWebFetcher 未能从候选页面取得可用正文。", {"attempted": min(len(results), 2)}, "fetch_failed", last_error)


def _authority_probe(provider: str) -> ProbeResult:
    from catalog.services.authority_suggestions import _fetch_provider_with_policy, _provider_enabled

    if not _provider_enabled(provider):
        return ProbeResult(False, False, False, False, f"{provider} authority provider 未启用。")
    try:
        rows = _fetch_provider_with_policy(provider, "person", "George Herbert Mead")
    except Exception as exc:
        return ProbeResult(True, False, False, False, f"{provider} authority provider 实际查询失败。", {}, "authority_unavailable", exc.__class__.__name__)
    productive = bool(rows)
    return ProbeResult(True, True, True, productive, f"{provider} authority provider 返回候选。" if productive else f"{provider} 可调用，但本次没有候选。", {"result_count": len(rows)}, "authority_zero_results" if not productive else "")


def _metadata_provider_probe(provider: str) -> ProbeResult:
    from ingestion.services.metadata import (
        search_crossref_title,
        search_google_books_title,
        search_openlibrary_title,
    )
    from ingestion.services.provider_gateway import invoke_provider, provider_configuration_health

    config = next(row for row in provider_configuration_health() if row["provider"] == provider)
    if not config["enabled"] or not config["configured"] or not config["allowed_host"]:
        return ProbeResult(False, False, False, False, f"{provider} metadata provider 未完整配置。", config)
    resolvers = {
        "crossref": lambda: search_crossref_title("Mind Self and Society", limit=2),
        "openlibrary": lambda: search_openlibrary_title("Mind Self and Society", language="en", limit=2),
        "google_books": lambda: search_google_books_title("Mind Self and Society", language="en", limit=2),
    }
    values, warnings = invoke_provider(
        provider=provider,
        operation="health_search",
        query={"title": "Mind Self and Society"},
        resolver=resolvers[provider],
    )
    functional = not warnings
    productive = bool(values)
    return ProbeResult(True, functional, functional, productive, f"{provider} metadata provider 返回候选。" if productive else f"{provider} metadata provider 没有产出候选。", {"result_count": len(values), "warnings": warnings[:3]}, "metadata_provider_failed" if warnings else "metadata_provider_zero_results" if not productive else "")


def _research_productive_probe() -> ProbeResult:
    now = timezone.now()
    cutoff = now - timedelta(days=2)
    orphan_inventory = stale_research_run_inventory(now=now)
    orphan_count = orphan_inventory["orphan_nonterminal_count"]
    unverified_count = orphan_inventory["ownership_unverified_count"]
    latest = (
        ResearchRun.objects.filter(
            created_at__gte=cutoff,
            status__in=RESEARCH_RUN_TERMINAL_STATUSES,
            finished_at__isnull=False,
        )
        .order_by("-finished_at", "-created_at")
        .first()
    )
    if latest is None:
        if orphan_count or unverified_count:
            if orphan_count:
                summary = f"发现 {orphan_count} 条超过时限且没有 Celery ownership 的 ResearchRun。"
                error_code = "research_orphaned_runs"
            else:
                summary = f"有 {unverified_count} 条 stale ResearchRun 因 Celery inventory 不可用而无法确认 ownership。"
                error_code = "research_ownership_unverified"
            return ProbeResult(
                True,
                True,
                True,
                False,
                summary,
                {"run_id": None, **orphan_inventory},
                error_code=error_code,
            )
        return ProbeResult(
            True,
            True,
            True,
            None,
            "近两天没有 terminal ResearchRun，可在工作流中运行一次真实研究。",
            {"run_id": None, **orphan_inventory},
            error_code="research_run_missing",
        )
    diagnostics = latest.diagnostics or {}
    counts = diagnostics.get("candidate_counts") or {}
    candidate_total = 0
    for value in counts.values():
        try:
            candidate_total += int(value or 0)
        except (TypeError, ValueError):
            continue
    productive = (
        latest.status in {ResearchRun.Status.COMPLETED, ResearchRun.Status.DEGRADED}
        and candidate_total > 0
        and orphan_count == 0
        and unverified_count == 0
    )
    functional = latest.status != ResearchRun.Status.FAILED
    if productive:
        summary = "Research Pipeline 已把研究输入转换成可审核候选。"
    elif orphan_count:
        summary = f"最近 terminal ResearchRun 已读取，但另有 {orphan_count} 条孤儿任务需要安全收口。"
    elif unverified_count:
        summary = f"最近 terminal ResearchRun 已读取，但有 {unverified_count} 条 stale 任务的 ownership 无法确认。"
    else:
        summary = "最近 terminal ResearchRun 未能证明候选产出。"
    error_code = (
        "research_orphaned_runs"
        if orphan_count
        else "research_ownership_unverified"
        if unverified_count
        else latest.error_code or ("research_not_productive" if not productive else "")
    )
    return ProbeResult(
        True,
        True,
        functional,
        productive,
        summary,
        {
            "run_id": str(latest.id),
            "status": latest.status,
            "finished_at": latest.finished_at,
            "candidate_counts": counts,
            "searxng_called": diagnostics.get("searxng_called"),
            **orphan_inventory,
        },
        error_code,
    )


def _register_probes() -> None:
    values = [
        HealthProbe("database", "catalog_core", "数据库", 60, _database_probe, ("公开目录", "后台编辑", "研究候选"), ("PostgreSQL 不可达", "连接池耗尽"), critical=True),
        HealthProbe("cache", "catalog_core", "Redis / Cache", 60, _cache_probe, ("会话", "缓存", "任务协调"), ("Redis 不可达",), critical=True),
        HealthProbe("worker", "background_processing", "Broker / Worker / Beat", 60, _worker_probe, ("入库", "OCR", "Research", "索引"), ("Broker 不可达", "Worker 未消费", "Beat 未调度"), ("rerun_probe", "recover_ingestion_queue"), True),
        HealthProbe("storage_reader", "public_reading", "PDF 存储与 Reader", 300, _storage_reader_probe, ("在线阅读", "下载", "复制"), ("NAS 挂载不可用", "PDF 缺失或损坏"), critical=True),
        HealthProbe("ocr", "ingestion", "PaddleOCR", 300, _ocr_probe, ("OCR", "全文复制", "入库"), ("OCR 容器不可达", "模型未加载"), ("rerun_probe", "recover_ingestion_queue")),
        HealthProbe("semantic", "search", "Meilisearch 与语义索引", 300, _semantic_probe, ("站内检索", "语义检索"), ("Meilisearch 不可达", "活动索引缺失"), ("rerun_probe", "recover_semantic_queue"), True),
        HealthProbe("query_lexicon", "search", "QueryLexicon", 300, _query_lexicon_probe, ("双语检索", "实体匹配"), ("投影未初始化", "重建任务失败"), ("rerun_probe", "recover_query_lexicon")),
        HealthProbe("processing", "background_processing", "处理任务", 60, _processing_probe, ("入库", "OCR", "索引", "研究"), ("任务 ownership 失效", "Worker 中断"), ("rerun_probe", "recover_ingestion_queue")),
        HealthProbe("public_catalog", "public_catalog", "公开目录新鲜度", 300, _public_catalog_probe, ("首页", "检索", "作品页"), ("发布投影未刷新", "搜索索引时间缺失"), critical=True),
        HealthProbe("research_contracts", "research", "Research Contract", 300, _research_contract_probe, ("全工作流自动研究",), ("字段声明缺失", "实现未注册")),
        HealthProbe("research_planner", "research", "Research Planner", 300, _research_planner_probe, ("自动研究", "增量重规划"), ("上下文构建失败", "规划为空")),
        HealthProbe("searxng", "external_research", "SearXNG", 900, _searxng_probe, ("一般 Web discovery", "Entity Picker"), ("SearXNG 不可达", "engine 无结果")),
        HealthProbe("safe_web_fetcher", "external_research", "SafeWebFetcher", 1800, _safe_fetcher_probe, ("网页证据",), ("来源页面阻止抓取", "SSRF 安全规则拒绝")),
        HealthProbe("research_productive", "research", "Research Pipeline 产出", 300, _research_productive_probe, ("候选生成", "Processing Center 研究健康"), ("最近研究失败", "Provider 无候选", "孤儿 ResearchRun"), ("rerun_probe", "recover_stale_research", "retry_failed_research")),
    ]
    for provider in ("wikidata", "viaf", "loc", "openalex"):
        values.append(HealthProbe(f"authority.{provider}", "external_research", f"{provider} authority", 1800, lambda value=provider: _authority_probe(value), ("实体身份候选",), ("Provider 不可达", "限流或查询失败")))
    for provider in ("crossref", "openlibrary", "google_books"):
        values.append(HealthProbe(f"metadata.{provider}", "external_research", f"{provider} metadata", 1800, lambda value=provider: _metadata_provider_probe(value), ("书目候选",), ("Provider 不可达", "限流或查询失败")))
    for value in values:
        HEALTH_CHECKS.register(value)


_register_probes()


def _safe_recovery_actions_for_result(
    probe: HealthProbe,
    result: ProbeResult,
) -> list[str]:
    """Expose only recovery actions that the current probe result can execute."""

    actions = list(probe.safe_recovery_actions)
    if probe.key != "research_productive":
        return actions

    details = dict(result.details or {})
    if not details.get("orphan_nonterminal_count"):
        actions = [value for value in actions if value != "recover_stale_research"]
    if str(details.get("status") or "") != ResearchRun.Status.FAILED:
        actions = [value for value in actions if value != "retry_failed_research"]
    return actions


def _active_recovery_for_incident(
    incident: HealthIncident,
    *,
    action: str = "",
) -> RecoveryAction | None:
    queryset = RecoveryAction.objects.filter(incident=incident).filter(
        Q(status__in=[RecoveryAction.Status.QUEUED, RecoveryAction.Status.RUNNING])
        | Q(
            status=RecoveryAction.Status.FAILED,
            next_retry_at__isnull=False,
        )
    )
    if action:
        queryset = queryset.filter(action=action)
    return queryset.order_by("-created_at").first()


def run_health_probe(probe_key: str, *, source: str = HealthCheckRun.Source.SCHEDULED, actor=None) -> HealthCheckRun:
    probe = HEALTH_CHECKS.get(probe_key)
    started_at = timezone.now()
    started = time.perf_counter()
    try:
        result = probe.runner()
    except SoftTimeLimitExceeded:
        raise
    except Exception as exc:
        logger.exception("health probe failed", extra={"probe_key": probe.key})
        result = ProbeResult(True, False, False, False, "健康探测执行失败。", {}, "probe_failed", exc.__class__.__name__)
    completed_at = timezone.now()
    status_value = _status(result)
    details = _json_safe_details(result.details)
    safe_recovery_actions = _safe_recovery_actions_for_result(probe, result)
    run = HealthCheckRun.objects.create(
        probe_key=probe.key,
        capability=probe.capability,
        status=status_value,
        source=source,
        configured=result.configured,
        reachable=result.reachable,
        functional=result.functional,
        productive=result.productive,
        summary=result.summary[:500],
        details=details,
        error_code=result.error_code,
        error_category=result.error_category,
        started_at=started_at,
        completed_at=completed_at,
        latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
        initiated_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    now = timezone.now()
    if status_value in {HealthCheckRun.Status.FAILED, HealthCheckRun.Status.DEGRADED}:
        incident_key = f"{probe.key}:{result.error_code or status_value}"[:160]
        with transaction.atomic():
            incident, created = (
                HealthIncident.objects.select_for_update(of=("self",)).get_or_create(
                    incident_key=incident_key,
                    defaults={
                        "capability": probe.capability,
                        "probe_key": probe.key,
                        "status": HealthIncident.Status.OPEN,
                        "severity": HealthIncident.Severity.CRITICAL if probe.critical else HealthIncident.Severity.WARNING,
                        "error_code": result.error_code or status_value,
                        "error_category": result.error_category,
                        "error_message": result.summary,
                        "first_seen_at": now,
                        "last_seen_at": now,
                        "affected_features": list(probe.affected_features),
                        "probable_causes": list(probe.probable_causes),
                        "safe_recovery_actions": safe_recovery_actions,
                        "manual_guidance": "先查看依赖详情与最近一次成功时间。自动恢复次数用尽后再人工检查服务日志。",
                        "details": details,
                        "latest_run": run,
                    },
                )
            )
            if not created:
                active_recovery = _active_recovery_for_incident(incident)
                incident.status = (
                    HealthIncident.Status.RECOVERING
                    if active_recovery is not None
                    else HealthIncident.Status.OPEN
                )
                incident.last_seen_at = now
                incident.occurrence_count += 1
                incident.error_category = result.error_category
                incident.error_message = result.summary
                incident.details = details
                incident.latest_run = run
                incident.safe_recovery_actions = safe_recovery_actions
                incident.resolved_at = None
                incident.resolved_by = None
                incident.save(update_fields=["status", "last_seen_at", "occurrence_count", "error_category", "error_message", "details", "latest_run", "safe_recovery_actions", "resolved_at", "resolved_by", "updated_at"])
    elif status_value == HealthCheckRun.Status.HEALTHY:
        HealthIncident.objects.filter(
            probe_key=probe.key,
            status__in=[HealthIncident.Status.OPEN, HealthIncident.Status.RECOVERING],
        ).update(
            status=HealthIncident.Status.RESOLVED,
            resolved_at=now,
            last_success_at=now,
            latest_run=run,
            updated_at=now,
        )
    return run


def run_due_health_probes(*, limit: int = 12) -> dict[str, Any]:
    batch_limit = max(1, min(int(limit), 24))
    lease_token = uuid4().hex
    try:
        acquired = cache.add(
            HEALTH_SCHEDULE_LEASE_KEY,
            lease_token,
            timeout=HEALTH_SCHEDULE_LEASE_SECONDS,
        )
    except Exception as exc:
        logger.exception("scheduled health probe lease unavailable")
        return {
            "due": 0,
            "executed": 0,
            "runs": [],
            "skipped": "lease_unavailable",
            "error_category": exc.__class__.__name__,
        }
    if not acquired:
        return {
            "due": 0,
            "executed": 0,
            "runs": [],
            "skipped": "lease_held",
        }
    try:
        now = timezone.now()
        recover_stale_recovery_actions(now=now)
        due = []
        for probe in HEALTH_CHECKS.all():
            latest = HealthCheckRun.objects.filter(probe_key=probe.key).order_by("-started_at").first()
            if latest is None or latest.started_at <= now - timedelta(seconds=probe.interval_seconds):
                due.append(probe)
        due.sort(key=lambda row: (row.interval_seconds, row.key))
        runs = [run_health_probe(row.key) for row in due[:batch_limit]]
        return {
            "due": len(due),
            "executed": len(runs),
            "runs": [
                {"id": str(row.id), "probe_key": row.probe_key, "status": row.status}
                for row in runs
            ],
        }
    finally:
        try:
            if cache.get(HEALTH_SCHEDULE_LEASE_KEY) == lease_token:
                cache.delete(HEALTH_SCHEDULE_LEASE_KEY)
        except Exception:
            logger.exception("scheduled health probe lease release failed")


def _latest_runs() -> dict[str, HealthCheckRun]:
    output: dict[str, HealthCheckRun] = {}
    for row in HealthCheckRun.objects.order_by("probe_key", "-started_at"):
        output.setdefault(row.probe_key, row)
    return output


STATUS_RANK = {
    HealthCheckRun.Status.FAILED: 6,
    HealthCheckRun.Status.RECOVERING: 5,
    HealthCheckRun.Status.DEGRADED: 4,
    HealthCheckRun.Status.UNKNOWN: 3,
    HealthCheckRun.Status.PAUSED: 2,
    HealthCheckRun.Status.HEALTHY: 1,
}


CAPABILITY_LABELS = {
    "catalog_core": "书库核心服务",
    "public_reading": "公开阅读",
    "public_catalog": "公开目录",
    "search": "站内检索",
    "ingestion": "入库与 OCR",
    "background_processing": "后台任务",
    "research": "Research Orchestrator",
    "external_research": "外部研究来源",
}


def functional_health_snapshot() -> dict[str, Any]:
    from catalog.services.processing_center_diagnostics import processing_center_diagnostics

    latest = _latest_runs()
    open_incidents = list(HealthIncident.objects.filter(status__in=[HealthIncident.Status.OPEN, HealthIncident.Status.RECOVERING]).order_by("-severity", "-last_seen_at")[:100])
    incidents_by_capability: dict[str, list[HealthIncident]] = defaultdict(list)
    for row in open_incidents:
        incidents_by_capability[row.capability].append(row)
    grouped: dict[str, list[tuple[HealthProbe, HealthCheckRun | None]]] = defaultdict(list)
    for probe in HEALTH_CHECKS.all():
        grouped[probe.capability].append((probe, latest.get(probe.key)))
    capabilities = []
    for key, dependencies in grouped.items():
        statuses = [row.status for _probe, row in dependencies if row is not None]
        status_value = max(statuses, key=lambda value: STATUS_RANK.get(value, 0)) if statuses else HealthCheckRun.Status.UNKNOWN
        dimensions: dict[str, bool | None] = {}
        for field_name in ("configured", "reachable", "functional", "productive"):
            values = [getattr(row, field_name) for _probe, row in dependencies if row is not None and getattr(row, field_name) is not None]
            dimensions[field_name] = all(values) if values else None
        capabilities.append({
            "key": key,
            "label": CAPABILITY_LABELS.get(key, key),
            "status": status_value,
            **dimensions,
            "last_checked_at": max((row.started_at for _probe, row in dependencies if row is not None), default=None),
            "dependencies": [
                {
                    "probe_key": probe.key,
                    "label": probe.label,
                    "status": row.status if row else HealthCheckRun.Status.UNKNOWN,
                    "configured": row.configured if row else None,
                    "reachable": row.reachable if row else None,
                    "functional": row.functional if row else None,
                    "productive": row.productive if row else None,
                    "summary": row.summary if row else "尚未运行后台探测。",
                    "last_checked_at": row.started_at if row else None,
                    "latency_ms": row.latency_ms if row else None,
                    "error_code": row.error_code if row else "not_probed",
                    "details": row.details if row else {},
                }
                for probe, row in dependencies
            ],
            "incident_count": len(incidents_by_capability.get(key, [])),
        })
    capabilities.sort(key=lambda row: (-STATUS_RANK.get(row["status"], 0), row["label"]))
    recoveries = RecoveryAction.objects.select_related("incident").order_by("-created_at")[:50]
    return {
        "version": HEALTH_REGISTRY_VERSION,
        "generated_at": timezone.now(),
        "overall_status": max((row["status"] for row in capabilities), key=lambda value: STATUS_RANK.get(value, 0), default=HealthCheckRun.Status.UNKNOWN),
        "capabilities": capabilities,
        "incidents": [
            {
                "id": str(row.id),
                "incident_key": row.incident_key,
                "capability": row.capability,
                "probe_key": row.probe_key,
                "status": row.status,
                "severity": row.severity,
                "error_code": row.error_code,
                "error_category": row.error_category,
                "error_message": row.error_message,
                "first_seen_at": row.first_seen_at,
                "last_seen_at": row.last_seen_at,
                "last_success_at": row.last_success_at,
                "occurrence_count": row.occurrence_count,
                "recovery_attempt_count": row.recovery_attempt_count,
                "affected_features": row.affected_features,
                "probable_causes": row.probable_causes,
                "safe_recovery_actions": row.safe_recovery_actions,
                "manual_guidance": row.manual_guidance,
                "details": row.details,
            }
            for row in open_incidents
        ],
        "recoveries": [
            {
                "id": str(row.id),
                "incident_id": str(row.incident_id),
                "action": row.action,
                "status": row.status,
                "attempt": row.attempt,
                "max_attempts": row.max_attempts,
                "next_retry_at": row.next_retry_at,
                "details": row.details,
                "error_code": row.error_code,
                "created_at": row.created_at,
                "finished_at": row.finished_at,
            }
            for row in recoveries
        ],
        "probe_count": len(HEALTH_CHECKS.all()),
        "page_load_performs_live_probes": False,
        "diagnostics": processing_center_diagnostics(),
    }


SAFE_RECOVERY_ACTIONS = {
    "rerun_probe",
    "recover_ingestion_queue",
    "recover_semantic_queue",
    "recover_query_lexicon",
    "recover_stale_research",
    "retry_failed_research",
}


def _dispatch_health_recovery(
    recovery_id: str,
    task_id: str,
    *,
    countdown: int | None = None,
) -> bool:
    """Dispatch one pre-owned recovery and retain a recoverable DB state."""

    from catalog.tasks import execute_health_recovery

    kwargs: dict[str, Any] = {
        "args": [str(recovery_id)],
        "task_id": str(task_id),
    }
    if countdown is not None:
        kwargs["countdown"] = int(countdown)
    try:
        execute_health_recovery.apply_async(**kwargs)
        return True
    except Exception as exc:
        logger.exception(
            "health recovery dispatch failed",
            extra={"recovery_action_id": str(recovery_id)},
        )
        now = timezone.now()
        with transaction.atomic():
            recovery = (
                RecoveryAction.objects.select_for_update(of=("self",))
                .filter(pk=recovery_id)
                .first()
            )
            if recovery is None:
                return False
            details = dict(recovery.details or {})
            if str(details.get("dispatch_task_id") or "") != str(task_id):
                return False
            details.update(
                {
                    "dispatch_task_id": "",
                    "claimed_at": None,
                    "dispatch_error": exc.__class__.__name__,
                }
            )
            recovery.status = RecoveryAction.Status.FAILED
            recovery.details = details
            recovery.error_code = "recovery_dispatch_failed"
            recovery.error_message = "恢复任务未能提交到 Celery。"
            recovery.next_retry_at = now
            recovery.finished_at = now
            recovery.save(
                update_fields=[
                    "status",
                    "details",
                    "error_code",
                    "error_message",
                    "next_retry_at",
                    "finished_at",
                    "updated_at",
                ]
            )
        return False


def recover_stale_recovery_actions(
    *,
    now=None,
    stale_after_seconds: int = RECOVERY_CLAIM_STALE_SECONDS,
    limit: int = 50,
    ownership_snapshot: CeleryOwnershipSnapshot | None = None,
) -> dict[str, Any]:
    """Re-dispatch lost RecoveryAction workers without duplicating broker work."""

    now = now or timezone.now()
    stale_seconds = max(60, min(int(stale_after_seconds), 24 * 60 * 60))
    cutoff = now - timedelta(seconds=stale_seconds)
    bounded_limit = max(1, min(int(limit), 200))
    running_query = RecoveryAction.objects.filter(
        status=RecoveryAction.Status.RUNNING,
        updated_at__lt=cutoff,
    )
    queued_query = RecoveryAction.objects.filter(
        status=RecoveryAction.Status.QUEUED,
        updated_at__lt=cutoff,
    )
    failed_dispatch_query = RecoveryAction.objects.filter(
        status=RecoveryAction.Status.FAILED,
        next_retry_at__lte=now,
    )
    candidates = list(
        (queued_query | running_query | failed_dispatch_query)
        .order_by("updated_at", "created_at")
        .only("id", "status", "attempt", "max_attempts", "details", "updated_at")[:bounded_limit]
    )
    snapshot = ownership_snapshot
    if snapshot is None and any(
        row.status == RecoveryAction.Status.RUNNING
        and str((row.details or {}).get("dispatch_task_id") or "").strip()
        for row in candidates
    ):
        snapshot = celery_research_ownership_snapshot()
    snapshot = snapshot or CeleryOwnershipSnapshot(
        available=True,
        task_ids=frozenset(),
        detail="没有带 owner token 的 stale RecoveryAction。",
    )
    requeued: list[tuple[str, str]] = []
    terminal: list[str] = []
    skipped_owned = 0
    skipped_unverified = 0
    with transaction.atomic():
        locked = list(
            RecoveryAction.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(pk__in=[row.pk for row in candidates])
            .select_related("incident")
        )
        for recovery in locked:
            details = dict(recovery.details or {})
            previous_task_id = str(details.get("dispatch_task_id") or "").strip()
            if recovery.status == RecoveryAction.Status.QUEUED:
                if recovery.updated_at >= cutoff:
                    continue
            elif recovery.status == RecoveryAction.Status.RUNNING:
                claimed_at = _claimed_at(details)
                if recovery.updated_at >= cutoff or (
                    claimed_at is not None and claimed_at >= cutoff
                ):
                    continue
                if previous_task_id:
                    if not snapshot.available:
                        skipped_unverified += 1
                        continue
                    if previous_task_id in snapshot.task_ids:
                        skipped_owned += 1
                        continue
            elif not (
                recovery.status == RecoveryAction.Status.FAILED
                and recovery.next_retry_at
                and recovery.next_retry_at <= now
            ):
                continue

            if recovery.attempt >= recovery.max_attempts:
                recovery.status = RecoveryAction.Status.FAILED
                recovery.error_code = "recovery_worker_lost"
                recovery.error_message = "Recovery Worker 丢失且已达到最大尝试次数。"
                recovery.next_retry_at = None
                recovery.finished_at = now
                recovery.save(
                    update_fields=[
                        "status",
                        "error_code",
                        "error_message",
                        "next_retry_at",
                        "finished_at",
                        "updated_at",
                    ]
                )
                HealthIncident.objects.filter(
                    pk=recovery.incident_id,
                    status=HealthIncident.Status.RECOVERING,
                ).update(status=HealthIncident.Status.OPEN, updated_at=now)
                terminal.append(str(recovery.id))
                continue

            # A queued action is safe to republish with the same durable task
            # id. Two deliveries cannot both execute because execute_recovery
            # claims that id and status under a row lock. Lost running workers
            # receive a new owner so the old worker cannot write terminal state.
            next_task_id = (
                previous_task_id
                if recovery.status in {
                    RecoveryAction.Status.QUEUED,
                    RecoveryAction.Status.FAILED,
                }
                and previous_task_id
                else str(uuid4())
            )
            lifecycle = list(details.get("dispatch_lifecycle") or [])
            lifecycle.append(
                {
                    "code": "recovery_dispatch_stale"
                    if recovery.status == RecoveryAction.Status.QUEUED
                    else "recovery_worker_lost"
                    if recovery.status == RecoveryAction.Status.RUNNING
                    else "recovery_dispatch_retry",
                    "occurred_at": now.isoformat(),
                    "previous_task_id": previous_task_id,
                }
            )
            details.update(
                {
                    "dispatch_task_id": next_task_id,
                    "claimed_at": None,
                    "dispatch_lifecycle": lifecycle[-10:],
                }
            )
            recovery.status = RecoveryAction.Status.QUEUED
            recovery.details = details
            recovery.error_code = "recovery_worker_lost"
            recovery.error_message = "Recovery Worker 未完成，已安排安全重试。"
            recovery.next_retry_at = now
            recovery.finished_at = None
            recovery.save(
                update_fields=[
                    "status",
                    "details",
                    "error_code",
                    "error_message",
                    "next_retry_at",
                    "finished_at",
                    "updated_at",
                ]
            )
            requeued.append((str(recovery.id), next_task_id))
        for recovery_id, task_id in requeued:
            transaction.on_commit(
                lambda recovery_id=recovery_id, task_id=task_id: _dispatch_health_recovery(
                    recovery_id,
                    task_id,
                )
            )
    return {
        "candidates": len(candidates),
        "requeued": len(requeued),
        "requeued_ids": [row[0] for row in requeued],
        "terminal": len(terminal),
        "terminal_ids": terminal,
        "skipped_celery_owned": skipped_owned,
        "skipped_ownership_unverified": skipped_unverified,
        "ownership_inventory_available": snapshot.available,
        "stale_after_seconds": stale_seconds,
    }


def request_recovery(incident: HealthIncident, *, action: str, actor=None, request_key: str = "") -> tuple[RecoveryAction, bool]:
    action = str(action or "").strip().casefold()
    if action not in SAFE_RECOVERY_ACTIONS:
        raise ValueError("该 incident 不允许此恢复动作。")
    with transaction.atomic():
        incident = HealthIncident.objects.select_for_update().get(pk=incident.pk)
        if action not in SAFE_RECOVERY_ACTIONS or action not in set(incident.safe_recovery_actions or []):
            raise ValueError("该 incident 不允许此恢复动作。")
        if incident.status == HealthIncident.Status.RESOLVED:
            raise ValueError("incident 已恢复，无需重复操作。")
        active_recovery = _active_recovery_for_incident(
            incident,
            action=action,
        )
        if active_recovery is not None:
            if incident.status != HealthIncident.Status.RECOVERING:
                incident.status = HealthIncident.Status.RECOVERING
                incident.save(update_fields=["status", "updated_at"])
            return active_recovery, False
        stable_request = request_key or f"occurrence:{incident.occurrence_count}"
        key = sha256(f"{incident.id}:{action}:{stable_request}".encode()).hexdigest()
        task_id = str(uuid4())
        recovery, created = RecoveryAction.objects.get_or_create(
            idempotency_key=key,
            defaults={
                "incident": incident,
                "action": action,
                "requested_by": actor if getattr(actor, "is_authenticated", False) else None,
                "max_attempts": 3,
                "details": {
                    "dispatch_task_id": task_id,
                    "claimed_at": None,
                },
            },
        )
        if created:
            incident.status = HealthIncident.Status.RECOVERING
            incident.recovery_attempt_count += 1
            incident.save(update_fields=["status", "recovery_attempt_count", "updated_at"])
            AuditEvent.objects.create(
                actor=actor if getattr(actor, "is_authenticated", False) else None,
                action="health_recovery_requested",
                object_type="catalog.HealthIncident",
                object_id=str(incident.id),
                after={"recovery_action_id": str(recovery.id), "action": action, "idempotency_key": key},
                request_id=stable_request[:120],
            )
            transaction.on_commit(
                lambda: _dispatch_health_recovery(
                    str(recovery.id),
                    task_id,
                )
            )
    return recovery, created


def _claimed_at(details: dict[str, Any]) -> Any:
    value = details.get("claimed_at")
    if not value:
        return None
    if hasattr(value, "tzinfo"):
        return value
    parsed = parse_datetime(str(value))
    if parsed is not None and timezone.is_naive(parsed):
        return timezone.make_aware(parsed)
    return parsed


def execute_recovery(recovery_id: str, *, task_id: str = "") -> RecoveryAction:
    with transaction.atomic():
        recovery = RecoveryAction.objects.select_for_update().select_related("incident").get(pk=recovery_id)
        if recovery.status == RecoveryAction.Status.SUCCEEDED:
            return recovery
        now = timezone.now()
        ownership = dict(recovery.details or {})
        expected_task_id = str(ownership.get("dispatch_task_id") or "").strip()
        current_task_id = str(task_id or expected_task_id or "").strip()
        if expected_task_id and current_task_id and current_task_id != expected_task_id:
            return recovery
        if recovery.status == RecoveryAction.Status.RUNNING:
            claimed_at = _claimed_at(ownership)
            if claimed_at is None or claimed_at > now - timedelta(seconds=RECOVERY_CLAIM_STALE_SECONDS):
                return recovery
        if recovery.next_retry_at and recovery.next_retry_at > now:
            return recovery
        if recovery.attempt >= recovery.max_attempts:
            if recovery.status != RecoveryAction.Status.FAILED:
                recovery.status = RecoveryAction.Status.FAILED
                recovery.error_code = "attempt_limit_reached"
                recovery.error_message = "恢复动作已达到最大尝试次数。"
                recovery.finished_at = now
                recovery.next_retry_at = None
                recovery.save(update_fields=["status", "error_code", "error_message", "finished_at", "next_retry_at", "updated_at"])
            HealthIncident.objects.filter(
                pk=recovery.incident_id,
                status=HealthIncident.Status.RECOVERING,
            ).update(status=HealthIncident.Status.OPEN, updated_at=now)
            return recovery
        recovery.status = RecoveryAction.Status.RUNNING
        recovery.attempt += 1
        recovery.started_at = recovery.started_at or now
        recovery.finished_at = None
        recovery.next_retry_at = None
        ownership["dispatch_task_id"] = current_task_id or expected_task_id
        ownership["claimed_at"] = now.isoformat()
        recovery.details = ownership
        recovery.save(update_fields=["status", "attempt", "started_at", "finished_at", "next_retry_at", "details", "updated_at"])
    try:
        if recovery.action == "rerun_probe":
            details = {"run_id": str(run_health_probe(recovery.incident.probe_key, source=HealthCheckRun.Source.RECOVERY).id)}
        elif recovery.action == "recover_ingestion_queue":
            from ingestion.tasks import recover_ingestion_queue

            details = recover_ingestion_queue.run()
        elif recovery.action == "recover_semantic_queue":
            from catalog.services.semantic_indexing import recover_semantic_index_jobs

            details = recover_semantic_index_jobs()
        elif recovery.action == "recover_query_lexicon":
            from catalog.tasks import recover_query_lexicon_events

            details = recover_query_lexicon_events.run()
        elif recovery.action == "recover_stale_research":
            details = recover_stale_research_runs(
                actor=recovery.requested_by,
                request_id=str(recovery.id),
            )
            if details.get("skipped_ownership_unverified"):
                raise RuntimeError("Celery ownership inventory 不可用，未处理带 task_id 的 ResearchRun。")
        elif recovery.action == "retry_failed_research":
            incident_run_id = str((recovery.incident.details or {}).get("run_id") or "").strip()
            if not incident_run_id:
                raise ValueError("当前 incident 没有绑定可重试的 ResearchRun。")
            failed = ResearchRun.objects.filter(
                pk=incident_run_id,
                status=ResearchRun.Status.FAILED,
            ).first()
            if failed is None:
                raise ValueError("incident 绑定的 ResearchRun 不存在或已不再是 failed。")
            from catalog.services.research.orchestrator import ResearchOrchestrator

            retried, created = ResearchOrchestrator().retry_failed(
                failed,
                retry_key=f"{recovery.id}:{recovery.attempt}",
                actor=recovery.requested_by,
                dispatch=True,
            )
            if retried.status == ResearchRun.Status.FAILED:
                raise RuntimeError("Research retry 未能提交到独立任务。")
            details = {
                "research_run_id": str(failed.id),
                "retry_run_id": str(retried.id),
                "retry_created": created,
                "status": retried.status,
                "execution": "celery_research_task",
            }
        else:
            raise ValueError("未注册的恢复动作。")
        now = timezone.now()
        completed = RecoveryAction.objects.filter(
            pk=recovery.pk,
            status=RecoveryAction.Status.RUNNING,
            attempt=recovery.attempt,
            details__dispatch_task_id=current_task_id or expected_task_id,
        ).update(
            status=RecoveryAction.Status.SUCCEEDED,
            details=details or {},
            error_code="",
            error_message="",
            next_retry_at=None,
            finished_at=now,
            updated_at=now,
        )
        if not completed:
            return RecoveryAction.objects.get(pk=recovery.pk)
        AuditEvent.objects.create(
            actor=recovery.requested_by,
            action="health_recovery_completed",
            object_type="catalog.HealthIncident",
            object_id=str(recovery.incident_id),
            after={
                "recovery_action_id": str(recovery.id),
                "action": recovery.action,
                "status": "succeeded",
                "attempt": recovery.attempt,
                "max_attempts": recovery.max_attempts,
            },
        )
    except Exception as exc:
        logger.exception("health recovery failed", extra={"recovery_action_id": str(recovery.id)})
        delay = min(3600, 30 * (2 ** max(0, recovery.attempt - 1)))
        now = timezone.now()
        next_retry_at = now + timedelta(seconds=delay) if recovery.attempt < recovery.max_attempts else None
        retry_task_id = str(uuid4()) if next_retry_at else ""
        failure_details = dict(recovery.details or {})
        failure_details.update({
            "dispatch_task_id": retry_task_id,
            "claimed_at": None,
        })
        failed_update = RecoveryAction.objects.filter(
            pk=recovery.pk,
            status=RecoveryAction.Status.RUNNING,
            attempt=recovery.attempt,
            details__dispatch_task_id=current_task_id or expected_task_id,
        ).update(
            status=RecoveryAction.Status.FAILED,
            details=failure_details,
            error_code="recovery_failed",
            error_message=exc.__class__.__name__,
            next_retry_at=next_retry_at,
            finished_at=now,
            updated_at=now,
        )
        if not failed_update:
            return RecoveryAction.objects.get(pk=recovery.pk)
        if recovery.attempt >= recovery.max_attempts:
            HealthIncident.objects.filter(
                pk=recovery.incident_id,
                status=HealthIncident.Status.RECOVERING,
            ).update(status=HealthIncident.Status.OPEN, updated_at=now)
        AuditEvent.objects.create(
            actor=recovery.requested_by,
            action="health_recovery_failed",
            object_type="catalog.HealthIncident",
            object_id=str(recovery.incident_id),
            after={
                "recovery_action_id": str(recovery.id),
                "action": recovery.action,
                "status": "failed",
                "error_category": exc.__class__.__name__,
                "attempt": recovery.attempt,
                "max_attempts": recovery.max_attempts,
                "next_retry_at": next_retry_at.isoformat() if next_retry_at else None,
            },
        )
        if recovery.attempt < recovery.max_attempts:
            transaction.on_commit(
                lambda: _dispatch_health_recovery(
                    str(recovery.id),
                    retry_task_id,
                    countdown=delay,
                )
            )
    return RecoveryAction.objects.get(pk=recovery.pk)
