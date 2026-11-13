"""Bounded, asynchronous materialized searches over the shared projections.

The session stores identities and ranking order, not a second copy of quotations.
Every read rehydrates through the publication/permission boundary. An expansion
only appends; signed cursors address the immutable stored order including tombstones.
"""
from __future__ import annotations

from collections import Counter
from datetime import timedelta
import hashlib
import hmac
import logging
import re
import secrets
from uuid import UUID, uuid4

from billiard.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import NotFound, Throttled, ValidationError

from catalog.discovery_models import DiscoverySearchSession
from catalog.services.semantic_search import viewer_access_statuses
from common.concurrency import capacity_slot
from catalog.services.discovery_documents import (
    effective_filters, allowed_rows, begin_document_query, finish_document_query, document_payload,
)

logger = logging.getLogger(__name__)
CHANNELS = ("passages", "entities", "curation")
DEEP_CHANNEL = "deep"
DEEP_RESULTS_KEY = "passages_deep"
DEEP_RANKED_KEY = "passages_deep_ranked"
RESUME_KEY = "_resume"
DISPLAY_SORTS = ("relevance", "year_desc", "year_asc")
PIPELINE_VERSION = "discovery-3.0.8-1"
CURSOR_SALT = "catalog.discovery.cursor.v1"
ACTIVE = ("queued", "running")
MAX_MATERIALIZED = 400
MAX_VISIBLE_PASSAGES = MAX_MATERIALIZED + 40
STALE_MINUTES = {"queued": 30, "running": 15}


def request_access(request) -> list[str]:
    user = request.user
    authenticated = bool(user and user.is_authenticated)
    staff = authenticated and bool(getattr(user, "is_staff", False) or
                                   getattr(user, "role", "") in {"admin", "editor", "reviewer"})
    return viewer_access_statuses(authenticated=authenticated, staff=staff)


def normalize_filters(raw) -> dict:
    if raw in (None, ""):
        return {}
    if not isinstance(raw, dict):
        raise ValidationError({"filters": "筛选条件必须是对象。"})
    aliases = {
        "work": "work_ids", "work_id": "work_ids", "work_ids": "work_ids",
        "scholar": "authors", "author": "authors", "authors": "authors",
        "theory": "theory_node_ids", "theory_node_ids": "theory_node_ids",
        "topic": "topic_ids", "topic_ids": "topic_ids",
        "concept": "concepts", "tag": "concepts", "concepts": "concepts",
        "document_type": "document_types", "document_types": "document_types",
        "language": "languages", "languages": "languages", "year": "years", "years": "years",
        "access": "access", "source_type": "source_types", "source_types": "source_types",
        "availability": "availability",
        "theories": "theories", "topics": "topics",
    }
    output: dict = {}
    for key, value in raw.items():
        if key == "search_scope":
            from catalog.services.discovery_scope import SCOPE_FIELDS
            if not isinstance(value, str) or value not in {"all", *SCOPE_FIELDS}:
                raise ValidationError({key: "请选择有效的检索范围。"})
            if value != "all":
                output[key] = value
            continue
        if key in {"year_min", "year_max"}:
            if value in (None, ""):
                continue
            try:
                number = int(value)
            except (TypeError, ValueError):
                raise ValidationError({key: "年份必须为整数。"})
            if not 1 <= number <= 3000:
                raise ValidationError({key: "年份必须在 1 至 3000 之间。"})
            output[key] = number
            continue
        if key not in aliases:
            # Former stance/sort/display options cannot silently restrict discovery.
            if key in {"relation", "relations", "sort", "max_per_work"}:
                continue
            raise ValidationError({"filters": f"不支持的筛选字段：{str(key)[:60]}"})
        target = aliases[key]
        values = value if isinstance(value, list) else [value]
        if len(values) > 30:
            raise ValidationError({key: "单项筛选最多选择 30 项。"})
        clean = []
        for item in values:
            if item in (None, ""):
                continue
            if not isinstance(item, (str, int)) or isinstance(item, bool):
                raise ValidationError({key: "筛选项必须为字符串。"})
            clean.extend(part.strip() for part in str(item).split(",") if part.strip())
        if len(clean) > 30 or any(len(item) > 160 for item in clean):
            raise ValidationError({key: "筛选条件过长。"})
        if target in {"work_ids", "authors", "theory_node_ids", "topic_ids"}:
            identifiers, slugs = [], []
            for item in clean:
                try:
                    identifiers.append(str(UUID(item)))
                except (TypeError, ValueError):
                    slugs.append(item)
            if slugs and target in {"work_ids", "authors"}:
                raise ValidationError({key: "作品与学者筛选需要有效的馆内标识。"})
            if slugs:
                legacy = "theories" if target == "theory_node_ids" else "topics"
                output[legacy] = list(dict.fromkeys([*output.get(legacy, []), *slugs]))
            clean = identifiers
        output[target] = list(dict.fromkeys([*output.get(target, []), *clean]))
    if output.get("year_min", 1) > output.get("year_max", 3000):
        raise ValidationError({"year_max": "结束年份不能早于起始年份。"})
    if any(value not in {"readable", "pdf", "zh_translation"} for value in output.get("availability", [])):
        raise ValidationError({"availability": "可读版本筛选无效。"})
    source_types = output.pop("source_types", [])
    mapping = {"book": ["book"], "journal": ["journal_article", "journal_issue"], "other": ["thesis", "report", "chapter", "other"]}
    if any(value not in mapping for value in source_types):
        raise ValidationError({"source_type": "材料类型无效。"})
    if source_types:
        output["document_types"] = list(dict.fromkeys([
            *output.get("document_types", []), *(kind for value in source_types for kind in mapping[value])]))
    if output.get("document_types"):
        output["document_types"] = ["journal_article" if value == "article" else value for value in output["document_types"]]
        if any(value not in {"book", "journal_article", "journal_issue", "thesis", "report", "chapter", "other"} for value in output["document_types"]):
            raise ValidationError({"document_type": "文献类型无效。"})
    return output


def _warning(code: str, message: str, channel: str = "") -> dict:
    return {"code": code, "message": message, **({"channel": channel} if channel else {})}


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _enqueue(session_id, generation: int, task_id: str) -> None:
    from catalog.discovery_tasks import run_discovery_search
    try:
        run_discovery_search.apply_async(args=[str(session_id), generation], task_id=task_id,
                                         queue=getattr(settings, "DISCOVERY_QUERY_TASK_QUEUE", "celery"))
    except Exception as exc:
        logger.warning("Discovery dispatch failed: %s", type(exc).__name__)
        fail_session(session_id, generation, task_id, "queue_unavailable", statuses=("queued",))


def close_stale_sessions(*, session_id=None) -> int:
    """Close abandoned work without requeueing it or spending expansion budget."""
    now = timezone.now()
    stale = Q()
    for state, minutes in STALE_MINUTES.items():
        stale |= Q(status=state, updated_at__lt=now - timedelta(minutes=minutes))
    rows = DiscoverySearchSession.objects.filter(stale)
    if session_id is not None:
        rows = rows.filter(pk=session_id)
    closed = 0
    for row in rows.order_by("updated_at")[:25]:
        closed += int(fail_session(row.pk, row.generation, row.task_id, "task_timeout",
                                   observed_updated_at=row.updated_at))
    return closed


def _check_admission(owner, now):
    # Abandoned sessions must not occupy all admission slots until a reader
    # happens to poll them. No additional scheduled task is needed.
    close_stale_sessions()
    active = DiscoverySearchSession.objects.filter(status__in=ACTIVE, expires_at__gt=now)
    if active.count() >= max(2, int(getattr(settings, "DISCOVERY_MAX_QUEUED_QUERIES", 12))):
        raise Throttled(wait=10, detail="馆内检索任务正在处理，请稍后重试。")
    if owner and active.filter(owner=owner).count() >= 2:
        raise Throttled(wait=5, detail="请先等待或取消当前检索。")


def create_session(request, query: str, filters: dict) -> tuple[DiscoverySearchSession, str]:
    # Serialize admission across web workers, but never hold an HTTP request in
    # a wait queue. The shared cache lock expires even if the process is lost.
    with capacity_slot("discovery-admission", limit=1, timeout=10) as acquired:
        if not acquired:
            raise Throttled(wait=1, detail="正在接收其他检索，请稍后重试。")
        return _create_session(request, query, filters)


def _create_session(request, query: str, filters: dict) -> tuple[DiscoverySearchSession, str]:
    query = str(query or "").strip()
    if not 2 <= len(query) <= 1200:
        raise ValidationError({"q": "请输入 2 至 1200 个字符的概念、问题或原文线索。"})
    owner = request.user if request.user.is_authenticated else None
    now = timezone.now()
    _check_admission(owner, now)
    token = secrets.token_urlsafe(32)
    task_id = str(uuid4())
    with transaction.atomic():
        session = DiscoverySearchSession.objects.create(
            owner=owner, token_hash=_token_hash(token), query=query, filters=filters,
            access_statuses=request_access(request), task_id=task_id,
            results={**{channel: [] for channel in CHANNELS}, DEEP_RESULTS_KEY: []},
            channels={**{channel: {"status": "pending"} for channel in CHANNELS},
                      DEEP_CHANNEL: {"status": "pending"}},
            expires_at=now + timedelta(hours=24))
        from reading.privacy import remember_search_after_commit, retention_enabled
        if owner and retention_enabled(owner, "search_history"):
            transaction.on_commit(lambda: remember_search_after_commit(owner, session.id, query, filters))
        transaction.on_commit(lambda: _enqueue(session.id, session.generation, task_id))
    session.refresh_from_db()
    return session, token


def get_session(request, session_id) -> DiscoverySearchSession:
    session = DiscoverySearchSession.objects.filter(pk=session_id, expires_at__gt=timezone.now()).first()
    if session is None:
        raise NotFound("检索记录不存在或已过期，请重新检索。")
    if session.owner_id:
        permitted = request.user.is_authenticated and str(request.user.pk) == str(session.owner_id)
    else:
        token = str(request.headers.get("X-Discovery-Token") or "")
        permitted = bool(token) and len(token) <= 200 and hmac.compare_digest(session.token_hash, _token_hash(token))
    if not permitted:
        raise NotFound("检索记录不存在或已过期，请重新检索。")
    # Lost workers must not leave the reader polling forever. Late deliveries
    # are rejected by the same terminal-state/generation check in the task.
    if session.status in ACTIVE and close_stale_sessions(session_id=session.pk):
        session.refresh_from_db()
    return session


def session_access(session: DiscoverySearchSession, request) -> list[str]:
    # Signing in or acquiring staff privileges must not widen an old session.
    return sorted(set(session.access_statuses).intersection(request_access(request)))


def expand_session(session: DiscoverySearchSession, access_statuses=None) -> DiscoverySearchSession:
    return _resume_session(session, access_statuses, expand=True)


def retry_session(session: DiscoverySearchSession, access_statuses, *, expected_generation: int) -> DiscoverySearchSession:
    return _resume_session(session, access_statuses, expand=False, expected_generation=expected_generation)


def _resume_session(session, access_statuses, *, expand, expected_generation=None):
    with capacity_slot("discovery-admission", limit=1, timeout=10) as acquired:
        if not acquired:
            raise Throttled(wait=1, detail="正在接收其他检索，请稍后重试。")
        return _resume_locked(session, access_statuses, expand=expand, expected_generation=expected_generation)


def _resume_locked(session, access_statuses, *, expand, expected_generation):
    with transaction.atomic():
        session = DiscoverySearchSession.objects.select_for_update().get(pk=session.pk)
        if session.expires_at <= timezone.now():
            raise NotFound("检索记录已过期，请重新检索。")
        if not expand:
            # A repeated POST for the same observed attempt returns its current
            # state. It never creates a second task, even after that task ends.
            resume = (session.results or {}).get(RESUME_KEY) or {}
            if (session.generation == expected_generation + 1
                    and resume.get("kind") == "retry"
                    and resume.get("previous_generation") == expected_generation):
                return session
            if session.generation != expected_generation:
                raise ValidationError({"expected_generation": "检索轮次已改变，请刷新后重试。"})
            if session.status not in {"failed", "partial", "canceled"}:
                raise ValidationError({"detail": "只有失败、部分完成或已取消的检索可以继续。"})
        if session.status in ACTIVE:
            raise ValidationError({"detail": "当前检索尚在进行，请等待完成后扩大范围。"})
        if expand and session.status == "canceled":
            raise ValidationError({"detail": "请先继续已取消的检索，再扩大范围。"})
        if expand and session.expansion_count >= 1:
            raise ValidationError({"detail": "本次检索已使用扩展预算，可调整问题后重新检索。"})
        _check_admission(session.owner_id, timezone.now())
        session.expansion_count += int(expand)
        session.generation += 1
        session.status = "queued"
        session.task_id = str(uuid4())
        session.finished_at = None
        session.started_at = None
        previous_deep = (session.channels or {}).get(DEEP_CHANNEL, {})
        session.results = {
            **(session.results or {}),
            DEEP_RANKED_KEY: (session.results or {}).get(
                DEEP_RANKED_KEY, (previous_deep.get("bge") or {}).get("status") == "completed"),
            # Only identities, never copied quotations or bibliography. A
            # reread marks additions only while those sources remain valid.
            RESUME_KEY: {
                "kind": "expand" if expand else "retry",
                "previous_generation": session.generation - 1,
                "baseline": {
                    channel: sorted({_resume_identity(ref) for ref in [
                        *(session.results or {}).get(channel, [])[:MAX_MATERIALIZED],
                        *((session.results or {}).get(DEEP_RESULTS_KEY, [])[:MAX_MATERIALIZED]
                          if channel == "passages" else []),
                    ] if _identity(ref)}) for channel in CHANNELS
                },
            },
        }
        session.channels = {
            **{channel: {"status": "pending"} for channel in CHANNELS},
            DEEP_CHANNEL: {"status": "pending"},
        }
        if access_statuses is not None:
            session.access_statuses = sorted(set(session.access_statuses).intersection(access_statuses))
        session.save(update_fields=["expansion_count", "generation", "status", "task_id", "started_at", "finished_at", "channels", "results", "access_statuses", "updated_at"])
        transaction.on_commit(lambda: _enqueue(session.id, session.generation, session.task_id))
    session.refresh_from_db()
    return session


def cancel_session(session: DiscoverySearchSession) -> DiscoverySearchSession:
    with transaction.atomic():
        session = DiscoverySearchSession.objects.select_for_update().get(pk=session.pk)
        if session.status in ACTIVE:
            session.status = "canceled"
            session.finished_at = timezone.now()
            session.generation += 1
            session.channels = {key: ({"status": "canceled"} if value.get("status") in {"pending", "queued", "running"} else value)
                                for key, value in session.channels.items()}
            session.save(update_fields=["status", "finished_at", "generation", "channels", "updated_at"])
    # Cooperative cancellation avoids terminating a shared worker or indexing.
    return session


def _identity(row: dict) -> str:
    return str(row.get("id") or "")


def _resume_identity(row: dict) -> str:
    return f"{_identity(row)}:{row.get('source_revision') or ''}"


def _mark_additions(session, channel: str, rows: list[dict]) -> list[dict]:
    baseline = ((session.results or {}).get(RESUME_KEY) or {}).get("baseline")
    previous = set(baseline.get(channel, [])) if isinstance(baseline, dict) else None
    return [{**row, "is_new": previous is not None and _resume_identity(row) not in previous}
            for row in rows]


def _reference(row: dict) -> dict:
    return {"id": _identity(row), "source_revision": str(row.get("source_revision") or ""),
            "knowledge_assertion_ids": [str(value) for value in row.get("knowledge_assertion_ids", [])[:4]],
            "match_basis": [str(item)[:160] for item in row.get("match_basis", [])[:5]]}


def _deep_reference(row: dict) -> dict:
    """Keep only bounded deep annotations beside the source identity."""
    reference = _reference(row)
    for key in ("deep_rank", "deep_score", "deep_context"):
        if key not in row:
            continue
        value = row[key]
        if key == "deep_context" and isinstance(value, dict):
            value = {
                "policy": str(value.get("policy") or "")[:80],
                "provider": str(value.get("provider") or "")[:80],
                "available": bool(value.get("available")),
                # Text is re-read by session_context. Persisting neighbour
                # quotations here would serve stale text after their edits.
                "blocks": [
                    {
                        "evidence_span_id": str(block.get("evidence_span_id") or ""),
                        "document_revision_id": str(block.get("document_revision_id") or ""),
                        "pdf_page": block.get("pdf_page"),
                        "role": str(block.get("role") or "")[:24],
                    }
                    for block in value.get("blocks") or []
                    if isinstance(block, dict)
                ][:6],
                **{key: value[key] for key in ("context_score", "context_rank", "truncated", "query_truncated")
                   if key in value},
            }
        reference[key] = value
    return reference


def _rrf(branches: list[tuple[list[dict], float]]) -> list[dict]:
    scores, rows = {}, {}
    for candidates, weight in branches:
        seen = set()
        for rank, row in enumerate(candidates, start=1):
            key = _identity(row)
            if not key or key in seen:
                continue
            seen.add(key)
            rows.setdefault(key, row)
            scores[key] = scores.get(key, 0.0) + weight / (60 + rank)
    return [rows[key] for key in sorted(rows, key=lambda key: (-scores[key], key))]


def _deduplicate(rows: list[dict]) -> list[dict]:
    seen, output = set(), []
    for row in rows:
        text = re.sub(r"\s+", "", str(row.get("excerpt") or row.get("text") or ""))
        # Same paragraph duplicated by overlapping windows does not consume
        # multiple reranker slots. Preserve other passages from the same book.
        key = (str(row.get("asset_id") or (row.get("metadata") or {}).get("asset_id") or ""),
               hashlib.sha256(text.encode()).hexdigest())
        if text and key in seen:
            continue
        metadata = row.get("metadata") or {}
        start = row.get("start_offset", metadata.get("start_offset"))
        end = row.get("end_offset", metadata.get("end_offset"))
        if "page_text_range" in row:
            exact = row["page_text_range"] or {}
            start, end = exact.get("start"), exact.get("end")
        page = row.get("pdf_page") or metadata.get("pdf_page") or metadata.get("page_number")
        if isinstance(start, int) and isinstance(end, int) and end > start:
            duplicate = False
            for prior in output:
                old = prior.get("metadata") or {}
                other_start = prior.get("start_offset", old.get("start_offset"))
                other_end = prior.get("end_offset", old.get("end_offset"))
                if "page_text_range" in prior:
                    exact = prior["page_text_range"] or {}
                    other_start, other_end = exact.get("start"), exact.get("end")
                if (key[0] == str(prior.get("asset_id") or old.get("asset_id") or "") and
                        page == (prior.get("pdf_page") or old.get("pdf_page") or old.get("page_number")) and
                        isinstance(other_start, int) and isinstance(other_end, int) and other_end > other_start):
                    overlap = max(0, min(end, other_end) - max(start, other_start))
                    if overlap / min(end - start, other_end - other_start) >= 0.8:
                        duplicate = True
                        break
            if duplicate:
                continue
        seen.add(key)
        output.append(row)
    return output


def _diverse_prefix(rows: list[dict], *, eligible_count: int | None = None) -> list[dict]:
    # Limit repetition only within the first six ranks, allowing two highly
    # ranked passages per work. Scan the eligible pool, retaining deferred hits
    # in their original order after the first screen.
    counts, prefix, deferred = Counter(), [], []
    eligible = rows if eligible_count is None else rows[:eligible_count]
    for row in eligible:
        work = row.get("work") or (row.get("metadata") or {}).get("work") or {}
        work_id = str(work.get("id") or row.get("work_id") or _identity(row))
        if len(prefix) < 6 and counts[work_id] < 2:
            prefix.append(row)
            counts[work_id] += 1
        else:
            deferred.append(row)
    return prefix + deferred + rows[len(eligible):]


def _rerank(query: str, rows: list[dict], limit: int, expected_artifact: str) -> tuple[list[dict], list[dict]]:
    if not rows:
        return rows, []
    from catalog.services.discovery_inference import DiscoveryInferenceError, rerank
    candidates = rows[:limit]
    try:
        if not expected_artifact:
            raise DiscoveryInferenceError("artifact_missing", "当前索引未固定重排模型版本。")
        ranked = rerank(query, ["\n".join(filter(None, [row.get("context_text"), str(row.get("excerpt") or row.get("text") or "")])) for row in candidates],
                        top_n=len(candidates), expected_artifact=expected_artifact)
        order = [int(item["index"]) for item in ranked.get("results", [])]
        if sorted(order) != list(range(len(candidates))):
            raise ValueError("Incomplete reranker permutation")
        warnings = []
        if ranked.get("query_truncated") or any(item.get("truncated") for item in ranked.get("results", [])):
            warnings.append(_warning("rerank_windowed", "部分长文本按有界窗口参与相关性重排；展示原文未被改写。", "passages"))
        return [candidates[index] for index in order] + rows[len(candidates):], warnings
    except (DiscoveryInferenceError, ValueError, TypeError, KeyError) as exc:
        logger.warning("Discovery reranker unavailable: %s", type(exc).__name__)
        return rows, [_warning("reranker_unavailable", "本地重排暂不可用，已保留关键词与向量融合次序。", "passages")]


def _task_current(session_id, generation: int, task_id: str) -> bool:
    return DiscoverySearchSession.objects.filter(pk=session_id, generation=generation, task_id=task_id,
                                                 status__in=ACTIVE, expires_at__gt=timezone.now()).exists()


def retrieve_discovery_channel(*args, **kwargs):
    """Compatibility name for existing callers."""
    from catalog.services.retrieval.search import retrieve_channel
    return retrieve_channel(*args, **kwargs)


def _deep_task_current(session_id, generation: int, task_id: str) -> bool:
    return DiscoverySearchSession.objects.filter(
        pk=session_id,
        generation=generation,
        task_id=task_id,
        status__in=ACTIVE,
        expires_at__gt=timezone.now(),
    ).exists()


def _deep_reference_rows(session, access_statuses) -> list[dict]:
    """Rehydrate baseline passage identities before the optional deep stages."""
    from catalog.services.discovery_projection import validate_discovery_results

    refs = (session.results or {}).get("passages", [])[:MAX_MATERIALIZED]
    rows = allowed_rows(session, validate_discovery_results("passages", refs, access_statuses, filters=effective_filters(session)))
    by_key = {(_identity(row), str(row.get("source_revision") or "")): row for row in rows}
    return [
        row
        for ref in refs
        if (row := by_key.get((_identity(ref), str(ref.get("source_revision") or "")))) is not None
    ]


def execute_deep_session(session_id, generation: int, task_id: str) -> None:
    """Asynchronously supplement a completed first screen in the same session."""
    from catalog.services.retrieval.deep_pipeline import DEEP_RESULT_KEY, run_deep_pipeline

    with transaction.atomic():
        session = DiscoverySearchSession.objects.select_for_update().filter(pk=session_id).first()
        if (
            session is None
            or session.generation != generation
            or session.task_id != task_id
            or session.status not in ACTIVE
            or session.expires_at <= timezone.now()
        ):
            return
        session.channels = {
            **(session.channels or {}),
            DEEP_CHANNEL: {"status": "running", "pipeline_version": "stl4-recommended-deep-v1"},
        }
        session.save(update_fields=["channels", "updated_at"])
    try:
        session.refresh_from_db()
        access_statuses = list(session.access_statuses or [])
        baseline = _deep_reference_rows(session, access_statuses)
        result = run_deep_pipeline(
            session.query,
            baseline,
            access_statuses,
            filters=effective_filters(session),
            is_current=lambda: _deep_task_current(session_id, generation, task_id),
        )
        if result.get("status") == "canceled":
            return
        rows = result.get("rows") or []
        from catalog.services.discovery_projection import validate_discovery_results

        annotations = {
            _identity(row): {
                key: row[key]
                for key in ("deep_rank", "deep_score", "deep_context")
                if key in row
            }
            for row in rows
        }
        rows = allowed_rows(session, validate_discovery_results("passages", rows, access_statuses, filters=effective_filters(session)))
        for row in rows:
            row.update(annotations.get(_identity(row), {}))
        refs = [_deep_reference(row) for row in rows[:MAX_MATERIALIZED] if _identity(row)]
        stage = {
            key: value
            for key, value in result.items()
            if key not in {"rows", "warnings"}
        }
        embedding_state = result.get("embedding") if isinstance(result.get("embedding"), dict) else {}
        bge_state = result.get("bge") if isinstance(result.get("bge"), dict) else {}
        context_state = result.get("convmemory") if isinstance(result.get("convmemory"), dict) else {}
        baseline_identity = (session.versions or {}).get("_identity", {})
        if not isinstance(baseline_identity, dict):
            baseline_identity = {}
        embedding_ready = embedding_state.get("status") == "completed"
        stage.update({
            # These fields are evidence of a loaded, queried deep index. A
            # configured UID/artifact alone is not enough to expose it as
            # active metadata in the visual workbench.
            "index_uid": str(embedding_state.get("index_uid") or "") if embedding_ready else "",
            "index_generation": str(
                getattr(settings, "STL_DEEP_RETRIEVAL_GENERATION", "")
                or baseline_identity.get("index_generation")
                or ""
            ) if embedding_ready else "",
            "embedding_artifact": str(embedding_state.get("artifact") or "") if embedding_ready else "",
            "embedding_dimensions": embedding_state.get("dimensions") if embedding_ready else None,
            # A configured model name is not proof that the isolated worker
            # loaded it. Keep artifact identity empty until that stage reports
            # completion; the nested state still exposes the requested model
            # and its pending/degraded status for the UI.
            "reranker_artifact": str(
                bge_state.get("artifact") or ""
            ) if bge_state.get("status") == "completed" else "",
            "context_artifact": str(
                context_state.get("artifact") or context_state.get("artifact_id") or ""
            ) if context_state.get("status") == "completed" else "",
        })
        stage.update({"status": result.get("status", "degraded"), "warnings": result.get("warnings", [])})
        with transaction.atomic():
            current = DiscoverySearchSession.objects.select_for_update().get(pk=session_id)
            if not _deep_task_current(session_id, generation, task_id):
                return
            # A failed retry must not erase the last usable deep prefix. Every
            # response still revalidates that prefix against current sources.
            if result.get("ranking_applied") or not (current.results or {}).get(DEEP_RESULT_KEY):
                current.results = {**(current.results or {}), DEEP_RESULT_KEY: refs,
                                   DEEP_RANKED_KEY: bool(result.get("ranking_applied"))}
            current.channels = {**(current.channels or {}), DEEP_CHANNEL: stage}
            version = str(result.get("pipeline_version") or "stl4-recommended-deep-v1")
            versions = list((current.versions or {}).get(DEEP_CHANNEL) or [])
            if version not in versions:
                versions.append(version)
            current.versions = {**(current.versions or {}), DEEP_CHANNEL: versions}
            unique_warnings = {
                str(item.get("code", "")) + str(item.get("channel", "")): item
                for item in [*(current.warnings or []), *(result.get("warnings") or [])]
                if isinstance(item, dict)
            }
            current.warnings = list(unique_warnings.values())[:20]
            baseline_states = [
                value.get("status")
                for key, value in (current.channels or {}).items()
                if key != DEEP_CHANNEL
            ]
            deep_status = str(stage.get("status") or "degraded")
            current.status = (
                "failed"
                if not baseline_states or all(value == "failed" for value in baseline_states)
                else "partial"
                if deep_status in {"failed", "degraded"}
                or any(value in {"failed", "degraded"} for value in baseline_states)
                else "completed"
            )
            current.finished_at = timezone.now()
            current.save(update_fields=["results", "channels", "versions", "warnings", "status", "finished_at", "updated_at"])
    except Exception as exc:
        logger.warning("Deep discovery failed: %s", type(exc).__name__)
        fail_deep_session(session_id, generation, task_id)


def fail_deep_session(session_id, generation: int, task_id: str, code: str = "deep_task_failed") -> bool:
    """Mark only the optional deep stage failed, preserving baseline cards."""
    with transaction.atomic():
        current = DiscoverySearchSession.objects.select_for_update().filter(
            pk=session_id, generation=generation, task_id=task_id, status__in=ACTIVE
        ).first()
        if current is None:
            return False
        current.channels = {
            **(current.channels or {}),
            DEEP_CHANNEL: {
                "status": "failed",
                "pipeline_version": "stl4-recommended-deep-v1",
            },
        }
        current.warnings = [
            *(current.warnings or []),
            _warning(code, "深度检索暂未完成，已保留首屏检索结果。", DEEP_CHANNEL),
        ][-20:]
        baseline_states = [
            value.get("status")
            for key, value in (current.channels or {}).items()
            if key != DEEP_CHANNEL
        ]
        current.status = "failed" if baseline_states and all(value == "failed" for value in baseline_states) else "partial"
        current.finished_at = timezone.now()
        current.save(update_fields=["channels", "warnings", "status", "finished_at", "updated_at"])
        return True


def execute_session(session_id, generation: int, task_id: str) -> None:
    with transaction.atomic():
        session = DiscoverySearchSession.objects.select_for_update().filter(pk=session_id).first()
        if (session is None or session.generation != generation or session.task_id != task_id or
                session.status != "queued" or session.expires_at <= timezone.now()):
            return
        session.status = "running"
        session.started_at = timezone.now()
        session.warnings = []
        session.save(update_fields=["status", "started_at", "warnings", "updated_at"])
    expanded = session.expansion_count > 0
    aliases: list[str] = []
    # Ephemeral per-task preparation: one original-query vector is reused by
    # all three channels, pinned to the same index generation. Never shared
    # across users or retained as query history.
    retrieval_context: dict = {"on_passage_scope": lambda scopes, index: begin_document_query(
        session_id, generation, task_id, scopes, index)}
    channel_states = {}
    for channel in ("entities", "curation", "passages"):
        if not _task_current(session_id, generation, task_id):
            return
        with transaction.atomic():
            current = DiscoverySearchSession.objects.select_for_update().get(pk=session_id)
            if current.generation != generation or current.task_id != task_id or current.status not in ACTIVE:
                return
            current.channels = {**current.channels, channel: {"status": "running"}}
            current.save(update_fields=["channels", "updated_at"])
        cap = (300 if expanded else 100) if channel == "passages" else (40 if expanded else 16)
        warnings = []
        result = {}
        try:
            result = retrieve_discovery_channel(session.query, channel, effective_filters(session), session.access_statuses,
                limit=cap, expanded=expanded, aliases=aliases, request_context=retrieval_context,
                is_current=lambda: _task_current(session_id, generation, task_id))
            if result["canceled"]:
                return
            rows, warnings = result["rows"], result["warnings"]
            if channel == "entities":
                for row in rows[:6]:
                    for alias in row.get("aliases") or (row.get("metadata") or {}).get("aliases") or []:
                        value = str(alias).strip()
                        if 2 <= len(value) <= 120 and value != session.query and value not in aliases:
                            aliases.append(value)
                aliases = aliases[:6]
            channel_state = {"status": "degraded" if warnings else "completed"}
            version = str(result.get("version") or "")
        except SoftTimeLimitExceeded:
            raise
        except Exception as exc:
            # A failed channel does not erase valid results in another channel.
            # Never expose exception strings (provider URLs or private text).
            logger.warning("Discovery %s failed: %s", channel, type(exc).__name__)
            rows, version = [], ""
            channel_state = {"status": "failed"}
            warnings = [_warning(f"{channel}_unavailable", "此检索通道暂不可用，已保留其他通道的结果。", channel)]
        with transaction.atomic():
            current = DiscoverySearchSession.objects.select_for_update().get(pk=session_id)
            if current.generation != generation or current.task_id != task_id or current.status not in ACTIVE:
                return
            existing = list((current.results or {}).get(channel, []))
            seen = {_identity(row) for row in existing}
            additions = [_reference(row) for row in rows if _identity(row) not in seen]
            current.results = {**current.results, channel: (existing + additions)[:MAX_MATERIALIZED]}
            if channel == "passages":
                finish_document_query(current, warnings, failed=channel_state["status"] == "failed")
            current.channels = {**current.channels, channel: channel_state}
            versions = list((current.versions or {}).get(channel) or [])
            if version and version not in versions:
                versions.append(version)
            version_state = {**current.versions, channel: versions}
            # Keep verified model/index identity beside the immutable version
            # list. This is diagnostics only and does not change ranking or
            # access; absent backend metadata stays absent in the response.
            identity = {
                "index_uid": str(result.get("index_uid") or ""),
                "embedding_artifact": str(result.get("embedding_artifact") or ""),
                "embedding_dimensions": result.get("embedding_dimensions"),
                "reranker_artifact": str(result.get("reranker_artifact") or ""),
                "index_generation": version,
            }
            if any(value not in ("", None) for value in identity.values()):
                version_state["_identity"] = {key: value for key, value in identity.items()
                                                if value not in ("", None)}
            current.versions = version_state
            unique_warnings = {str(item.get("code", "")) + str(item.get("channel", "")): item
                               for item in [*current.warnings, *warnings] if isinstance(item, dict)}
            current.warnings = list(unique_warnings.values())[:20]
            current.save(update_fields=["results", "channels", "versions", "warnings", "updated_at"])
        channel_states[channel] = channel_state["status"]
    if not _task_current(session_id, generation, task_id):
        return
    statuses = list(channel_states.values())
    terminal = "failed" if all(value == "failed" for value in statuses) else (
        "partial" if any(value in {"failed", "degraded"} for value in statuses) else "completed")
    deep_enabled = bool(getattr(settings, "STL_DEEP_RETRIEVAL_ENABLED", False)) and not session.filters.get("search_scope")
    deep_task_id = str(uuid4()) if deep_enabled else ""
    with transaction.atomic():
        current = DiscoverySearchSession.objects.select_for_update().filter(
            pk=session_id, generation=generation, task_id=task_id, status__in=ACTIVE
        ).first()
        if current is None:
            return
        passages = list((current.results or {}).get("passages", []))
        if deep_enabled and passages:
            # Baseline cards stay visible while the deep stages run. The task
            # id moves with the same generation so cancel/retry remains safe.
            current.task_id = deep_task_id
            current.channels = {
                **(current.channels or {}),
                DEEP_CHANNEL: {
                    "status": "queued",
                    "pipeline_version": "stl4-recommended-deep-v1",
                    "task_id": deep_task_id,
                },
            }
            current.status = "running"
            current.save(update_fields=["task_id", "channels", "status", "updated_at"])
        else:
            current.channels = {
                **(current.channels or {}),
                DEEP_CHANNEL: {
                    "status": "disabled" if not deep_enabled else "skipped",
                    "pipeline_version": "stl4-recommended-deep-v1",
                    "reason": "field_scope" if current.filters.get("search_scope") else "feature_disabled" if not deep_enabled else "no_baseline_results",
                },
            }
            current.status = terminal
            current.finished_at = timezone.now()
            current.save(update_fields=["channels", "status", "finished_at", "updated_at"])
            deep_task_id = ""
    if deep_task_id:
        from catalog.discovery_tasks import run_discovery_deep

        try:
            run_discovery_deep.apply_async(
                args=[str(session_id), generation],
                task_id=deep_task_id,
                queue=getattr(settings, "DISCOVERY_QUERY_TASK_QUEUE", "celery"),
            )
        except Exception as exc:
            logger.warning("Deep discovery dispatch failed: %s", type(exc).__name__)
            with transaction.atomic():
                current = DiscoverySearchSession.objects.select_for_update().filter(
                    pk=session_id, generation=generation, task_id=deep_task_id, status__in=ACTIVE
                ).first()
                if current is not None:
                    current.channels = {
                        **(current.channels or {}),
                        DEEP_CHANNEL: {
                            "status": "failed",
                            "pipeline_version": "stl4-recommended-deep-v1",
                        },
                    }
                    current.status = "failed" if terminal == "failed" else "partial"
                    current.finished_at = timezone.now()
                    current.warnings = [
                        *(current.warnings or []),
                        _warning("deep_queue_unavailable", "深度检索任务暂未排队，已保留首屏检索结果。", "deep"),
                    ][-20:]
                    current.save(update_fields=["channels", "status", "finished_at", "warnings", "updated_at"])


def fail_session(session_id, generation: int, task_id: str, code="task_failed", *,
                 statuses=ACTIVE, observed_updated_at=None) -> bool:
    with transaction.atomic():
        rows = DiscoverySearchSession.objects.select_for_update().filter(
            pk=session_id, generation=generation, task_id=task_id, status__in=statuses)
        if observed_updated_at is not None:
            rows = rows.filter(updated_at=observed_updated_at)
        session = rows.first()
        if session is None:
            return False
        session.status = "partial" if any(
            (session.results or {}).get(channel) for channel in (*CHANNELS, DEEP_RESULTS_KEY)
        ) else "failed"
        session.finished_at = timezone.now()
        session.warnings = [*session.warnings, _warning(code, "检索任务未能完成，已保留找到的材料，可重试当前范围。")][-20:]
        session.channels = {key: ({"status": "failed"} if value.get("status") in {"pending", "queued", "running"} else value)
                            for key, value in session.channels.items()}
        session.save(update_fields=["status", "finished_at", "warnings", "channels", "updated_at"])
        return True


def _rehydrate(session, access_statuses) -> dict[str, list[dict]]:
    from catalog.services.discovery_projection import validate_discovery_results
    output = {}
    for channel in CHANNELS:
        refs = (session.results or {}).get(channel, [])[:MAX_MATERIALIZED]
        fresh = validate_discovery_results(channel, refs, access_statuses, filters=effective_filters(session))
        if channel == "passages":
            fresh = allowed_rows(session, fresh)
        by_id = {(_identity(row), str(row.get("source_revision") or "")): row for row in fresh}
        output[channel] = []
        for position, ref in enumerate(refs):
            row = by_id.get((_identity(ref), str(ref.get("source_revision") or "")))
            if row is not None:
                row = dict(row)
                row["_position"] = position
                row["match_basis"] = ref.get("match_basis") or row.get("match_basis") or []
                output[channel].append(row)
        output[channel] = _mark_additions(session, channel, output[channel])
        if channel == "passages":
            from catalog.services.retrieval.locators import attach_locators
            output[channel] = attach_locators(output[channel])
    return output


def _rehydrate_deep(session, access_statuses) -> list[dict]:
    from catalog.services.discovery_projection import validate_discovery_results

    refs = (session.results or {}).get(DEEP_RESULTS_KEY, [])[:MAX_MATERIALIZED]
    fresh = allowed_rows(session, validate_discovery_results("passages", refs, access_statuses, filters=effective_filters(session)))
    by_key = {(_identity(row), str(row.get("source_revision") or "")): row for row in fresh}
    output = []
    for position, ref in enumerate(refs):
        row = by_key.get((_identity(ref), str(ref.get("source_revision") or "")))
        if row is None:
            continue
        row = dict(row)
        row["_position"] = position
        row["match_basis"] = ref.get("match_basis") or row.get("match_basis") or []
        annotations = _deep_reference(ref)
        for key in ("deep_rank", "deep_score", "deep_context"):
            if key in annotations:
                row[key] = annotations[key]
        output.append(row)
    from catalog.services.retrieval.locators import attach_locators
    return attach_locators(_mark_additions(session, "passages", output))


def _deep_order_token(session) -> str:
    results = session.results or {}
    stage = (session.channels or {}).get(DEEP_CHANNEL, {})
    ranked = results.get(DEEP_RANKED_KEY, (stage.get("bge") or {}).get("status") == "completed")
    refs = results.get(DEEP_RESULTS_KEY, [])[:40]
    if not ranked or not refs:
        return "baseline"
    identity = "|".join(f"{_identity(ref)}:{ref.get('source_revision', '')}" for ref in refs)
    return "deep:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()


def rehydrate_passages(session, access_statuses, *, baseline_only=False,
                       baseline_rows=None, deep_rows=None) -> list[dict]:
    """One validated passage order for cards, pagination and research capture.

    Deep ranking supplements a bounded prefix; it never discards the baseline
    tail. Positions belong to stored references, so withdrawn rows remain
    tombstones and cannot make a cursor skip the next still-readable source.
    """
    baseline = _rehydrate(session, access_statuses)["passages"] if baseline_rows is None else baseline_rows
    deep = _rehydrate_deep(session, access_statuses) if deep_rows is None else deep_rows
    results = session.results or {}
    refs = list(results.get("passages", [])[:MAX_MATERIALIZED])
    if not baseline_only and _deep_order_token(session) != "baseline":
        prefix = list(results.get(DEEP_RESULTS_KEY, [])[:40])
        seen = {(_identity(ref), str(ref.get("source_revision") or "")) for ref in prefix}
        refs = prefix + [ref for ref in refs
                         if (_identity(ref), str(ref.get("source_revision") or "")) not in seen]
    by_key = {(_identity(row), str(row.get("source_revision") or "")): row for row in [*baseline, *deep]}
    output = []
    for position, ref in enumerate(refs):
        row = by_key.get((_identity(ref), str(ref.get("source_revision") or "")))
        if row is not None:
            output.append({**row, "_position": position})
    return output


def _public_row(row: dict) -> dict:
    # Projection diagnostics, access filters and ranking scores are never part
    # of a public card. Their existence must not expand the response contract.
    allowed = {"id", "title", "excerpt", "text", "url", "reader_url", "source_kind", "source_label",
               "source_title", "recommendation_excerpt", "source_revision", "portrait_url", "portrait_media", "kind",
               "linked_work_ids", "match_basis", "pdf_page", "page_number", "printed_page", "asset_id",
               "edition_id", "work_id", "document_revision_id", "evidence_span_id", "passage_id",
               "work", "authors", "locator_precision", "context_reference", "deep_rank", "deep_score",
               "deep_context", "bibliography", "section_title", "attribution", "is_new",
               "locator", "anchor_id", "node_id", "coverage", "source_type", "knowledge_paths"}
    output = {key: value for key, value in row.items() if key in allowed}
    metadata = row.get("metadata") or {}
    if "pdf_page" not in output:
        output["pdf_page"] = output.get("page_number") or metadata.get("page_number") or metadata.get("pdf_page")
    for key in ("asset_id", "edition_id", "work_id", "document_revision_id", "evidence_span_id", "passage_id", "work", "authors", "printed_page", "locator_precision", "context_reference"):
        if key not in output and key in metadata:
            output[key] = metadata[key]
    for key in ("reader_url", "source_kind"):
        if metadata.get(key):
            output[key] = metadata[key]
    output.setdefault("excerpt", output.get("text", ""))
    output.setdefault("context_reference", output.get("id"))
    if row.get("channel") == "passages" or output.get("asset_id"):
        # PDF30's source inspector uses the current published taxonomy already
        # revalidated by source_header, never draft tags or model suggestions.
        for field, node_type in (("related_concepts", "concept"), ("related_theories", "theory_tradition")):
            output[field] = [{"id": str(node["id"]), "title": str(node.get("name") or node.get("foreign_name") or ""), "slug": str(node.get("slug") or "")}
                             for node in row.get("theories", []) if isinstance(node, dict) and node.get("id") and node.get("type") == node_type]
        if not isinstance(output.get("work"), dict):
            url = str(output.get("url") or "")
            output["work"] = {"id": str(output.get("work_id") or ""), "title": str(output.get("title") or "未题名"),
                              "slug": url.removeprefix("/works/") if url.startswith("/works/") else ""}
        output["authors"] = [str(value.get("name") or value.get("preferred_name") or "") if isinstance(value, dict) else str(value)
                             for value in output.get("authors") or []]
        output["authors"] = [value for value in output["authors"] if value]
        output.setdefault("locator_precision", "page")
    output.setdefault("kind", output.get("source_kind") or "knowledge")
    output.setdefault("source_title", output.get("title") or "")
    output.setdefault("recommendation_excerpt", output.get("excerpt") or "")
    return output


DEEP_PROGRESS_STATUSES = {
    "baseline_ready", "deep_queued", "deep_running", "queued", "running",
    "completed", "partial", "degraded", "disabled", "skipped", "unavailable",
}


def _deep_progress(session) -> dict:
    """Project optional deep ranking/context state without inventing completion.

    The baseline Discovery channels remain useful when the isolated BGE /
    ConvMemory worker is not configured. A future deep worker can persist its
    own ``channels.deep`` state; the public response then carries that exact
    state and its verified artifact identities.
    """
    raw = session.channels.get("deep") if isinstance(session.channels, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    raw_status = str(raw.get("status") or "")
    # Workers may persist their implementation state names; keep the public
    # contract stable while they roll forward to the canonical six statuses.
    status = {
        "pending": "deep_queued", "queued": "deep_queued", "running": "deep_running",
        "degraded": "partial", "disabled": "unavailable", "skipped": "unavailable",
        "failed": "unavailable", "canceled": "unavailable",
    }.get(raw_status, raw_status)
    if status not in DEEP_PROGRESS_STATUSES:
        passage = session.channels.get("passages", {}) if isinstance(session.channels, dict) else {}
        passage_status = passage.get("status") if isinstance(passage, dict) else ""
        status = "baseline_ready" if passage_status in {"completed", "degraded"} else "unavailable"
    terminal = status in {"baseline_ready", "completed", "partial", "degraded", "disabled", "skipped", "unavailable"}
    identity = (session.versions or {}).get("_identity", {})
    if not isinstance(identity, dict):
        identity = {}
    deep_state = raw.get("bge") if isinstance(raw.get("bge"), dict) else {}
    context_state = raw.get("convmemory") if isinstance(raw.get("convmemory"), dict) else {}
    embedding_state = raw.get("embedding") if isinstance(raw.get("embedding"), dict) else {}
    baseline_identity_visible = status == "baseline_ready"
    embedding_ready = embedding_state.get("status") == "completed"
    bge_ready = deep_state.get("status") == "completed"
    context_ready = context_state.get("status") == "completed"
    payload = {
        "status": status,
        "stage": str(raw.get("stage") or ("baseline" if status == "baseline_ready" else "deep")),
        "completed": int(raw.get("completed") or (1 if status in {"baseline_ready", "completed", "partial", "degraded", "disabled", "skipped"} else 0)),
        "total": int(raw.get("total") or 1),
        "terminal": bool(raw.get("terminal", terminal)),
        "model": str(raw.get("model") or deep_state.get("model") or context_state.get("model") or ""),
        "index_uid": str(raw.get("index_uid") or (identity.get("index_uid") if baseline_identity_visible else "") or ""),
        "index_generation": str(raw.get("index_generation") or (identity.get("index_generation") if baseline_identity_visible else "") or ""),
        "embedding_artifact": str(raw.get("embedding_artifact") or (embedding_state.get("artifact") if embedding_ready else "") or (identity.get("embedding_artifact") if baseline_identity_visible else "") or ""),
        "embedding_dimensions": raw.get("embedding_dimensions", embedding_state.get("dimensions") if embedding_ready else (identity.get("embedding_dimensions") if baseline_identity_visible else None)),
        # Model names describe the requested provider; artifact fields only
        # describe a loaded, verified bundle. Never copy a model name into an
        # artifact slot while the isolated worker is pending or degraded.
        "reranker_artifact": str(raw.get("reranker_artifact") or (deep_state.get("artifact") if bge_ready else "") or (identity.get("reranker_artifact") if baseline_identity_visible else "") or ""),
        "context_artifact": str(raw.get("context_artifact") or (context_state.get("artifact") or context_state.get("artifact_id") if context_ready else "") or ""),
        "notice": str(raw.get("notice") or ("基础候选已就绪；深度层尚未启动。" if status == "baseline_ready" else
                                              "当前没有可用深度任务，保留基础检索结果。" if status == "unavailable" else "")),
    }
    for key in ("started_at", "updated_at", "finished_at"):
        value = raw.get(key)
        payload[key] = value.isoformat() if hasattr(value, "isoformat") else value
    return payload


def _year_order(row: dict, sort: str) -> tuple[int, int, int]:
    year = (row.get("bibliography") or {}).get("publication_year")
    known = type(year) is int and 1 <= year <= 3000
    return (0 if known else 1, (-year if sort == "year_desc" else year) if known else 0,
            row["_position"])


def serialize_session(session, access_statuses, *, cursor="", limit=3, sort="relevance") -> dict:
    if sort not in DISPLAY_SORTS:
        raise ValidationError({"sort": "请选择相关度、出版年份从新到旧或从旧到新。"})
    offset = 0
    after = None
    order = _deep_order_token(session)
    if cursor:
        try:
            signed = signing.loads(cursor, salt=CURSOR_SALT, max_age=24 * 60 * 60)
            if signed.get("id") != str(session.id):
                raise ValueError("wrong session")
            if signed.get("sort", "relevance") != sort:
                raise ValueError("different sort")
            offset = int(signed["offset"])
            if not 0 <= offset <= MAX_VISIBLE_PASSAGES:
                raise ValueError("bad offset")
            cursor_order = str(signed.get("order") or "baseline")
            if cursor_order != "baseline" and cursor_order != order:
                raise ValueError("ranking changed")
            order = cursor_order
            if sort != "relevance":
                if signed.get("generation") != session.generation:
                    raise ValueError("attempt changed")
                after = signed.get("after")
                if (not isinstance(after, list) or len(after) != 3
                        or any(type(value) is not int for value in after)
                        or after[0] not in (0, 1) or not -3000 <= after[1] <= 3000
                        or not 0 <= after[2] < MAX_VISIBLE_PASSAGES):
                    raise ValueError("invalid year position")
                after = tuple(after)
        except (signing.BadSignature, ValueError, TypeError, KeyError):
            raise ValidationError({"cursor": "分页位置无效或已过期，请重新检索。"})
    limit = max(1, min(int(limit), MAX_VISIBLE_PASSAGES))
    visible = _rehydrate(session, access_statuses)
    deep_visible = _rehydrate_deep(session, access_statuses)
    deep = _deep_progress(session)
    passage_rows = rehydrate_passages(session, access_statuses, baseline_only=order == "baseline",
                                     baseline_rows=visible["passages"], deep_rows=deep_visible)
    if sort == "relevance":
        remaining = [row for row in passage_rows if row["_position"] >= offset]
    else:
        # Sort only revalidated, already materialized candidates; no retrieval
        # or ranker is run here. Stable source positions break same-year ties.
        passage_rows = sorted(passage_rows, key=lambda row: _year_order(row, sort))
        remaining = [row for row in passage_rows if after is None or _year_order(row, sort) > after]
    page = remaining[:limit]
    next_cursor = None
    if len(remaining) > len(page) and page:
        next_cursor = signing.dumps({"id": str(session.id), "offset": page[-1]["_position"] + 1,
                                     "order": order, "sort": sort,
                                     **({"after": _year_order(page[-1], sort), "generation": session.generation}
                                        if sort != "relevance" else {})}, salt=CURSOR_SALT)
    removed = any(len(visible[channel]) < len((session.results or {}).get(channel, [])) for channel in CHANNELS)
    deep_removed = len(deep_visible) < len((session.results or {}).get(DEEP_RESULTS_KEY, []))
    warnings = list(session.warnings or [])
    if removed or deep_removed:
        warnings.append(_warning("sources_changed", "部分来源已更新、撤回或不再可访问，本次结果已移除；可重新检索最新资料。"))
    counts = {channel: len(visible[channel]) for channel in CHANNELS}
    counts["passages"] = len(passage_rows)
    # No cached corpus totals are returned after permissions change.
    from catalog.services.discovery_projection import discovery_coverage
    coverage = discovery_coverage(access_statuses, filters=effective_filters(session))
    coverage = {**coverage, "message": coverage.get("notice") or (
        f"当前权限与筛选范围内有 {coverage.get('published_editions', 0)} 份已公开书目，"
        f"其中 {coverage.get('eligible_editions', 0)} 份具备全文检索资格，"
        f"{coverage.get('text_pending_editions', 0)} 份文档的正文尚未就绪，"
        f"{coverage.get('bibliographic_editions', 0)} 份为纯书目记录。关键词与向量覆盖分别统计。")}
    identity = (session.versions or {}).get("_identity", {})
    identity = identity if isinstance(identity, dict) else {}
    return {
        "id": str(session.id), "query": session.query, "original_query": session.query,
        "documents": document_payload(session, access_statuses, passage_rows),
        "status": session.status, "mode": "expanded" if session.expansion_count else "standard",
        "can_retry": session.status in {"failed", "partial", "canceled"},
        "task_progress": {
            "id": str(session.pk), "generation": session.generation, "status": session.status,
            "terminal": session.status not in ACTIVE,
            "stage": next((key for key, value in session.channels.items() if value.get("status") == "running"), session.status),
            "completed": sum(value.get("status") in {"completed", "degraded", "partial", "failed", "disabled", "skipped"}
                             for value in session.channels.values()),
            "total": len(CHANNELS) + int(DEEP_CHANNEL in session.channels), "unit": "channels",
            "retryable": session.status in {"failed", "partial", "canceled"},
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "updated_at": session.updated_at.isoformat(),
            "finished_at": session.finished_at.isoformat() if session.finished_at else None,
            "deep": deep,
        },
        "expansion_count": session.expansion_count, "generation": session.generation,
        "filters": session.filters, "pipeline_version": PIPELINE_VERSION,
        "retrieval_identity": {
            "index_generation": str(identity.get("index_generation") or ""),
            "index_uid": str(identity.get("index_uid") or ""),
            "embedding_artifact": str(identity.get("embedding_artifact") or ""),
            "embedding_dimensions": identity.get("embedding_dimensions"),
            "reranker_artifact": str(identity.get("reranker_artifact") or ""),
            "pipeline_version": PIPELINE_VERSION,
        },
        "corpus_version": ",".join((session.versions or {}).get("passages", [])),
        "knowledge_version": ",".join(dict.fromkeys([*(session.versions or {}).get("entities", []), *(session.versions or {}).get("curation", [])])),
        "passages": [_public_row(row) for row in page],
        "deep_passages": [_public_row(row) for row in deep_visible],
        "deep_stage": deep,
        "entities": [_public_row(row) for row in visible["entities"]],
        "curation": [_public_row(row) for row in visible["curation"]],
        "count": counts["passages"], "counts": counts, "next_cursor": next_cursor,
        "sort": sort, "added_count": sum(bool(row.get("is_new")) for row in passage_rows),
        "can_expand": session.status not in (*ACTIVE, "canceled") and session.expansion_count < 1,
        "completed_channels": [key for key, value in session.channels.items() if value.get("status") in {"completed", "degraded"}],
        "channels": session.channels, "coverage_summary": coverage, "warnings": warnings,
        "source_changed": removed or deep_removed or any(
            isinstance(value, list) and len(value) > 1
            for key, value in session.versions.items() if key != "_identity"
        ),
        "created_at": session.created_at.isoformat(), "expires_at": session.expires_at.isoformat(),
        "poll_after_ms": 1500 if session.status in ACTIVE else None,
        "notice": "原文材料来自当前可访问馆藏；知识与策展分别列出，不判断观点首创或学术立场。",
    }
