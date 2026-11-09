"""Evidence-bound Library Synthesis candidates.

This module schedules derived editorial suggestions without writing canonical
knowledge.  A model receives an immutable EvidencePack and its output becomes
an ordinary MetadataCandidate that still requires an explicit editor action.
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Iterable

from django.db import transaction

from catalog.models import (
    CapabilityDemand,
    DocumentRevision,
    EvidencePack,
    EvidenceSpan,
)
from catalog.services.evidence_envelope import evidence_span_envelope
from catalog.services.research.evidence_pack import create_evidence_pack
from catalog.services.research.prompt_registry import resolve_prompt
from catalog.services.research.task_profiles import resolve_task_profile
from common.task_runtime import queue_or_wait
from ingestion.models import CandidateEvidence, MetadataCandidate, UploadItem
from ingestion.services.candidate_store import persist_metadata_candidates
from ingestion.services.metadata import Candidate


LIBRARY_SYNTHESIS_VERSION = "library-synthesis-v1"
LIBRARY_SYNTHESIS_PROMPT_KEY = "research.library_synthesis"
LIBRARY_SYNTHESIS_FIELDS = frozenset(
    {
        "abstract",
        "core_viewpoints",
        "major_criticisms",
        "major_responses",
        "editorial_summary",
    }
)
MAX_SYNTHESIS_EVIDENCE = 12
MAX_SYNTHESIS_INPUT_CHARS = 24_000

CODE_PROMPT = (
    "你是馆藏证据综合助手。只能使用 EvidencePack 中给出的馆藏原文，不得补充训练知识、"
    "外部事实或没有页码的判断。生成一个简洁、可编辑的候选，并列出实际使用的 "
    "EvidenceSpan id。证据不足时返回空 value。"
)


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def resolve_library_synthesis_prompt() -> dict[str, Any]:
    profile = resolve_task_profile("library_synthesis")
    stored = resolve_prompt(key=LIBRARY_SYNTHESIS_PROMPT_KEY)
    content = str(stored.content if stored else CODE_PROMPT)
    schema = dict(stored.output_schema if stored and stored.output_schema else profile["output_schema"])
    return {
        "key": LIBRARY_SYNTHESIS_PROMPT_KEY,
        "version": str(stored.version if stored else LIBRARY_SYNTHESIS_VERSION),
        "content": content,
        "schema": schema,
        "content_hash": sha256(content.encode("utf-8")).hexdigest(),
        "schema_hash": sha256(_stable_json(schema).encode("utf-8")).hexdigest(),
        "registry_id": str(stored.id) if stored else "",
        "registry_version": stored.version if stored else None,
        "source": "prompt_registry" if stored else "code_baseline",
    }


def _span_score(span: EvidenceSpan, *, field_name: str) -> tuple[float, int, int]:
    section = str(span.section or "").casefold()
    text = str(span.normalized_text or span.original_text or "")
    section_bonus = 0.0
    if any(token in section for token in ("摘要", "abstract", "导论", "introduction", "前言", "preface")):
        section_bonus = 0.45
    elif any(token in section for token in ("结论", "conclusion", "总结", "summary")):
        section_bonus = 0.35
    elif field_name != "abstract" and any(token in section for token in ("批评", "回应", "criticism", "response")):
        section_bonus = 0.35
    length_score = min(len(text), 1800) / 1800 * 0.15
    early_bonus = 0.12 if span.page_number <= 30 else 0
    return (float(span.quality or 0) + section_bonus + length_score + early_bonus, -span.page_number, -span.start_offset)


def build_library_synthesis_evidence_pack(
    revision: DocumentRevision,
    *,
    field_name: str = "abstract",
    research_run=None,
    actor=None,
) -> EvidencePack | None:
    """Retrieve a small, locator-backed collection-only EvidencePack."""

    if field_name not in LIBRARY_SYNTHESIS_FIELDS:
        raise ValueError("该字段不支持馆藏综合候选。")
    if not revision.is_active:
        return None
    pool = list(
        revision.evidence_spans.filter(is_stale=False)
        .select_related("document_revision__asset__edition__work", "page")
        .prefetch_related("document_revision__asset__edition__contributions__person")
        .order_by("page_number", "start_offset")[:400]
    )
    eligible = [
        span
        for span in pool
        if len(str(span.normalized_text or span.original_text or "").strip()) >= 80
        and float(span.quality or 0) >= 0.35
    ]
    ranked = sorted(
        eligible,
        key=lambda span: _span_score(span, field_name=field_name),
        reverse=True,
    )
    selected: list[EvidenceSpan] = []
    selected_ids: set[str] = set()
    total_chars = 0
    for span in ranked:
        text = str(span.original_text or "")
        if str(span.id) in selected_ids or total_chars + len(text) > MAX_SYNTHESIS_INPUT_CHARS:
            continue
        selected.append(span)
        selected_ids.add(str(span.id))
        total_chars += len(text)
        if len(selected) >= MAX_SYNTHESIS_EVIDENCE:
            break
    if len(selected) < 2:
        return None
    envelopes = [evidence_span_envelope(span).as_dict() for span in selected]
    return create_evidence_pack(
        task_profile=resolve_task_profile("library_synthesis"),
        envelopes=envelopes,
        retrieval_snapshot={
            "profile": "library_synthesis",
            "version": LIBRARY_SYNTHESIS_VERSION,
            "field_name": field_name,
            "evidence_span_ids": [str(span.id) for span in selected],
            "collection_only": True,
        },
        subject_type="work",
        subject_id=str(revision.asset.edition.work_id),
        research_run=research_run,
        actor=actor,
    )


def schedule_library_synthesis(
    evidence_pack: EvidencePack,
    *,
    upload_item: UploadItem,
    field_name: str = "abstract",
    priority: int = 0,
) -> dict[str, Any]:
    from catalog.services.knowledge_retirement import retired_result
    return retired_result()



def _pack_span_ids(pack: EvidencePack) -> set[str]:
    return {
        str(row.get("id") or "")
        for row in pack.envelope_snapshot
        if isinstance(row, dict) and str(row.get("id") or "")
    }


@transaction.atomic
def persist_library_synthesis_candidate(
    demand: CapabilityDemand,
    result: dict[str, Any],
    *,
    provider: str,
    model: str,
    model_revision: str,
) -> dict[str, Any]:
    from catalog.services.knowledge_retirement import MESSAGE
    raise ValueError(MESSAGE)
