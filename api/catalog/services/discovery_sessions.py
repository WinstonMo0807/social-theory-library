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
from django.utils import timezone
from rest_framework.exceptions import NotFound, Throttled, ValidationError

from catalog.discovery_models import DiscoverySearchSession
from catalog.services.semantic_search import viewer_access_statuses
from common.concurrency import capacity_slot

logger = logging.getLogger(__name__)
CHANNELS = ("passages", "entities", "curation")
PIPELINE_VERSION = "discovery-3.0.8-1"
CURSOR_SALT = "catalog.discovery.cursor.v1"
ACTIVE = ("queued", "running")
MAX_MATERIALIZED = 400


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
        "theories": "theories", "topics": "topics",
    }
    output: dict = {}
    for key, value in raw.items():
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
    source_types = output.pop("source_types", [])
    mapping = {"book": ["book"], "journal": ["journal_article", "journal_issue"], "other": ["thesis", "report"]}
    if any(value not in mapping for value in source_types):
        raise ValidationError({"source_type": "材料类型无效。"})
    if source_types:
        output["document_types"] = list(dict.fromkeys([
            *output.get("document_types", []), *(kind for value in source_types for kind in mapping[value])]))
    if output.get("document_types"):
        output["document_types"] = ["journal_article" if value == "article" else value for value in output["document_types"]]
        if any(value not in {"book", "journal_article", "journal_issue", "thesis", "report"} for value in output["document_types"]):
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
        DiscoverySearchSession.objects.filter(pk=session_id, generation=generation, task_id=task_id, status="queued").update(
            status="failed", finished_at=timezone.now(),
            warnings=[_warning("queue_unavailable", "检索任务未能进入队列，请稍后重新检索。")])


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
    active = DiscoverySearchSession.objects.filter(status__in=ACTIVE, expires_at__gt=now)
    if active.count() >= max(2, int(getattr(settings, "DISCOVERY_MAX_QUEUED_QUERIES", 12))):
        raise Throttled(wait=10, detail="馆内检索任务正在处理，请稍后重试。")
    if owner and active.filter(owner=owner).count() >= 2:
        raise Throttled(wait=5, detail="请先等待或取消当前检索。")
    token = secrets.token_urlsafe(32)
    task_id = str(uuid4())
    with transaction.atomic():
        session = DiscoverySearchSession.objects.create(
            owner=owner, token_hash=_token_hash(token), query=query, filters=filters,
            access_statuses=request_access(request), task_id=task_id,
            results={channel: [] for channel in CHANNELS},
            channels={channel: {"status": "pending"} for channel in CHANNELS},
            expires_at=now + timedelta(hours=24))
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
    stale_after = timedelta(minutes=15 if session.status == "running" else 30)
    if session.status in ACTIVE and session.updated_at < timezone.now() - stale_after:
        DiscoverySearchSession.objects.filter(pk=session.id, status__in=ACTIVE,
                                               generation=session.generation).update(
            status="failed", finished_at=timezone.now(),
            warnings=[*session.warnings, _warning("task_timeout", "检索任务超时，已保留找到的材料，可重新检索。")])
        session.refresh_from_db()
    return session


def session_access(session: DiscoverySearchSession, request) -> list[str]:
    # Signing in or acquiring staff privileges must not widen an old session.
    return sorted(set(session.access_statuses).intersection(request_access(request)))


def expand_session(session: DiscoverySearchSession, access_statuses=None) -> DiscoverySearchSession:
    with transaction.atomic():
        session = DiscoverySearchSession.objects.select_for_update().get(pk=session.pk)
        if session.expires_at <= timezone.now():
            raise NotFound("检索记录已过期，请重新检索。")
        if session.status in ACTIVE:
            raise ValidationError({"detail": "当前检索尚在进行，请等待完成后扩大范围。"})
        if session.status == "canceled":
            raise ValidationError({"detail": "已取消的检索不能继续，请重新检索。"})
        if session.expansion_count >= 1:
            raise ValidationError({"detail": "本次检索已使用扩展预算，可调整问题后重新检索。"})
        session.expansion_count += 1
        session.generation += 1
        session.status = "queued"
        session.task_id = str(uuid4())
        session.finished_at = None
        session.channels = {channel: {"status": "pending"} for channel in CHANNELS}
        if access_statuses is not None:
            session.access_statuses = sorted(set(session.access_statuses).intersection(access_statuses))
        session.save(update_fields=["expansion_count", "generation", "status", "task_id", "finished_at", "channels", "access_statuses", "updated_at"])
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
            session.save(update_fields=["status", "finished_at", "generation", "updated_at"])
    # Cooperative cancellation avoids terminating a shared worker or indexing.
    return session


def _identity(row: dict) -> str:
    return str(row.get("id") or "")


def _reference(row: dict) -> dict:
    return {"id": _identity(row), "source_revision": str(row.get("source_revision") or ""),
            "match_basis": [str(item)[:160] for item in row.get("match_basis", [])[:5]]}


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
        page = row.get("pdf_page") or metadata.get("pdf_page") or metadata.get("page_number")
        if isinstance(start, int) and isinstance(end, int) and end > start:
            duplicate = False
            for prior in output:
                old = prior.get("metadata") or {}
                other_start = prior.get("start_offset", old.get("start_offset"))
                other_end = prior.get("end_offset", old.get("end_offset"))
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


def _diverse_prefix(rows: list[dict]) -> list[dict]:
    # Limit repetition only within the first six ranks, allowing two highly
    # ranked passages per work. Deferred hits remain available in later pages.
    counts, prefix, deferred = Counter(), [], []
    for row in rows:
        work = row.get("work") or (row.get("metadata") or {}).get("work") or {}
        work_id = str(work.get("id") or row.get("work_id") or _identity(row))
        if len(prefix) < 6 and counts[work_id] < 2:
            prefix.append(row)
            counts[work_id] += 1
        else:
            deferred.append(row)
    return prefix + deferred


def _rerank(query: str, rows: list[dict], limit: int, expected_artifact: str) -> tuple[list[dict], list[dict]]:
    if not rows:
        return rows, []
    from catalog.services.discovery_inference import DiscoveryInferenceError, rerank
    candidates = rows[:limit]
    try:
        if not expected_artifact:
            raise DiscoveryInferenceError("artifact_missing", "当前索引未固定重排模型版本。")
        ranked = rerank(query, [str(row.get("excerpt") or row.get("text") or "") for row in candidates],
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


def execute_session(session_id, generation: int, task_id: str) -> None:
    from catalog.services.discovery_projection import discovery_candidates, validate_discovery_results
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
    retrieval_context: dict = {}
    channel_states = {}
    for channel in ("entities", "curation", "passages"):
        if not _task_current(session_id, generation, task_id):
            return
        cap = (300 if expanded else 100) if channel == "passages" else (40 if expanded else 16)
        warnings = []
        try:
            result = discovery_candidates(session.query, channel, session.filters,
                                          session.access_statuses, limit=cap, expanded=expanded,
                                          request_context=retrieval_context)
            branches = [(result.get("sparse", []), 1.0), (result.get("dense", []), 1.0)]
            warnings.extend(result.get("warnings", []))
            if channel == "passages" and expanded and aliases:
                # Original full-corpus channels retain dominant total weight.
                for alias in aliases[:4]:
                    if not _task_current(session_id, generation, task_id):
                        return
                    branch = discovery_candidates(alias, channel, session.filters,
                                                  session.access_statuses, limit=40, expanded=True,
                                                  request_context=retrieval_context)
                    branches.extend([(branch.get("sparse", []), 0.2 / len(aliases[:4])),
                                     (branch.get("dense", []), 0.2 / len(aliases[:4]))])
                    warnings.extend(branch.get("warnings", []))
            rows = _rrf(branches)[:MAX_MATERIALIZED]
            rows = validate_discovery_results(channel, rows, session.access_statuses)
            if channel == "entities":
                for row in rows[:6]:
                    for alias in row.get("aliases") or (row.get("metadata") or {}).get("aliases") or []:
                        value = str(alias).strip()
                        if 2 <= len(value) <= 120 and value != session.query and value not in aliases:
                            aliases.append(value)
                aliases = aliases[:6]
            if channel == "passages":
                rows = _deduplicate(rows)
                if not _task_current(session_id, generation, task_id):
                    return
                rows, rerank_warnings = _rerank(session.query, rows, 40 if expanded else 20,
                                              str(result.get("reranker_artifact") or ""))
                warnings.extend(rerank_warnings)
                rows = _diverse_prefix(rows)
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
            current.channels = {**current.channels, channel: channel_state}
            versions = list((current.versions or {}).get(channel) or [])
            if version and version not in versions:
                versions.append(version)
            current.versions = {**current.versions, channel: versions}
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
    DiscoverySearchSession.objects.filter(pk=session_id, generation=generation, task_id=task_id,
                                          status__in=ACTIVE).update(status=terminal, finished_at=timezone.now(),
                                                                   updated_at=timezone.now())


def fail_session(session_id, generation: int, task_id: str, code="task_failed") -> None:
    DiscoverySearchSession.objects.filter(pk=session_id, generation=generation, task_id=task_id,
                                          status__in=ACTIVE).update(
        status="failed", finished_at=timezone.now(), updated_at=timezone.now(),
        warnings=[_warning(code, "检索任务未能完成，已保留找到的材料，可重新检索。")])


def _rehydrate(session, access_statuses) -> dict[str, list[dict]]:
    from catalog.services.discovery_projection import validate_discovery_results
    output = {}
    for channel in CHANNELS:
        refs = (session.results or {}).get(channel, [])[:MAX_MATERIALIZED]
        fresh = validate_discovery_results(channel, refs, access_statuses)
        by_id = {(_identity(row), str(row.get("source_revision") or "")): row for row in fresh}
        output[channel] = []
        for position, ref in enumerate(refs):
            row = by_id.get((_identity(ref), str(ref.get("source_revision") or "")))
            if row is not None:
                row = dict(row)
                row["_position"] = position
                row["match_basis"] = ref.get("match_basis") or row.get("match_basis") or []
                output[channel].append(row)
    return output


def _public_row(row: dict) -> dict:
    # Projection diagnostics, access filters and ranking scores are never part
    # of a public card. Their existence must not expand the response contract.
    allowed = {"id", "title", "excerpt", "text", "url", "reader_url", "source_kind", "source_label",
               "source_title", "recommendation_excerpt", "source_revision", "portrait_url", "kind",
               "linked_work_ids", "match_basis", "pdf_page", "page_number", "printed_page", "asset_id",
               "edition_id", "work_id", "document_revision_id", "evidence_span_id", "passage_id",
               "work", "authors", "locator_precision", "context_reference"}
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


def serialize_session(session, access_statuses, *, cursor="", limit=3) -> dict:
    offset = 0
    if cursor:
        try:
            signed = signing.loads(cursor, salt=CURSOR_SALT, max_age=24 * 60 * 60)
            if signed.get("id") != str(session.id):
                raise ValueError("wrong session")
            offset = int(signed["offset"])
            if not 0 <= offset <= MAX_MATERIALIZED:
                raise ValueError("bad offset")
        except (signing.BadSignature, ValueError, TypeError, KeyError):
            raise ValidationError({"cursor": "分页位置无效或已过期，请重新检索。"})
    limit = max(1, min(int(limit), MAX_MATERIALIZED))
    visible = _rehydrate(session, access_statuses)
    remaining = [row for row in visible["passages"] if row["_position"] >= offset]
    page = remaining[:limit]
    next_cursor = None
    if len(remaining) > len(page) and page:
        next_cursor = signing.dumps({"id": str(session.id), "offset": page[-1]["_position"] + 1}, salt=CURSOR_SALT)
    removed = any(len(visible[channel]) < len((session.results or {}).get(channel, [])) for channel in CHANNELS)
    warnings = list(session.warnings or [])
    if removed:
        warnings.append(_warning("sources_changed", "部分来源已更新、撤回或不再可访问，本次结果已移除；可重新检索最新资料。"))
    counts = {channel: len(visible[channel]) for channel in CHANNELS}
    # No cached corpus totals are returned after permissions change.
    from catalog.services.discovery_projection import discovery_coverage
    coverage = discovery_coverage(access_statuses, filters=session.filters)
    coverage = {**coverage, "message": (f"当前权限与筛选范围内，有 {coverage.get('eligible_editions', 0)} 份文献具备正文公开资格。"
                            "关键词与向量覆盖分别统计；这不是全部可阅读馆藏的数量。")}
    return {
        "id": str(session.id), "query": session.query, "original_query": session.query,
        "status": session.status, "mode": "expanded" if session.expansion_count else "standard",
        "expansion_count": session.expansion_count, "generation": session.generation,
        "filters": session.filters, "pipeline_version": PIPELINE_VERSION,
        "corpus_version": ",".join((session.versions or {}).get("passages", [])),
        "knowledge_version": ",".join(dict.fromkeys([*(session.versions or {}).get("entities", []), *(session.versions or {}).get("curation", [])])),
        "passages": [_public_row(row) for row in page],
        "entities": [_public_row(row) for row in visible["entities"]],
        "curation": [_public_row(row) for row in visible["curation"]],
        "count": counts["passages"], "counts": counts, "next_cursor": next_cursor,
        "can_expand": session.status not in (*ACTIVE, "canceled") and session.expansion_count < 1,
        "completed_channels": [key for key, value in session.channels.items() if value.get("status") in {"completed", "degraded"}],
        "channels": session.channels, "coverage_summary": coverage, "warnings": warnings,
        "source_changed": removed or any(len(value) > 1 for value in session.versions.values()),
        "created_at": session.created_at.isoformat(), "expires_at": session.expires_at.isoformat(),
        "poll_after_ms": 1500 if session.status in ACTIVE else None,
        "notice": "原文材料来自当前可访问馆藏；知识与策展分别列出，不判断观点首创或学术立场。",
    }
