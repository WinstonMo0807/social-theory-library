"""Read-only aggregation and bounded step research for the admin workflow.

The service presents the existing candidate models through one DTO.  It is
safe to call while a canonical draft is dirty because it never writes Work,
Edition or relations.  The optional research run is explicit and bounded; its
persisted field candidates still go through the existing FieldEnrichment
service and decision endpoints.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import date, datetime
import logging
import re
from typing import Any
from uuid import UUID, uuid4

from django.db.models import Q

from catalog.models import (
    Asset,
    Edition,
    EnrichmentCandidate,
    EnrichmentSourceClass,
    KnowledgeNode,
    QueryLexiconCandidate,
    SemanticChunk,
    TheoryReviewTask,
)
from catalog.services.field_enrichment import FieldEnrichmentRequest, FieldEnrichmentService
from catalog.services.field_enrichment.policies import FIELD_POLICIES
from catalog.services.field_enrichment.web import SafeWebFetcher, WebSearchError, configured_web_search_adapter
from catalog.services.query_lexicon.resolver import ADMIN_RESOLVABLE
from catalog.services.query_lexicon.search import resolve_search_query
from ingestion.models import EntityResolutionCandidate, MetadataCandidate, UploadItem

from .query_lexicon.registry import EntityKey, describe_entity
from .workflow_suggestion_policies import (
    SOURCE_PROFILES,
    SOURCE_PROFILE_VERSION,
    WORKFLOW_SUGGESTION_POLICIES,
    WORKFLOW_SUGGESTION_POLICY_VERSION,
    WorkflowSuggestionPolicy,
    policy_payload,
    source_profile_payload,
)


logger = logging.getLogger(__name__)

STEP_FIELD_ALIASES = {
    "work": ("title", "subtitle", "original_title", "uniform_title", "language", "original_language", "first_publication_date", "abstract"),
    "bibliography": ("version_label", "publication_year", "publisher", "publication_place", "isbn", "isbn10", "isbn13", "series", "extent", "responsibility_statement", "journal_title", "volume", "issue", "page_range", "doi", "degree_institution", "degree_type", "report_institution"),
    "contributors": ("contributors", "display_name", "person"),
    "classification": ("primary_disciplines", "related_disciplines", "subdisciplines", "disciplines"),
    "knowledge": ("relations", "theory", "topic", "knowledge_node"),
    "reader": ("reader_rendition_policy", "text_layer_status", "page_label_status", "semantic_index_status"),
    "curation": ("reading_path_placements", "recommendation_reason"),
    "publication": ("preflight",),
}

SOURCE_TIER_LABELS = {
    "in_library": "本馆正式条目",
    "query_lexicon": "QueryLexicon 匹配",
    "pdf_evidence": "当前 PDF / OCR",
    "structured_source": "结构化来源",
    "web_evidence": "联网学术来源",
    "research_lead": "联网研究线索",
}


def _json_value(value: Any) -> Any:
    if isinstance(value, (UUID, date, datetime)):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(row) for key, row in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(row) for row in value]
    return value


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return " ".join(_text(row) for row in (value.values() if isinstance(value, dict) else value))
    return str(value).strip()


def _supporting_excerpt(text: str, terms: list[str], *, limit: int = 900) -> str:
    compact = " ".join(str(text or "").split())
    if not compact:
        return ""
    folded = compact.casefold()
    positions = [folded.find(term.casefold()) for term in terms if term and folded.find(term.casefold()) >= 0]
    if not positions:
        return ""
    start = max(0, min(positions) - 260)
    return compact[start : start + limit]


def _step_for_metadata(field_name: str) -> str:
    field = str(field_name or "").strip()
    for step, fields in STEP_FIELD_ALIASES.items():
        if field in fields:
            return step
    if field in {"authors", "contributors"}:
        return "contributors"
    if field in {"theory_schools", "topics", "concepts", "knowledge_nodes"}:
        return "knowledge"
    if field in {"disciplines", "subdisciplines"}:
        return "classification"
    return "work"


def _metadata_tier(source: str) -> tuple[str, str, bool]:
    value = str(source or "").casefold()
    if any(token in value for token in ("pdf", "ocr", "grobid", "text_layer", "semantic")):
        return "pdf_evidence", "pdf", True
    return "in_library", "library", True


def _source_profile(source_class: str, *, structured: bool = False):
    if structured:
        return SOURCE_PROFILES.get("structured")
    return SOURCE_PROFILES.for_source_class(source_class)


def _evidence_payload(rows, *, limit: int = 8) -> list[dict[str, Any]]:
    output = []
    for row in list(rows)[:limit]:
        output.append(
            _json_value(
                {
                    "id": getattr(row, "id", None),
                    "canonical_url": getattr(row, "canonical_url", "") or getattr(row, "source_url", ""),
                    "source_title": getattr(row, "source_title", "") or getattr(row, "source", ""),
                    "source_class": getattr(row, "source_class", "") or getattr(row, "source_kind", ""),
                    "supporting_text": getattr(row, "supporting_text", "") or getattr(row, "text_quote", ""),
                    "page_number": getattr(row, "page_number", None),
                    "retrieved_at": getattr(row, "retrieved_at", None),
                }
            )
        )
    return output


def _dto(
    *,
    identifier: Any,
    step: str,
    field: str,
    kind: str,
    label: str,
    value: Any = None,
    source_tier: str,
    source_class: str = "",
    confidence: float = 0,
    reasons: list[str] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    current_value: Any = None,
    entity_type: str = "",
    entity_id: Any = None,
    decision_url: str = "",
    available_actions: list[str] | None = None,
    status: str = "pending",
    evidence_status: str = "",
) -> dict[str, Any]:
    profile = SOURCE_PROFILES.get("library") if source_tier == "in_library" else None
    if profile is None:
        profile = next((row for row in SOURCE_PROFILES.all() if row.tier == source_tier), SOURCE_PROFILES.get("general_web"))
    evidence_rows = evidence or []
    return {
        "id": str(identifier),
        "step": step,
        "field": field,
        "field_name": field,
        "kind": kind,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id else None,
        "label": label or _text(value) or "候选",
        "secondary_label": "",
        "value": _json_value(value),
        "proposed_value": _json_value(value),
        "current_value": _json_value(current_value),
        "source_tier": source_tier,
        "source_tier_label": SOURCE_TIER_LABELS.get(source_tier, source_tier),
        "source_class": source_class,
        "source": source_class or SOURCE_TIER_LABELS.get(source_tier, source_tier),
        "confidence": round(float(confidence or 0), 4),
        "reasons": list(reasons or []),
        "evidence_count": len(evidence_rows),
        "evidence_records": evidence_rows,
        "evidence": evidence_rows,
        "evidence_status": evidence_status or ("evidence" if profile.is_evidence else "lead_only"),
        "status": status,
        "review_state": status,
        "decision_url": decision_url or None,
        "available_actions": list(available_actions or ["inspect"]),
        "human_confirmation_required": True,
    }


class WorkflowSuggestionAggregator:
    """Combine local, lexicon, corpus and persisted web candidates for a Work."""

    def __init__(self, edition: Edition, *, item: UploadItem | None = None):
        self.edition = edition
        self.work = edition.work
        self.item = item

    def _metadata_rows(self, step: str | None, field: str | None) -> list[dict]:
        if self.item is None:
            return []
        queryset = MetadataCandidate.objects.filter(upload_item=self.item).prefetch_related("evidence_records")
        rows = []
        for candidate in queryset.order_by("field_name", "-confidence", "created_at")[:300]:
            candidate_step = _step_for_metadata(candidate.field_name)
            if step and candidate_step != step:
                continue
            if field and candidate.field_name not in {field, "contributors" if field in {"person", "display_name"} else field}:
                continue
            tier, source_class, is_evidence = _metadata_tier(candidate.source)
            evidence = _evidence_payload(candidate.evidence_records.all())
            rows.append(
                _dto(
                    identifier=candidate.id,
                    step=candidate_step,
                    field=candidate.field_name,
                    kind="metadata",
                    label=_text(candidate.value),
                    value=candidate.value,
                    source_tier=tier,
                    source_class=source_class,
                    confidence=candidate.confidence,
                    reasons=[f"MetadataCandidate · {candidate.source}"],
                    evidence=evidence,
                    status="pending" if candidate.lifecycle == MetadataCandidate.Lifecycle.PROPOSED else candidate.lifecycle,
                    decision_url=(
                        f"/ingestion/items/{self.item.id}/metadata-candidates/{candidate.id}/decision/"
                        if candidate.lifecycle == MetadataCandidate.Lifecycle.PROPOSED
                        else ""
                    ),
                    available_actions=["inspect", "reject"] if candidate.lifecycle == MetadataCandidate.Lifecycle.PROPOSED else ["inspect"],
                    evidence_status="evidence" if is_evidence else "lead_only",
                )
            )
        return rows

    def _entity_rows(self, step: str | None, field: str | None) -> list[dict]:
        if self.item is None:
            return []
        rows = []
        for candidate in EntityResolutionCandidate.objects.filter(upload_item=self.item).order_by("target_type", "source_name", "-match_score", "created_at")[:300]:
            candidate_field = "contributors" if candidate.target_type == "person" else candidate.target_type
            if step and step != "contributors" and candidate_field != step:
                continue
            if field and field not in {candidate_field, "contributors", "person", "display_name"}:
                continue
            evidence = [
                {
                    "match_reasons": candidate.match_reasons,
                    "conflicts": candidate.conflicts,
                    "preview": candidate.preview_data,
                    "supporting_properties": candidate.supporting_properties,
                }
            ]
            status = "pending" if candidate.status == EntityResolutionCandidate.Status.PROPOSED else candidate.status
            rows.append(
                _dto(
                    identifier=candidate.id,
                    step="contributors",
                    field="contributors",
                    kind="entity",
                    label=candidate.label,
                    value={"id": candidate.candidate_entity_id or None, "name": candidate.label},
                    source_tier="in_library",
                    source_class="entity_resolution",
                    confidence=candidate.match_score,
                    reasons=list(candidate.match_reasons or []) or ["实体消歧候选"],
                    evidence=evidence,
                    entity_type=candidate.candidate_entity_type,
                    entity_id=candidate.candidate_entity_id,
                    status=status,
                    decision_url=f"/ingestion/items/{self.item.id}/entity-resolution-candidates/{candidate.id}/decision/",
                    available_actions=(
                        ["inspect", "link_existing", "create_draft", "keep_unresolved", "reject"]
                        if candidate.status == EntityResolutionCandidate.Status.PROPOSED
                        else ["inspect"]
                    ),
                )
            )
        return rows

    def _enrichment_rows(self, step: str | None, field: str | None) -> list[dict]:
        queryset = EnrichmentCandidate.objects.filter(
            Q(target_type=EnrichmentCandidate.TargetType.WORK, target_id=self.work.id)
            | Q(target_type=EnrichmentCandidate.TargetType.EDITION, target_id=self.edition.id)
        ).prefetch_related("evidence_records")
        rows = []
        for candidate in queryset.order_by("field_name", "-confidence", "created_at")[:300]:
            candidate_step = "bibliography" if candidate.target_type == "edition" else "work"
            if candidate.field_name in {"discipline", "subdiscipline", "relation"}:
                candidate_step = "classification" if candidate.field_name != "relation" else "knowledge"
            if candidate.field_name == "item":
                candidate_step = "curation"
            display_field = (
                "related_disciplines"
                if candidate.field_name == "discipline"
                else "subdisciplines"
                if candidate.field_name == "subdiscipline"
                else "relations"
                if candidate.field_name == "relation"
                else candidate.field_name
            )
            if step and candidate_step != step:
                continue
            if field and display_field != field:
                continue
            current_evidence = list(candidate.evidence_records.filter(is_current=True)[:20])
            evidence = _evidence_payload(current_evidence)
            structured = bool(current_evidence) and all(
                row.extraction_method == "structured_provider" for row in current_evidence
            )
            profile = _source_profile(candidate.source_class, structured=structured)
            rows.append(
                _dto(
                    identifier=candidate.id,
                    step=candidate_step,
                    field=display_field,
                    kind="enrichment",
                    label=_text(candidate.proposed_value),
                    value=candidate.proposed_value,
                    source_tier=profile.tier,
                    source_class=candidate.source_class,
                    confidence=candidate.confidence,
                    reasons=["FieldPolicy 候选", f"身份状态：{candidate.identity_status}"],
                    evidence=evidence,
                    current_value=candidate.current_value,
                    status=candidate.status,
                    decision_url=f"/catalog/admin/field-enrichment/candidates/{candidate.id}/decision/",
                    available_actions=["inspect", "accept", "reject"] if candidate.status == EnrichmentCandidate.Status.PENDING else ["inspect"],
                    evidence_status="evidence" if profile.is_evidence else "lead_only",
                )
            )
        return rows

    def _theory_rows(self, step: str | None, field: str | None) -> list[dict]:
        if step and step != "knowledge":
            return []
        if field and field not in {"relations", "theory", "topic", "knowledge_node"}:
            return []
        rows = []
        for candidate in TheoryReviewTask.objects.filter(work=self.work).select_related("candidate_node").order_by("-confidence", "created_at")[:200]:
            label = candidate.suggested_node_name or (candidate.candidate_node.canonical_name_zh if candidate.candidate_node else "知识关系")
            evidence = [{"pages": candidate.evidence_pages, "supporting_text": candidate.evidence_text}] if candidate.evidence_text or candidate.evidence_pages else []
            rows.append(
                _dto(
                    identifier=candidate.id,
                    step="knowledge",
                    field="relations",
                    kind="relation",
                    label=label,
                    value={"target_id": str(candidate.candidate_node_id) if candidate.candidate_node_id else None, "name": label, "relation_type": candidate.suggested_relation_type},
                    source_tier="pdf_evidence",
                    source_class="theory_review",
                    confidence=candidate.confidence,
                    reasons=["TheoryReviewTask", "当前 PDF 证据"],
                    evidence=evidence,
                    entity_type="knowledge_node",
                    entity_id=candidate.candidate_node_id,
                    status="pending" if candidate.status in {TheoryReviewTask.TaskStatus.PENDING, TheoryReviewTask.TaskStatus.NEEDS_CHANGES, TheoryReviewTask.TaskStatus.INSUFFICIENT_EVIDENCE} else candidate.status,
                    available_actions=["inspect"],
                )
            )
        return rows

    def _query_lexicon_candidate_rows(self, step: str | None, field: str | None) -> list[dict]:
        if step and step not in {"contributors", "classification", "knowledge"}:
            return []
        queryset = QueryLexiconCandidate.objects.filter(
            evidence_records__work=self.work,
        ).prefetch_related("evidence_records").distinct().order_by("-confidence", "created_at")[:200]
        rows = []
        for candidate in queryset:
            candidate_step = "contributors" if candidate.target_entity_type == QueryLexiconCandidate.TargetEntityType.PERSON else "knowledge"
            candidate_field = "contributors" if candidate_step == "contributors" else "relations"
            if step and candidate_step != step:
                continue
            if field and field not in {candidate_field, "person", "theory", "knowledge_node"}:
                continue
            evidence = [
                _json_value(
                    {
                        "id": row.id,
                        "work_title": row.work.title,
                        "document_id": row.document_id,
                        "page_number": row.page_number,
                        "printed_page_label": row.printed_page_label,
                        "supporting_text": row.evidence_text,
                        "source_class": "pdf",
                    }
                )
                for row in candidate.evidence_records.filter(is_current=True)[:8]
            ]
            status = "pending" if candidate.status == QueryLexiconCandidate.Status.PENDING else candidate.status
            rows.append(
                _dto(
                    identifier=candidate.id,
                    step=candidate_step,
                    field=candidate_field,
                    kind="lexicon_candidate",
                    label=candidate.proposed_term,
                    value={
                        "id": str(candidate.target_entity_id) if candidate.target_entity_id else None,
                        "name": candidate.proposed_term,
                        "anchor_term": candidate.anchor_term,
                        "term_type": candidate.proposed_term_type,
                    },
                    source_tier="pdf_evidence",
                    source_class="query_lexicon_candidate",
                    confidence=candidate.confidence,
                    reasons=[
                        "PDF 术语候选",
                        f"解析状态：{candidate.linking_status}",
                        "接受后先写规范 alias，再由现有 QueryLexicon sync 生效",
                    ],
                    evidence=evidence,
                    entity_type=candidate.target_entity_type,
                    entity_id=candidate.target_entity_id,
                    status=status,
                    decision_url=f"/catalog/admin/candidate-review/query_lexicon/{candidate.id}/decision/",
                    available_actions=(
                        ["inspect", "accept", "reject"]
                        if candidate.status == QueryLexiconCandidate.Status.PENDING
                        and candidate.linking_status == QueryLexiconCandidate.LinkingStatus.LINKED
                        else ["inspect", "reject"]
                        if candidate.status == QueryLexiconCandidate.Status.PENDING
                        else ["inspect"]
                    ),
                    evidence_status="pdf_evidence",
                )
            )
        return rows

    def _query_lexicon_rows(self, step: str | None, field: str | None, query: str | None) -> list[dict]:
        policies = [row for row in WORKFLOW_SUGGESTION_POLICIES.all() if (not step or row.step == step) and row.query_lexicon_entity_types]
        if field:
            policies = [row for row in policies if row.field == field]
        if not policies:
            return []
        terms = [query or self.work.title, self.work.original_title, self.work.uniform_title]
        terms = [str(value).strip() for value in terms if str(value or "").strip()][:3]
        rows = []
        seen = set()
        for policy in policies:
            for term in terms:
                try:
                    resolved = resolve_search_query(term, scope=ADMIN_RESOLVABLE, entity_types=list(policy.query_lexicon_entity_types), expansion_limit=8)
                except Exception as exc:
                    logger.info("workflow QueryLexicon suggestion unavailable: %s", exc.__class__.__name__)
                    continue
                for matched in resolved.get("matched_entities", []):
                    entity = matched.get("canonical_entity") or {}
                    key = (policy.step, policy.field, entity.get("entity_type"), entity.get("entity_id"), matched.get("matched_term", {}).get("normalized_term"))
                    if key in seen:
                        continue
                    seen.add(key)
                    description = describe_entity(EntityKey(entity["entity_type"], UUID(str(entity["entity_id"])))) if entity.get("entity_type") and entity.get("entity_id") else None
                    label = (description or {}).get("canonical_label") or entity.get("canonical_label") or matched.get("matched_term", {}).get("term") or term
                    rows.append(
                        _dto(
                            identifier=f"ql-{policy.step}-{policy.field}-{entity.get('entity_id')}-{len(rows)}",
                            step=policy.step,
                            field=policy.field,
                            kind="entity",
                            label=label,
                            value={"id": entity.get("entity_id"), "name": label},
                            source_tier="query_lexicon",
                            source_class=matched.get("matched_term", {}).get("source_kind", "query_lexicon"),
                            confidence=0.86 if matched.get("matched_term", {}).get("trust_level") in {"authoritative", "verified"} else 0.62,
                            reasons=["QueryLexicon 命中", f"匹配词：{matched.get('matched_term', {}).get('term', term)}"],
                            entity_type=entity.get("entity_type", ""),
                            entity_id=entity.get("entity_id"),
                            available_actions=["inspect"],
                            evidence_status="lexicon_match",
                        )
                    )
        return rows[:200]

    def _corpus_rows(self, step: str | None, field: str | None, query: str | None) -> list[dict]:
        policies = [row for row in WORKFLOW_SUGGESTION_POLICIES.all() if row.corpus_enabled and (not step or row.step == step) and (not field or row.field == field)]
        if not policies:
            return []
        terms = [str(value).strip() for value in (query, self.work.title, self.work.original_title) if str(value or "").strip()]
        tokens = []
        for term in terms:
            tokens.extend(re.findall(r"[\u3400-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_-]{3,}", term))
        tokens = list(dict.fromkeys(tokens))[:5]
        if not tokens:
            return []
        condition = Q()
        for token in tokens:
            condition |= Q(normalized_text__icontains=token) | Q(original_text__icontains=token)
        rows = []
        for chunk in SemanticChunk.objects.filter(work=self.work, index_status=SemanticChunk.IndexStatus.READY).filter(condition).order_by("page_start", "order")[:30]:
            excerpt = " ".join((chunk.original_text or chunk.normalized_text).split())[:600]
            for policy in policies[:3]:
                rows.append(
                    _dto(
                        identifier=f"chunk-{chunk.id}-{policy.field}",
                        step=policy.step,
                        field=policy.field,
                        kind="corpus",
                        label=excerpt[:120],
                        value={"text": excerpt, "page_start": chunk.page_start, "page_end": chunk.page_end, "document_id": chunk.document_id},
                        source_tier="pdf_evidence",
                        source_class="semantic_chunk",
                        confidence=0.58,
                        reasons=["SemanticChunk 命中", f"页码 {chunk.page_start}-{chunk.page_end}"],
                        evidence=[{"document_id": chunk.document_id, "page_number": chunk.page_start, "supporting_text": excerpt}],
                        available_actions=["inspect"],
                    )
                )
        return rows

    def aggregate(self, *, step: str | None = None, field: str | None = None, query: str | None = None) -> dict[str, Any]:
        if step and step not in STEP_FIELD_ALIASES:
            raise ValueError("未知工作流步骤。")
        if field and step and field not in STEP_FIELD_ALIASES[step]:
            raise ValueError(f"{step} 步骤不支持字段 {field}。")
        rows = []
        rows.extend(self._metadata_rows(step, field))
        rows.extend(self._entity_rows(step, field))
        rows.extend(self._enrichment_rows(step, field))
        rows.extend(self._theory_rows(step, field))
        rows.extend(self._query_lexicon_candidate_rows(step, field))
        rows.extend(self._query_lexicon_rows(step, field, query))
        rows.extend(self._corpus_rows(step, field, query))
        deduplicated = {}
        for row in rows:
            key = (row["step"], row["field"], row["kind"], _text(row.get("proposed_value")), row.get("source_tier"), row.get("entity_id"))
            existing = deduplicated.get(key)
            if existing is None or row.get("confidence", 0) > existing.get("confidence", 0):
                deduplicated[key] = row
        rows = sorted(deduplicated.values(), key=lambda row: (-row.get("confidence", 0), row.get("source_tier", ""), row.get("label", "")))[:500]
        counts = Counter(row["source_tier"] for row in rows)
        return {
            "policy_version": WORKFLOW_SUGGESTION_POLICY_VERSION,
            "source_profile_version": SOURCE_PROFILE_VERSION,
            "step": step,
            "field": field,
            "groups": [
                {"key": key, "label": SOURCE_TIER_LABELS[key], "count": counts.get(key, 0)}
                for key in ("in_library", "query_lexicon", "pdf_evidence", "structured_source", "web_evidence", "research_lead")
                if counts.get(key, 0)
            ],
            "suggestions": rows,
            "stats": {"total": len(rows), "by_source_tier": dict(counts), "requires_human_confirmation": True},
            "errors": [],
            "policies": policy_payload(step),
            "source_profiles": source_profile_payload(),
        }

    def _research_context(self, step: str, fields: list[str]) -> dict[str, Any]:
        contributions = list(self.edition.contributions.select_related("person").values_list("person__preferred_name", flat=True)[:8])
        return {
            "title": self.work.title,
            "original_title": self.work.original_title,
            "canonical_terms": [value for value in (self.work.title, self.work.original_title, self.work.uniform_title) if value],
            "authors": contributions,
            "publisher": self.edition.publisher,
            "journal_title": self.edition.journal_title,
            "publication_year": self.edition.publication_year,
            "doi": self.edition.doi,
            "isbn": self.edition.isbn13 or self.edition.isbn10 or self.edition.isbn,
            "step": step,
            "fields": fields,
        }

    def run_step(self, *, step: str, fields: list[str] | None = None, mode: str = "full", actor=None) -> dict[str, Any]:
        if step not in STEP_FIELD_ALIASES:
            raise ValueError("未知工作流步骤。")
        selected = list(dict.fromkeys(fields or list(STEP_FIELD_ALIASES[step])))
        invalid = [value for value in selected if value not in STEP_FIELD_ALIASES[step]]
        if invalid:
            raise ValueError(f"字段不属于 {step} 步骤：{invalid[0]}")
        if len(selected) > 24:
            raise ValueError("一次研究最多选择 24 个字段。")
        mode = str(mode or "full").strip().casefold()
        if mode not in {"structured", "web", "full"}:
            raise ValueError("研究模式必须是 structured、web 或 full。")
        request_id = uuid4()
        errors = []
        stats: dict[str, Any] = {
            "request_id": str(request_id),
            "step": step,
            "fields": selected,
            "enrichment_runs": 0,
            "web_queries": 0,
            "web_leads": 0,
            "layers": [
                {"key": "in_library", "label": "本馆实体", "status": "complete"},
                {"key": "query_lexicon", "label": "QueryLexicon", "status": "complete"},
                {"key": "pdf", "label": "当前 PDF / OCR", "status": "complete"},
                {"key": "web", "label": "学术网页与课程大纲", "status": "pending" if mode in {"web", "full"} else "skipped"},
            ],
        }
        context = self._research_context(step, selected)
        # Existing FieldPolicy remains the only persistence/mutation path.
        # Group supported fields by target so a step makes at most one bounded
        # source run per Work or Edition, instead of one Web search per input.
        grouped_enrichment: dict[tuple[str, UUID], list[tuple[str, str]]] = {}
        for policy in WORKFLOW_SUGGESTION_POLICIES.for_step(step):
            if policy.field not in selected or not policy.enrichment_field or not policy.target_type:
                continue
            target_type = policy.target_type
            enrichment_field = policy.enrichment_field
            try:
                FIELD_POLICIES.get(target_type, enrichment_field)
            except ValueError:
                continue
            target_id = self.work.id if target_type == "work" else self.edition.id
            grouped_enrichment.setdefault((target_type, target_id), []).append(
                (policy.field, enrichment_field)
            )

        for (target_type, target_id), rows in grouped_enrichment.items():
            field_names = tuple(dict.fromkeys(row[1] for row in rows))[:12]
            try:
                result = FieldEnrichmentService().enrich(
                    FieldEnrichmentRequest(
                        target_type=target_type,
                        target_id=target_id,
                        field_names=field_names,
                        current_value=None,
                        form_context=context,
                        requested_mode=mode,
                        visibility="admin",
                    ),
                    actor=actor,
                )
                stats["enrichment_runs"] += 1
                stats.setdefault("enrichment", []).append({"fields": [row[0] for row in rows], "candidate_count": len(result.candidates), "errors": [asdict(row) for row in result.errors]})
            except Exception as exc:
                logger.info("workflow step enrichment failed for %s: %s", step, exc.__class__.__name__)
                errors.append({"code": "enrichment_unavailable", "field": step, "detail": "本节部分来源暂时不可用，已有候选未受影响。"})

        if mode in {"web", "full"} and any(row.web_enabled for row in WORKFLOW_SUGGESTION_POLICIES.for_step(step) if row.field in selected):
            try:
                adapter = configured_web_search_adapter()
                fetcher = SafeWebFetcher()
                fetched_urls: set[str] = set()
                fetch_budget = 6
                queries = [self.work.title]
                if self.work.original_title and self.work.original_title not in queries:
                    queries.append(self.work.original_title)
                if step == "classification":
                    queries.append(f"{self.work.title} sociology discipline syllabus")
                elif step == "knowledge":
                    queries.append(f"{self.work.title} theory concept scholarly")
                elif step == "curation":
                    queries.append(f"{self.work.title} university syllabus reading list")
                elif step == "bibliography" and self.work.document_type == "journal_article":
                    queries.append(f"{self.work.title} {self.edition.journal_title} DOI")
                for query in list(dict.fromkeys(value.strip() for value in queries if value.strip()))[:3]:
                    results, _record = adapter.search(query, limit=5)
                    stats["web_queries"] += 1
                    for result in results[:5]:
                        profile = SOURCE_PROFILES.for_source_class(result.source_class)
                        stats["web_leads"] += 1
                        evidence = []
                        source_tier = "research_lead"
                        reasons = ["SearXNG 发现", "搜索摘要仅作线索"]
                        if profile.is_evidence and result.url not in fetched_urls and len(fetched_urls) < fetch_budget:
                            fetched_urls.add(result.url)
                            try:
                                document = fetcher.fetch(result.url)
                                excerpt = _supporting_excerpt(
                                    document.text,
                                    [value for value in (self.work.title, self.work.original_title) if value],
                                )
                                if excerpt:
                                    source_tier = "web_evidence"
                                    reasons = ["SearXNG 发现", "SafeWebFetcher 已打开原页", f"来源画像：{profile.label}"]
                                    evidence = [
                                        {
                                            "canonical_url": document.canonical_url,
                                            "source_title": document.title,
                                            "source_class": document.source_class,
                                            "supporting_text": excerpt,
                                            "retrieved_at": document.retrieved_at,
                                        }
                                    ]
                            except Exception as exc:
                                logger.info("workflow research fetch failed: %s", exc.__class__.__name__)
                        stats.setdefault("web_suggestions", []).append(
                            _dto(
                                identifier=f"web-{request_id}-{stats['web_leads']}",
                                step=step,
                                field=selected[0] if selected else step,
                                kind="research_lead",
                                label=result.title,
                                value={"url": result.url, "query": query, "snippet": result.snippet},
                                source_tier=source_tier,
                                source_class=result.source_class,
                                confidence=0.66 if evidence else 0.38,
                                reasons=reasons,
                                evidence=evidence,
                                available_actions=["inspect"],
                                evidence_status="evidence" if evidence else "lead_only",
                            )
                        )
            except (WebSearchError, OSError, TimeoutError) as exc:
                errors.append({"code": getattr(exc, "code", "provider_unavailable"), "field": step, "detail": "联网研究来源暂时不可用。"})
            except Exception as exc:
                logger.info("workflow web suggestion failed: %s", exc.__class__.__name__)
                errors.append({"code": "provider_unavailable", "field": step, "detail": "联网研究来源暂时不可用。"})

        payload = self.aggregate(step=step)
        for layer in stats["layers"]:
            if layer["key"] == "web" and layer["status"] == "pending":
                layer["status"] = "attention" if any(row["code"] in {"provider_unavailable", "timeout", "rate_limited"} for row in errors) else "complete"
        payload["run"] = stats
        payload["errors"] = errors
        if stats.get("web_suggestions"):
            payload["suggestions"] = sorted(
                [*payload["suggestions"], *stats["web_suggestions"]],
                key=lambda row: (-row.get("confidence", 0), row.get("source_tier", "")),
            )[:500]
            counts = Counter(row["source_tier"] for row in payload["suggestions"])
            payload["groups"] = [
                {"key": key, "label": SOURCE_TIER_LABELS[key], "count": counts.get(key, 0)}
                for key in ("in_library", "query_lexicon", "pdf_evidence", "structured_source", "web_evidence", "research_lead")
                if counts.get(key, 0)
            ]
            payload["stats"]["total"] = len(payload["suggestions"])
            payload["stats"]["by_source_tier"] = dict(counts)
        return payload


def suggestion_policy_payload(step: str | None = None) -> dict[str, Any]:
    return {
        "policy_version": WORKFLOW_SUGGESTION_POLICY_VERSION,
        "source_profile_version": SOURCE_PROFILE_VERSION,
        "policies": policy_payload(step),
        "source_profiles": source_profile_payload(),
    }
