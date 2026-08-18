from __future__ import annotations

from collections.abc import Iterable, Iterator
from hashlib import sha256
import json
import logging
import re
import time
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from catalog.models import Asset, Edition, Page, PublicationState, Work
from common.ai_runtime import AICapability, runtime_profile
from common.concurrency import capacity_slot
from ingestion.services.ai_client import (
    AIClient,
    AIConfigurationError,
    AIProviderAuthError,
    AIProviderRateLimited,
    AIProviderTimeout,
    AIServiceError,
    AIServiceUnavailable,
    current_ai_configuration,
)

from .library_query import (
    LibraryQuery,
    LibraryQueryType,
    LibraryScopeError,
    build_library_query,
)
from .library_retrieval import LibraryEvidence, LibraryRetrievalResult, LibraryRetrievalService
from .models import LibraryConversation, LibraryMessage, LibraryMessageSource
from .prompting import LIBRARY_PROMPT_VERSION, library_system_prompt
from .runtime_profiles import active_library_runtime_summary
from .services import decrypt_private_text, encrypt_private_text


PROMPT_VERSION = LIBRARY_PROMPT_VERSION
MAX_QUESTION_CHARS = 4000
MAX_CONTEXT_CHARS = 9000
MAX_SOURCE_CHARS = 1200
MAX_HISTORY_MESSAGES = 8
CITATION_RE = re.compile(r"\[(S\d+)\]")
PARTIAL_CITATION_RE = re.compile(r"\[(?:S\d*)?$")
logger = logging.getLogger(__name__)


class LibraryAssistantError(RuntimeError):
    code = "library_assistant_error"


class LibraryAssistantUnavailable(LibraryAssistantError):
    code = "library_assistant_unavailable"


class LibraryEvidenceUnavailable(LibraryAssistantError):
    code = "library_evidence_unavailable"


def sse_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"


def assistant_status() -> dict:
    summary = active_library_runtime_summary()
    if not summary.get("configured"):
        return {
            **summary,
            "available": False,
            "status": "disabled" if not summary.get("enabled") else "not_configured",
            "detail": "管理员尚未配置独立的 Library QA runtime profile。",
        }
    try:
        config = current_ai_configuration(AICapability.LIBRARY_QA)
    except AIConfigurationError as exc:
        return {
            **summary,
            "configured": False,
            "available": False,
            "status": "invalid_profile",
            "detail": str(exc),
        }
    if not config.enabled:
        return {
            "configured": False,
            "available": False,
            "status": "disabled",
            **summary,
            "provider": "none",
            "detail": "管理员尚未启用问答模型服务。",
        }
    health = AIClient(config).health_check()
    if health.get("available"):
        return {
            "configured": True,
            "available": True,
            "status": "healthy",
            "profile_key": config.profile_key,
            "provider": config.provider,
            "model": config.model,
            "retrieval_profile": config.retrieval_profile,
            "detail": "问答模型服务可用。",
        }
    logger.warning(
        "Library assistant health check failed provider=%s status=%s",
        config.provider,
        health.get("status") or "unknown",
    )
    return {
        "configured": True,
        "available": False,
        "status": "down",
        "profile_key": config.profile_key,
        "provider": config.provider,
        "model": config.model,
        "retrieval_profile": config.retrieval_profile,
        "detail": "问答模型暂时不可用。已有会话和来源仍可查看。",
    }


def _bounded_text(value: object, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _source_context(
    sources: list[dict],
    *,
    max_chars: int = MAX_CONTEXT_CHARS,
) -> tuple[str, list[str]]:
    blocks = []
    included_keys = []
    used = 0
    for source in sources:
        authors = "、".join(str(item) for item in source.get("authors", []) if item)
        page = source.get("printed_label") or source.get("page_index") or "未标页"
        prefix = "\n".join(
            [
                f"SOURCE ID: [{source['source_key']}]",
                f"WORK: {source.get('title') or '未题名'}",
                f"AUTHOR: {authors or '未记录'}",
                f"PAGE: {page}",
                f"LANGUAGE: {source.get('language') or 'unknown'}",
                f"SECTION: {source.get('chapter_title') or source.get('section_title') or '未记录'}",
                "PASSAGE:",
            ]
        )
        separator = 2 if blocks else 0
        available = max_chars - used - len(prefix) - separator
        if available <= 40:
            break
        snippet = _bounded_text(source.get("snippet"), min(MAX_SOURCE_CHARS, available))
        snippet = CITATION_RE.sub("[摘录编号已移除]", snippet)
        if not snippet:
            continue
        block = f"{prefix}{snippet}"
        blocks.append(block)
        included_keys.append(str(source["source_key"]))
        used += len(block) + separator
    return "\n\n".join(blocks), included_keys


def _history_messages(
    conversation: LibraryConversation,
    *,
    exclude_message_id=None,
    max_chars: int = 6000,
) -> list[dict]:
    queryset = conversation.messages.filter(status=LibraryMessage.Status.COMPLETED)
    if exclude_message_id:
        queryset = queryset.exclude(pk=exclude_message_id)
    history_limit = int(
        getattr(settings, "LIBRARY_QA_MAX_HISTORY_MESSAGES", MAX_HISTORY_MESSAGES)
    )
    rows = list(queryset.order_by("-created_at")[:history_limit])
    rows.reverse()
    messages = []
    remaining = max(0, max_chars)
    for row in rows:
        text = decrypt_private_text(row.body_ciphertext)
        if not text:
            continue
        # Source keys are scoped to one answer.  Reusing an old [S1] token in
        # the next prompt could accidentally bind it to a different book.
        text = CITATION_RE.sub("", text)
        text = text[:remaining]
        if not text:
            break
        prefix = "[历史回答，仅作对话语境，不是馆藏证据] " if row.role == LibraryMessage.Role.ASSISTANT else ""
        messages.append({"role": row.role, "content": f"{prefix}{text}"})
        remaining -= len(text)
    return messages


def _valid_uuid(value: object) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return ""


def validated_source_rows(rows: list[dict]) -> list[dict]:
    """Discard stale or cross-linked search rows before they reach the model."""

    asset_ids = {_valid_uuid(row.get("asset_id")) for row in rows}
    asset_ids.discard("")
    assets = {
        str(asset.id): asset
        for asset in Asset.objects.select_related("edition__work").filter(
            id__in=asset_ids,
            edition__state=PublicationState.PUBLISHED,
            edition__is_primary=True,
            kind=Asset.Kind.NORMALIZED,
            status=Asset.Status.READY,
            is_current=True,
        )
    }
    page_ids = {_valid_uuid(row.get("page_id")) for row in rows}
    page_ids.discard("")
    pages = {
        str(page.id): page
        for page in Page.objects.filter(id__in=page_ids)
    }
    valid = []
    for row in rows:
        asset = assets.get(_valid_uuid(row.get("asset_id")))
        if asset is None:
            continue
        if _valid_uuid(row.get("edition_id")) != str(asset.edition_id):
            continue
        if _valid_uuid(row.get("work_id")) != str(asset.edition.work_id):
            continue
        page_id = _valid_uuid(row.get("page_id"))
        if page_id:
            page = pages.get(page_id)
            if page is None or page.asset_id != asset.id:
                continue
        valid.append(
            {
                **row,
                "asset_id": str(asset.id),
                "edition_id": str(asset.edition_id),
                "work_id": str(asset.edition.work_id),
                "title": _bounded_text(row.get("title"), 500) or asset.edition.work.title,
            }
        )
    return valid


def _build_messages_with_source_keys(
    *,
    conversation: LibraryConversation,
    question: str,
    sources: list[dict],
    assist_mode: str,
    exclude_message_id=None,
    library_query: LibraryQuery | None = None,
    max_input_chars: int | None = None,
) -> tuple[list[dict], list[str]]:
    if sources:
        evidence_instruction = (
            "你可以使用下方馆藏摘录。每一个由馆藏支持的事实，都必须紧邻标注真实来源编号，"
            "格式只能是 [S1]。不得虚构来源、页码、引文或书名。区分原文信息与自己的归纳。"
            "证据不足时明确说明，并建议读者打开来源核对上下文。"
        )
    else:
        evidence_instruction = (
            "本轮没有取得可用馆藏证据。不得凭一般知识伪装成馆藏回答，也不得生成来源编号。"
        )
    query_instruction = ""
    if library_query is not None:
        query_instruction = (
            f"\n本轮 query type: {library_query.query_type}. "
            f"原始问题必须保持为：{library_query.original_query}。"
            + (
                f"检索时解析的追问为：{library_query.resolved_query}。不得改变原问题含义。"
                if library_query.resolved_query != library_query.original_query
                else ""
            )
        )
    system = f"{library_system_prompt()}\n\n{evidence_instruction}{query_instruction}"
    max_input_chars = int(max_input_chars or getattr(settings, "AI_MAX_INPUT_CHARS", 16000))
    question_prefix = "读者问题："
    evidence_prefix = "\n\n仅可使用以下已编号馆藏摘录作为馆藏证据：\n"
    available_after_system = max(0, max_input_chars - len(system))
    source_reserve = (
        min(MAX_CONTEXT_CHARS, max(200, int(available_after_system * 0.55)))
        if sources
        else 0
    )
    question_budget = max(
        120,
        available_after_system - len(question_prefix) - source_reserve - len(evidence_prefix),
    )
    bounded_question = CITATION_RE.sub("[来源编号已移除]", question[:question_budget])
    user = f"{question_prefix}{bounded_question}"
    remaining = max(0, max_input_chars - len(system) - len(user))
    included_source_keys: list[str] = []
    if sources and remaining > len(evidence_prefix) + 40:
        context, included_source_keys = _source_context(
            sources,
            max_chars=min(MAX_CONTEXT_CHARS, remaining - len(evidence_prefix)),
        )
        if context:
            user += f"{evidence_prefix}{context}"
    history_budget = max(0, max_input_chars - len(system) - len(user))
    messages = [{"role": "system", "content": system}]
    messages.extend(
        _history_messages(
            conversation,
            exclude_message_id=exclude_message_id,
            max_chars=history_budget,
        )
    )
    messages.append({"role": "user", "content": user})
    return messages, included_source_keys


def build_messages(
    *,
    conversation: LibraryConversation,
    question: str,
    sources: list[dict],
    assist_mode: str,
    exclude_message_id=None,
    library_query: LibraryQuery | None = None,
    max_input_chars: int | None = None,
) -> list[dict]:
    messages, _ = _build_messages_with_source_keys(
        conversation=conversation,
        question=question,
        sources=sources,
        assist_mode=assist_mode,
        exclude_message_id=exclude_message_id,
        library_query=library_query,
        max_input_chars=max_input_chars,
    )
    return messages


def prepare_prompt_sources(
    *,
    conversation: LibraryConversation,
    question: str,
    sources: list[dict],
    assist_mode: str,
    library_query: LibraryQuery | None = None,
    max_input_chars: int | None = None,
) -> tuple[list[dict], list[dict]]:
    """Keep only evidence blocks that actually fit in the model prompt."""

    included_sources = list(sources)
    for _ in range(3):
        included_sources = [
            {**source, "source_key": f"S{index}"}
            for index, source in enumerate(included_sources, start=1)
        ]
        messages, included_keys = _build_messages_with_source_keys(
            conversation=conversation,
            question=question,
            sources=included_sources,
            assist_mode=assist_mode,
            library_query=library_query,
            max_input_chars=max_input_chars,
        )
        key_set = set(included_keys)
        fitted = [source for source in included_sources if source["source_key"] in key_set]
        if len(fitted) == len(included_sources):
            return fitted, messages
        included_sources = fitted
    messages, _ = _build_messages_with_source_keys(
        conversation=conversation,
        question=question,
        sources=included_sources,
        assist_mode=assist_mode,
        library_query=library_query,
        max_input_chars=max_input_chars,
    )
    return included_sources, messages


def persist_sources(message: LibraryMessage, rows: list[dict]) -> list[LibraryMessageSource]:
    if not rows:
        return []
    work_ids = {row.get("work_id") for row in rows if row.get("work_id")}
    edition_ids = {row.get("edition_id") for row in rows if row.get("edition_id")}
    asset_ids = {row.get("asset_id") for row in rows if row.get("asset_id")}
    works = {str(obj.id): obj for obj in Work.objects.filter(id__in=work_ids)}
    editions = {
        str(obj.id): obj
        for obj in Edition.objects.filter(id__in=edition_ids, state=PublicationState.PUBLISHED)
    }
    assets = {
        str(obj.id): obj
        for obj in Asset.objects.filter(
            id__in=asset_ids,
            edition__state=PublicationState.PUBLISHED,
            edition__is_primary=True,
            kind=Asset.Kind.NORMALIZED,
            status=Asset.Status.READY,
            is_current=True,
        )
    }
    page_ids = {row.get("page_id") for row in rows if row.get("page_id")}
    pages = {str(obj.id): obj for obj in Page.objects.filter(id__in=page_ids)}
    objects = []
    for row in rows:
        work = works.get(str(row.get("work_id")))
        edition = editions.get(str(row.get("edition_id")))
        asset = assets.get(str(row.get("asset_id")))
        # Re-check the complete public-reader relationship at persistence time.
        # Publication or rendition state may have changed after retrieval.
        if not (
            work
            and edition
            and asset
            and edition.is_primary
            and edition.work_id == work.id
            and asset.edition_id == edition.id
        ):
            continue
        page = pages.get(str(row.get("page_id") or ""))
        if page is None and row.get("page_index"):
            page = Page.objects.filter(
                asset=asset,
                index=row.get("page_index"),
            ).first()
        source_key = f"S{len(objects) + 1}"
        reader_url = _bounded_text(row.get("reader_url"), 1000)
        if not reader_url:
            passage = _bounded_text(row.get("document_id") or row.get("id"), 120)
            suffix = f"&passage={passage}" if passage else ""
            reader_url = f"/reader/{asset.id}?page={row.get('page_index') or 1}{suffix}"
        objects.append(
            LibraryMessageSource(
                message=message,
                source_key=source_key,
                ordinal=len(objects) + 1,
                work=work,
                edition=edition,
                asset=asset,
                page=page,
                source_chunk_id=_bounded_text(row.get("id"), 120),
                document_id=_bounded_text(row.get("document_id"), 64),
                title_snapshot=_bounded_text(row.get("title"), 500) or "未题名",
                authors_snapshot=[
                    _bounded_text(value, 240)
                    for value in row.get("authors", [])[:20]
                    if _bounded_text(value, 240)
                ],
                page_index=row.get("page_index") or None,
                printed_label=_bounded_text(row.get("printed_label"), 80),
                chapter_title=_bounded_text(
                    row.get("chapter_title") or row.get("section_title"),
                    500,
                ),
                passage_language=_bounded_text(row.get("language"), 16),
                reader_url_snapshot=reader_url,
                retrieval_provenance=(
                    row.get("retrieval_provenance")
                    if isinstance(row.get("retrieval_provenance"), dict)
                    else {}
                ),
                quote_ciphertext=encrypt_private_text(row.get("snippet", "")),
            )
        )
    return LibraryMessageSource.objects.bulk_create(objects)


def finalize_answer(
    *,
    answer: LibraryMessage,
    conversation: LibraryConversation,
    collected: list[str],
    valid_keys: set[str],
    status: str,
    error_code: str = "",
    error_message: str = "",
    require_citation: bool = False,
    usage_updates: dict | None = None,
) -> tuple[str, set[str]]:
    body = PARTIAL_CITATION_RE.sub("", "".join(collected).strip())
    cited = {match.group(1) for match in CITATION_RE.finditer(body)} & valid_keys
    usage = {**(answer.usage or {}), **(usage_updates or {})}
    if require_citation and valid_keys and status == LibraryMessage.Status.COMPLETED and not cited:
        body = _strict_no_evidence_answer("uncited_answer")
        error_code = "uncited_answer"
        usage["insufficient_evidence"] = True
        usage["insufficiency_reason"] = "model_returned_no_valid_citation"
    answer.status = status
    answer.error_code = error_code
    answer.error_message = error_message[:1000]
    answer.body_ciphertext = encrypt_private_text(body)
    answer.completed_at = timezone.now()
    answer.usage = usage
    answer.save(
        update_fields=[
            "status",
            "error_code",
            "error_message",
            "body_ciphertext",
            "completed_at",
            "usage",
            "updated_at",
        ]
    )
    if cited:
        answer.sources.filter(source_key__in=cited).update(cited=True)
    conversation.last_message_at = answer.completed_at
    conversation.save(update_fields=["last_message_at", "updated_at"])
    return body, cited


class LibraryAnswerStream:
    def __init__(self, messages: list[dict]):
        self.messages = messages
        self.runtime_info: dict = {}

    def __iter__(self):
        try:
            primary = current_ai_configuration(AICapability.LIBRARY_QA)
        except AIConfigurationError as exc:
            raise LibraryAssistantUnavailable(str(exc)) from exc
        if not primary.enabled:
            raise LibraryAssistantUnavailable("管理员尚未启用 Library QA runtime profile。")
        self.runtime_info = {
            "profile_key": primary.profile_key,
            "provider": primary.provider,
            "model": primary.model,
            "fallback_used": False,
            "usage": {},
        }
        emitted = False
        with capacity_slot(
            "library-question",
            limit=int(getattr(settings, "AI_LIBRARY_MAX_CONCURRENCY", 2)),
            timeout=int(primary.timeout) + 30,
        ) as acquired:
            if not acquired:
                raise LibraryAssistantUnavailable("问答服务当前繁忙，请稍后重试。")
            client = AIClient(primary)
            try:
                for text in client.stream(messages=self.messages):
                    emitted = True
                    yield text
                self.runtime_info["usage"] = dict(client.last_usage)
                return
            except AIServiceError:
                if emitted or not primary.fallback_profile_key:
                    raise
            fallback = current_ai_configuration(
                AICapability.LIBRARY_QA,
                primary.fallback_profile_key,
            )
            fallback_client = AIClient(fallback)
            self.runtime_info.update(
                {
                    "profile_key": fallback.profile_key,
                    "provider": fallback.provider,
                    "model": fallback.model,
                    "fallback_used": True,
                }
            )
            for text in fallback_client.stream(messages=self.messages):
                yield text
            self.runtime_info["usage"] = dict(fallback_client.last_usage)


def stream_library_answer(messages: list[dict]) -> LibraryAnswerStream:
    """Stream a library answer through the capability-selected AI runtime."""

    return LibraryAnswerStream(messages)


def _safe_citation_deltas(chunks: Iterable[str], valid_keys: set[str]) -> Iterator[str]:
    pending = ""
    for chunk in chunks:
        pending += str(chunk)
        partial = PARTIAL_CITATION_RE.search(pending)
        if partial:
            ready, pending = pending[: partial.start()], pending[partial.start() :]
        else:
            ready, pending = pending, ""
        if ready:
            yield CITATION_RE.sub(
                lambda match: match.group(0) if match.group(1) in valid_keys else "",
                ready,
            )
    if pending:
        yield CITATION_RE.sub(
            lambda match: match.group(0) if match.group(1) in valid_keys else "",
            pending,
        )


def _strict_no_evidence_answer(reason: str = "") -> str:
    if reason == "retrieval_failure":
        return "馆藏检索当前暂时不可用。已有会话不会丢失，请稍后重试。"
    if reason == "comparison_entities_unresolved":
        return "本次没有可靠识别出两个可比较的公开实体，因此不能生成比较结论。请写明双方的规范名称后再试。"
    if reason == "comparison_entity_coverage_incomplete":
        return "当前馆藏没有同时找到比较双方的足够原文，因此不能可靠完成比较。你可以查看已检索到的相关 passages，或缩小问题范围。"
    if reason == "quoted_phrase_not_found":
        return "当前馆藏没有找到这段引语的逐字原文。为避免把语义近似文本误作原句，本次不生成替代答案。"
    if reason == "legacy_retrieval_off":
        return "Ask Library 必须基于馆藏原文。此会话原先关闭了馆藏检索，请改用自动或始终检索后再提问。"
    if reason == "uncited_answer":
        return "模型没有给出可验证的馆藏引用，因此本次回答未被采用。你仍可查看本轮检索到的相关原文。"
    return (
        "当前馆藏中没有找到足以回答这个问题的原文证据。"
        "你可以换用更具体的概念、人物或著作名称后再试。"
    )


def _log_ask_result(
    *,
    answer: LibraryMessage,
    conversation: LibraryConversation,
    library_query: LibraryQuery,
    retrieval_result: LibraryRetrievalResult,
    provider_runtime: dict,
) -> None:
    provider_usage = provider_runtime.get("usage")
    if not isinstance(provider_usage, dict):
        provider_usage = {}
    persisted_evidence_count = (answer.usage or {}).get("persisted_evidence_count")
    if not isinstance(persisted_evidence_count, int):
        persisted_evidence_count = len(retrieval_result.evidence)
    logger.info(
        "Library ask request_id=%s user_id=%s role=%s profile=%s provider=%s model=%s "
        "query_type=%s scope=%s retrieval_ms=%s generation_ms=%s evidence_count=%s "
        "status=%s error_code=%s",
        answer.request_id,
        conversation.user_id,
        getattr(conversation.user, "role", ""),
        provider_runtime.get("profile_key") or answer.runtime_profile_key,
        provider_runtime.get("provider") or answer.model_provider,
        provider_runtime.get("model") or answer.model_name,
        library_query.query_type,
        library_query.scope.context,
        retrieval_result.metadata.get("latency_ms"),
        provider_usage.get("generation_latency_ms"),
        persisted_evidence_count,
        answer.status,
        answer.error_code,
    )


def _effective_evidence_status(
    *,
    library_query: LibraryQuery,
    retrieval_result: LibraryRetrievalResult,
    persisted_sources: list[LibraryMessageSource],
) -> tuple[bool, str]:
    if not retrieval_result.sufficient:
        return False, retrieval_result.insufficiency_reason or "no_library_evidence"
    if not persisted_sources:
        return False, "no_valid_public_evidence"
    if library_query.query_type == LibraryQueryType.COMPARISON:
        required_ids = {
            str(row.get("canonical_entity", {}).get("entity_id") or "")
            for row in library_query.entity_anchors[:2]
            if row.get("canonical_entity", {}).get("entity_id")
        }
        if len(required_ids) < 2:
            return False, "comparison_entities_unresolved"
        covered_ids = {
            str((source.retrieval_provenance or {}).get("coverage_entity_id") or "")
            for source in persisted_sources
        }
        if len(required_ids) >= 2 and not required_ids.issubset(covered_ids):
            return False, "comparison_entity_coverage_incomplete"
    return True, ""


def _stream_conversation_answer(
    *,
    conversation: LibraryConversation,
    question: str,
    assist_mode: str,
    retrieval_profile_override: str = "",
    debug: bool = False,
    scope: dict | None = None,
) -> Iterator[str]:
    question = str(question or "").strip()
    if not question:
        yield sse_event("error", {"code": "empty_question", "detail": "请输入问题。"})
        return
    if len(question) > MAX_QUESTION_CHARS:
        yield sse_event(
            "error",
            {"code": "question_too_long", "detail": f"问题不能超过 {MAX_QUESTION_CHARS} 个字符。"},
        )
        return

    try:
        runtime = runtime_profile(AICapability.LIBRARY_QA)
    except ValueError:
        runtime = None
    requested_profile = str(
        retrieval_profile_override
        or (runtime.retrieval_profile if runtime else "stable")
    ).strip().casefold()
    is_admin = getattr(conversation.user, "role", "") == "admin"
    if requested_profile == "experimental_v2" and not (is_admin and debug):
        yield sse_event(
            "error",
            {"code": "experimental_retrieval_forbidden", "detail": "experimental_v2 只允许管理员诊断。"},
        )
        return
    if requested_profile not in {"stable", "experimental_v2"}:
        yield sse_event("error", {"code": "invalid_retrieval_profile", "detail": "检索 profile 无效。"})
        return

    try:
        library_query, resolved_scope, lexicon_resolution = build_library_query(
            conversation=conversation,
            question=question,
            retrieval_profile=requested_profile,
            scope=scope,
            admin_visibility=bool(is_admin and debug),
        )
    except (ValueError, LibraryScopeError) as exc:
        yield sse_event("error", {"code": "invalid_scope", "detail": str(exc)})
        return

    retrieval_failed = False
    retrieval_error_category = ""
    if assist_mode == LibraryConversation.AssistMode.OFF:
        retrieval_result = LibraryRetrievalResult(
            evidence=(),
            sufficient=False,
            insufficiency_reason="legacy_retrieval_off",
            metadata={
                "retrieval_profile": requested_profile,
                "evidence_count": 0,
                "latency_ms": 0,
                "legacy_assist_off": True,
            },
        )
    else:
        try:
            retrieval_result = LibraryRetrievalService().retrieve(
                library_query=library_query,
                resolved_scope=resolved_scope,
            )
        except Exception as exc:  # Search internals remain server-side; failure is explicit to the reader.
            logger.exception(
                "Library retrieval failed request_scope=%s query_type=%s",
                library_query.scope.context,
                library_query.query_type,
            )
            retrieval_failed = True
            retrieval_error_category = "retrieval_failure"
            retrieval_result = LibraryRetrievalResult(
                evidence=(),
                sufficient=False,
                insufficiency_reason="retrieval_failure",
                metadata={
                    "retrieval_profile": requested_profile,
                    "evidence_count": 0,
                    "fallback_used": False,
                    "error_category": exc.__class__.__name__,
                },
            )

    sources = [
        {**row.source_row(), "source_key": f"S{index}"}
        for index, row in enumerate(retrieval_result.evidence, start=1)
    ]
    sources = validated_source_rows(sources)
    sources = [
        {**source, "source_key": f"S{index}"}
        for index, source in enumerate(sources, start=1)
    ]
    sources, model_messages = prepare_prompt_sources(
        conversation=conversation,
        question=question,
        sources=sources,
        assist_mode=assist_mode,
        library_query=library_query,
        max_input_chars=(runtime.max_input_chars if runtime else int(getattr(settings, "AI_MAX_INPUT_CHARS", 16000))),
    )

    plan_snapshot = {
        "implementation_version": library_query.implementation_version,
        "original_query_hash": sha256(
            library_query.original_query.encode("utf-8")
        ).hexdigest(),
        "resolved_query_hash": sha256(
            library_query.resolved_query.encode("utf-8")
        ).hexdigest(),
        "query_type": library_query.query_type,
        "language": library_query.language,
        "scope": library_query.scope.as_dict(),
        "entity_anchor_ids": [
            str(row.get("canonical_entity", {}).get("entity_id") or "")
            for row in library_query.entity_anchors
            if row.get("canonical_entity", {}).get("entity_id")
        ],
        "query_lexicon_revision": library_query.query_lexicon_revision,
        "retrieval_limits": library_query.retrieval_limits,
        "conversation_context": library_query.conversation_context,
    }

    with transaction.atomic():
        user_message = LibraryMessage.objects.create(
            conversation=conversation,
            role=LibraryMessage.Role.USER,
            body_ciphertext=encrypt_private_text(question),
            status=LibraryMessage.Status.COMPLETED,
            completed_at=timezone.now(),
        )
        answer = LibraryMessage.objects.create(
            conversation=conversation,
            role=LibraryMessage.Role.ASSISTANT,
            status=LibraryMessage.Status.STREAMING,
            retrieval_used=False,
            prompt_version=PROMPT_VERSION,
            model_provider=runtime.provider if runtime else "",
            model_name=runtime.model if runtime else "",
            runtime_profile_key=runtime.key if runtime else "",
            query_type=library_query.query_type,
            retrieval_profile=requested_profile,
            usage={
                "query_plan": plan_snapshot,
                "retrieval": retrieval_result.metadata,
                "insufficient_evidence": not retrieval_result.sufficient,
                "insufficiency_reason": retrieval_result.insufficiency_reason,
                "fallback_used": False,
            },
        )
        persisted_sources = persist_sources(answer, sources)
        effective_sufficient, effective_insufficiency_reason = _effective_evidence_status(
            library_query=library_query,
            retrieval_result=retrieval_result,
            persisted_sources=persisted_sources,
        )
        answer.retrieval_used = bool(persisted_sources)
        answer.usage = {
            **(answer.usage or {}),
            "insufficient_evidence": not effective_sufficient,
            "insufficiency_reason": effective_insufficiency_reason,
            "persisted_evidence_count": len(persisted_sources),
        }
        answer.save(update_fields=["retrieval_used", "usage", "updated_at"])
        if not conversation.title:
            conversation.title = question[:80]
        conversation.assist_mode = assist_mode
        conversation.last_message_at = user_message.created_at
        conversation.save(update_fields=["title", "assist_mode", "last_message_at", "updated_at"])

    if retrieval_failed:
        answer.error_code = "retrieval_failure"
        answer.save(update_fields=["error_code", "updated_at"])

    collected = []
    collected_chars = 0
    valid_keys = {source.source_key for source in persisted_sources}
    output_limit = int(getattr(settings, "AI_LIBRARY_MAX_OUTPUT_CHARS", 12000))
    provider_runtime = {
        "profile_key": runtime.key if runtime else "",
        "provider": runtime.provider if runtime else "",
        "model": runtime.model if runtime else "",
        "fallback_used": False,
        "usage": {},
    }
    try:
        yield sse_event(
            "meta",
            {
                "conversation_id": str(conversation.id),
                "message_id": str(answer.id),
                "retrieval_used": bool(persisted_sources),
                "source_count": len(persisted_sources),
                "evidence_count": len(persisted_sources),
                "retrieval_status": (
                    "failed"
                    if retrieval_failed
                    else "insufficient"
                    if not effective_sufficient
                    else "ready"
                ),
                "query_type": library_query.query_type,
                "scope": library_query.scope.as_dict(),
                "retrieval_profile": requested_profile,
                **(
                    {
                        "debug": {
                            "normalized_query": library_query.normalized_query,
                            "resolved_query": library_query.resolved_query,
                            "entity_anchors": list(library_query.entity_anchors),
                            "retrieval": retrieval_result.metadata,
                            "query_lexicon": lexicon_resolution,
                        }
                    }
                    if debug and is_admin
                    else {}
                ),
            },
        )
        if not effective_sufficient:
            deltas: Iterable[str] = [
                _strict_no_evidence_answer(effective_insufficiency_reason)
            ]
        else:
            if runtime is None or not runtime.enabled:
                raise LibraryAssistantUnavailable(
                    "管理员尚未启用独立的 Library QA runtime profile。"
                )
            deltas = stream_library_answer(model_messages)
        for delta in _safe_citation_deltas(deltas, valid_keys):
            if not delta:
                continue
            if LibraryMessage.objects.filter(pk=answer.pk, cancel_requested_at__isnull=False).exists():
                answer.status = LibraryMessage.Status.CANCELED
                answer.error_code = "canceled"
                break
            remaining = output_limit - collected_chars
            if remaining <= 0:
                break
            if len(delta) > remaining:
                delta = delta[:remaining]
            collected.append(delta)
            collected_chars += len(delta)
            yield sse_event("delta", {"text": delta})
        if hasattr(deltas, "runtime_info"):
            provider_runtime = dict(getattr(deltas, "runtime_info") or provider_runtime)
            answer.model_provider = str(provider_runtime.get("provider") or (runtime.provider if runtime else ""))
            answer.model_name = str(provider_runtime.get("model") or (runtime.model if runtime else ""))
            answer.runtime_profile_key = str(provider_runtime.get("profile_key") or (runtime.key if runtime else ""))
            answer.save(
                update_fields=[
                    "model_provider",
                    "model_name",
                    "runtime_profile_key",
                    "updated_at",
                ]
            )
        cancel_requested = LibraryMessage.objects.filter(
            pk=answer.pk,
            cancel_requested_at__isnull=False,
        ).exists()
        final_status = (
            LibraryMessage.Status.CANCELED
            if answer.status == LibraryMessage.Status.CANCELED or cancel_requested
            else LibraryMessage.Status.COMPLETED
        )
        _, cited = finalize_answer(
            answer=answer,
            conversation=conversation,
            collected=collected,
            valid_keys=valid_keys,
            status=final_status,
            error_code=answer.error_code,
            require_citation=effective_sufficient,
            usage_updates={
                "provider": {
                    "profile_key": provider_runtime.get("profile_key"),
                    "provider": provider_runtime.get("provider"),
                    "model": provider_runtime.get("model"),
                    "fallback_used": bool(provider_runtime.get("fallback_used")),
                    "usage": provider_runtime.get("usage") or {},
                },
                "retrieval_error_category": retrieval_error_category,
            },
        )
        evidence_payload = [
            {
                "id": str(source.id),
                "source_key": source.source_key,
                "title": source.title_snapshot,
                "page_index": source.page_index,
                "printed_label": source.printed_label,
                "passage_language": source.passage_language,
                "document_id": source.document_id,
                "reader_url": source.reader_url_snapshot,
                "cited": source.source_key in cited,
            }
            for source in persisted_sources
        ]
        yield sse_event(
            "sources",
            {
                "message_id": str(answer.id),
                "count": len(cited),
                "citation_ids": sorted(cited),
                "evidence_count": len(persisted_sources),
                "evidence": evidence_payload,
            },
        )
        answer.refresh_from_db(fields=["usage", "status", "error_code"])
        _log_ask_result(
            answer=answer,
            conversation=conversation,
            library_query=library_query,
            retrieval_result=retrieval_result,
            provider_runtime=provider_runtime,
        )
        yield sse_event(
            "done",
            {
                "message_id": str(answer.id),
                "status": answer.status,
                "insufficient_evidence": bool((answer.usage or {}).get("insufficient_evidence")),
                "fallback_used": bool(provider_runtime.get("fallback_used")),
                "error_code": answer.error_code,
            },
        )
    except GeneratorExit:
        finalize_answer(
            answer=answer,
            conversation=conversation,
            collected=collected,
            valid_keys=valid_keys,
            status=LibraryMessage.Status.CANCELED,
            error_code="client_disconnected",
        )
        raise
    except (LibraryAssistantError, AIServiceError) as exc:
        error_code = getattr(exc, "code", "library_assistant_unavailable")
        finalize_answer(
            answer=answer,
            conversation=conversation,
            collected=collected,
            valid_keys=valid_keys,
            status=LibraryMessage.Status.FAILED,
            error_code=error_code,
            error_message=str(exc),
        )
        _log_ask_result(
            answer=answer,
            conversation=conversation,
            library_query=library_query,
            retrieval_result=retrieval_result,
            provider_runtime=provider_runtime,
        )
        yield sse_event(
            "error",
            {
                "code": error_code,
                "detail": "问答模型当前不可用。馆藏检索和在线阅读仍可正常使用。",
                "message_id": str(answer.id),
            },
        )
    except Exception as exc:
        logger.exception("Library question streaming failed")
        finalize_answer(
            answer=answer,
            conversation=conversation,
            collected=collected,
            valid_keys=valid_keys,
            status=LibraryMessage.Status.FAILED,
            error_code="library_assistant_error",
            error_message=str(exc),
        )
        _log_ask_result(
            answer=answer,
            conversation=conversation,
            library_query=library_query,
            retrieval_result=retrieval_result,
            provider_runtime=provider_runtime,
        )
        yield sse_event(
            "error",
            {
                "code": "library_assistant_error",
                "detail": "回答生成中断。已保留当前会话，你可以稍后重试。",
                "message_id": str(answer.id),
            },
        )


def source_is_available(source: LibraryMessageSource) -> bool:
    return bool(
        source.work_id
        and source.asset_id
        and source.edition_id
        and source.edition
        and source.edition.state == PublicationState.PUBLISHED
        and source.edition.is_primary
        and source.edition.work_id == source.work_id
        and source.asset
        and source.asset.edition_id == source.edition_id
        and source.asset.kind == Asset.Kind.NORMALIZED
        and source.asset.status == Asset.Status.READY
        and source.asset.is_current
        and (not source.page_id or source.page.asset_id == source.asset_id)
    )


def stream_conversation_answer(
    *,
    conversation: LibraryConversation,
    question: str,
    assist_mode: str,
    retrieval_profile_override: str = "",
    debug: bool = False,
    scope: dict | None = None,
) -> Iterator[str]:
    """Serialize generation within one conversation without terminating workers."""

    timeout = int(getattr(settings, "AI_TIMEOUT", 60)) + 90
    with capacity_slot(
        f"library-conversation-{conversation.id}",
        limit=1,
        timeout=timeout,
    ) as acquired:
        if not acquired:
            yield sse_event(
                "error",
                {
                    "code": "conversation_busy",
                    "detail": "这个会话正在生成另一条回答，请等待完成后再继续提问。",
                },
            )
            return
        yield from _stream_conversation_answer(
            conversation=conversation,
            question=question,
            assist_mode=assist_mode,
            retrieval_profile_override=retrieval_profile_override,
            debug=debug,
            scope=scope,
        )
