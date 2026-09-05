from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from copy import deepcopy
from typing import Any, Iterable

from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from catalog.models import (
    CatalogFieldDecision,
    Contribution,
    EditorialRevision,
    EnrichmentCandidate,
    KnowledgeNode,
    KnowledgePublicationEvent,
    KnowledgePublicationStatus,
    Person,
    PublicationBundleItem,
    PublicationState,
    PublisherAuthority,
    RelationReviewStatus,
    ResearchRun,
    ScholarProfile,
    TheorySchool,
    Topic,
    Work,
    WorkKnowledgeRelation,
    WorkNodeRelation,
    WorkTopicRelation,
)
from catalog.services.field_decisions import (
    ensure_publication_bundle,
    invalidate_dependent_fields,
    record_edition_field_decision,
)
from catalog.services.editorial_revision import (
    editorial_target_snapshot,
    save_workflow_editorial_revision,
    serialize_editorial_revision,
)
from catalog.services.field_enrichment.mutations import reject_enrichment_candidate
from catalog.services.query_lexicon.normalization import normalize_term
from ingestion.models import (
    AuditEvent,
    DecisionLog,
    EntityResolutionCandidate,
    MetadataCandidate,
    ReviewTask,
    UploadItem,
)
from ingestion.services.entity_resolution_decisions import (
    ResolutionDecisionError,
    available_resolution_actions,
    decide_entity_resolution,
)
from ingestion.services.candidate_decisions import set_candidate_decision

from .contracts import FieldAssistantRequest, FieldAssistantResult
from .policies import AssistantFieldPolicy, get_field_policy


DECISION_FIELDS = {
    "author": "authors",
    "translator": "translators",
    "topic": "topics",
    "theory": "theories",
}
logger = logging.getLogger(__name__)


class FieldAssistantError(ValueError):
    pass


def _canonical_field(policy: AssistantFieldPolicy) -> str:
    return DECISION_FIELDS.get(policy.key, policy.key)


def _actor_id(actor):
    return getattr(actor, "pk", None)


def _context_fingerprint(request: FieldAssistantRequest, edition) -> str:
    draft = EditorialRevision.objects.filter(
        target_type="work", target_id=edition.work_id, status=EditorialRevision.Status.DRAFT,
    ).order_by("-revision").values("id", "revision", "updated_at", "patch").first()
    payload = {
        "object_type": request.object_type,
        "object_id": str(request.object_id),
        "field": request.field_name,
        "query": request.query,
        "confirmed_context": request.confirmed_context,
        "edition_updated_at": edition.updated_at.isoformat(),
        "work_updated_at": edition.work.updated_at.isoformat(),
        "editorial_draft": draft,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _edition_for_request(request: FieldAssistantRequest):
    from catalog.models import Edition, Work

    object_type = str(request.object_type or "").strip().casefold()
    if object_type == "edition":
        edition = (
            Edition.objects.select_related("work")
            .filter(pk=request.object_id)
            .first()
        )
    elif object_type == "work":
        work = Work.objects.filter(pk=request.object_id).first()
        edition = (
            work.editions.order_by("-is_primary", "-updated_at", "pk").first()
            if work
            else None
        )
        if edition is not None:
            edition.work = work
    else:
        raise FieldAssistantError("当前对象暂不支持字段智能查找。")
    if edition is None:
        raise FieldAssistantError("当前编目对象没有可编辑版本。")
    return edition


def _upload_item(edition, explicit_id=None) -> UploadItem | None:
    rows = UploadItem.objects.filter(edition=edition)
    if explicit_id:
        rows = rows.filter(pk=explicit_id)
    return rows.order_by("-updated_at", "-created_at").first()


def _normalized(value: Any) -> str:
    return normalize_term(" ".join(str(value or "").split()))


def _value_rows(value: Any) -> list[tuple[str, Any]]:
    if isinstance(value, list):
        output: list[tuple[str, Any]] = []
        for item in value:
            output.extend(_value_rows(item))
        return output
    if isinstance(value, dict):
        for key in (
            "label",
            "name",
            "preferred_name",
            "canonical_name_zh",
            "canonical_name_en",
            "title",
            "value",
            "publisher",
            "abstract",
            "summary",
            "publication_year",
        ):
            if value.get(key):
                return [(str(value[key]).strip(), value)]
        return []
    label = str(value or "").strip()
    return [(label, value)] if label else []


def _evidence(category: str, summary: str, *, locator: dict | None = None) -> dict:
    payload = {"category": category, "summary": str(summary or "").strip()}
    if locator:
        payload["locator"] = locator
    return payload


def _metadata_evidence(candidate: MetadataCandidate) -> list[dict]:
    output: list[dict] = []
    for row in candidate.evidence_records.all()[:20]:
        locator = {"page": row.page_number} if row.page_number else None
        summary = row.text_quote.strip() or "当前文件中的书目信息"
        output.append(_evidence("来自本书", summary[:280], locator=locator))
    if not output:
        source = str(candidate.source or "").casefold()
        category = "来自本书" if any(key in source for key in ("pdf", "ocr", "native")) else "其他资料"
        output.append(_evidence(category, "发现了与当前字段一致的值"))
    source = str(candidate.source or "").casefold()
    evidence = dict(candidate.evidence or {})
    if any(key in source for key in ("synthesis", "ai_generated", "llm")) or evidence.get("ai_assisted"):
        output.append(_evidence("AI整理", "采用前请核对所引用的馆藏原文。"))
    return output


def _metadata_value_rows(candidate: MetadataCandidate, policy: AssistantFieldPolicy):
    value = candidate.value
    if candidate.field_name == "contributors" and policy.contribution_role:
        rows = value if isinstance(value, list) else [value]
        value = [
            row for row in rows
            if isinstance(row, dict) and str(row.get("role") or "author") == policy.contribution_role
        ]
    return _value_rows(value)


def _enrichment_evidence(candidate: EnrichmentCandidate) -> list[dict]:
    output: list[dict] = []
    official = {
        "publisher": "出版社资料",
        "identifier_registry": "权威资料",
        "national_library": "权威资料",
        "library_catalog": "权威资料",
        "university": "权威资料",
        "research_institute": "权威资料",
        "academic_journal": "权威资料",
        "professional_association": "权威资料",
        "scholarly_encyclopedia": "权威资料",
        "scholar_homepage": "权威资料",
    }
    for row in candidate.evidence_records.filter(is_current=True)[:20]:
        category = official.get(row.source_class, "其他外部资料")
        locator = dict(row.locator or {})
        output.append(
            _evidence(category, row.supporting_text[:280], locator=locator or None)
        )
    context = dict(candidate.request_context or {})
    if any(context.get(key) for key in ("ai_generated", "ai_assisted", "library_synthesis")) or "synthesis" in str(context.get("source_kind", "")):
        output.append(_evidence("AI整理", "根据所列原始材料整理，采用前请核对原文。"))
    return output or [_evidence("其他资料", "该建议需要管理员进一步核对")]


def _entity_evidence(candidate: EntityResolutionCandidate) -> list[dict]:
    properties = dict(candidate.supporting_properties or {})
    evidence_status = str(properties.get("evidence_status") or "").casefold()
    provider = str(properties.get("provider") or "").casefold()
    if candidate.candidate_entity_id:
        category = "馆内已有记录"
    elif evidence_status in {"verified_text", "structured_evidence"}:
        category = "来自本书"
    elif provider in {"searxng", "web_search", "searching"}:
        category = "其他外部资料"
    else:
        category = "其他资料"
    reasons = [
        str(value).strip()
        for value in candidate.match_reasons or []
        if str(value).strip()
    ]
    # Keep evidence phrasing editorial. Raw provider names and numeric match
    # scores remain available only in diagnostics.
    if reasons:
        return [_evidence(category, reason[:280]) for reason in reasons[:6]]
    return [_evidence(category, "与当前作品及字段上下文一致")]


def _raw_candidate(
    *,
    label: str,
    value: Any,
    source_type: str,
    source_id,
    evidence: Iterable[dict],
    entity_type: str = "",
    entity_id=None,
    formal: bool = False,
    conflicts: Iterable[Any] = (),
) -> dict[str, Any]:
    return {
        "label": str(label or "").strip(),
        "value": value,
        "entity_type": str(entity_type or ""),
        "entity_id": str(entity_id) if entity_id else "",
        "formal": bool(formal),
        "conflicts": [str(item) for item in conflicts if str(item).strip()],
        "evidence": list(evidence),
        "ref": {
            "source_type": source_type,
            "source_id": str(source_id),
            "entity_type": str(entity_type or ""),
        },
    }


def _prepared_candidates(
    policy: AssistantFieldPolicy,
    edition,
    item: UploadItem | None,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    if item is not None:
        metadata = item.metadata_candidates.filter(
            field_name__in=policy.metadata_fields,
            lifecycle=MetadataCandidate.Lifecycle.PROPOSED,
        ).prefetch_related("evidence_records")
        for candidate in metadata:
            for label, value in _metadata_value_rows(candidate, policy):
                output.append(
                    _raw_candidate(
                        label=label,
                        value=value,
                        source_type="metadata",
                        source_id=candidate.pk,
                        evidence=_metadata_evidence(candidate),
                    )
                )

        entity_rows = item.entity_resolution_candidates.filter(
            target_type__in=policy.entity_target_types,
            status=EntityResolutionCandidate.Status.PROPOSED,
        )
        for candidate in entity_rows:
            if not {"link_existing", "create_draft"}.intersection(available_resolution_actions(candidate)):
                continue
            if policy.contribution_role:
                role = str(
                    (candidate.supporting_properties or {}).get("contribution_role")
                    or Contribution.Role.AUTHOR
                )
                if role != policy.contribution_role:
                    continue
            entity_type = str(candidate.candidate_entity_type or candidate.target_type)
            formal = bool(
                candidate.candidate_entity_id
                and not entity_type.endswith("_draft")
            )
            output.append(
                _raw_candidate(
                    label=candidate.label or candidate.source_name,
                    value={
                        "label": candidate.label or candidate.source_name,
                        "entity_id": candidate.candidate_entity_id,
                    },
                    source_type="entity_resolution",
                    source_id=candidate.pk,
                    evidence=_entity_evidence(candidate),
                    entity_type=entity_type.removesuffix("_draft"),
                    entity_id=candidate.candidate_entity_id or None,
                    formal=formal,
                    conflicts=candidate.conflicts or (),
                )
            )

    enrichment = EnrichmentCandidate.objects.filter(
        Q(target_type=EnrichmentCandidate.TargetType.WORK, target_id=edition.work_id)
        | Q(target_type=EnrichmentCandidate.TargetType.EDITION, target_id=edition.pk),
        field_name__in=policy.enrichment_fields,
        status=EnrichmentCandidate.Status.PENDING,
    ).prefetch_related("evidence_records")
    for candidate in enrichment:
        if not candidate.evidence_records.filter(is_current=True).exclude(supporting_text="").exists():
            continue
        for label, value in _value_rows(candidate.proposed_value):
            normalized = candidate.normalized_value or {}
            entity_type = str(
                normalized.get("entity_type")
                or normalized.get("target_type")
                or ""
            ) if isinstance(normalized, dict) else ""
            entity_id = (
                normalized.get("entity_id")
                if isinstance(normalized, dict)
                else None
            )
            output.append(
                _raw_candidate(
                    label=label,
                    value=value,
                    source_type="enrichment",
                    source_id=candidate.pk,
                    evidence=_enrichment_evidence(candidate),
                    entity_type=entity_type,
                    entity_id=entity_id,
                    formal=bool(entity_id),
                    conflicts=candidate.conflicts or (),
                )
            )
    return output


def _search_terms(request: FieldAssistantRequest, rows: list[dict]) -> list[str]:
    values = [request.query]
    values.extend(row["label"] for row in rows)
    terms: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalized(value)
        if normalized and normalized not in seen:
            terms.append(str(value).strip())
            seen.add(normalized)
    return terms[:12]


def _local_candidates(
    policy: AssistantFieldPolicy,
    terms: list[str],
    edition=None,
) -> list[dict[str, Any]]:
    if not terms:
        return []
    query = Q()
    for term in terms:
        if policy.entity_type == "person":
            query |= Q(preferred_name__icontains=term) | Q(original_name__icontains=term)
        elif policy.entity_type == "publisher":
            query |= Q(canonical_name__icontains=term)
        elif policy.entity_type == "topic":
            query |= Q(name__icontains=term)
        else:
            query |= Q(name__icontains=term)

    output: list[dict[str, Any]] = []
    def eligible(kind, state_field, formal_state):
        current_drafts = PublicationBundleItem.objects.filter(
            bundle__edition=edition, bundle__status="draft", object_type=kind,
        ).values("object_id") if edition is not None else []
        return Q(**{state_field: formal_state}) | Q(pk__in=current_drafts)

    if policy.entity_type == "person":
        rows = Person.objects.filter(query, eligible("person", "authority_status", "verified")).exclude(
            authority_status__in={
                Person.AuthorityStatus.REJECTED,
                Person.AuthorityStatus.MERGED,
                Person.AuthorityStatus.ARCHIVED,
            }
        )[:40]
        for person in rows:
            output.append(
                _raw_candidate(
                    label=person.preferred_name,
                    value={"entity_id": str(person.pk), "label": person.preferred_name},
                    source_type="local_person",
                    source_id=person.pk,
                    evidence=[_evidence("馆内已有记录", "馆内已有学者，可直接关联")],
                    entity_type="person",
                    entity_id=person.pk,
                    formal=person.authority_status == Person.AuthorityStatus.VERIFIED,
                )
            )
    elif policy.entity_type == "publisher":
        for publisher in PublisherAuthority.objects.filter(query, eligible("publisher", "editorial_status", "published"))[:40]:
            output.append(
                _raw_candidate(
                    label=publisher.canonical_name,
                    value={"entity_id": str(publisher.pk), "label": publisher.canonical_name},
                    source_type="local_publisher",
                    source_id=publisher.pk,
                    evidence=[_evidence("馆内已有记录", "馆内已有出版社记录")],
                    entity_type="publisher",
                    entity_id=publisher.pk,
                    formal=publisher.editorial_status == "published",
                )
            )
    elif policy.entity_type == "topic":
        for topic in Topic.objects.filter(query, eligible("topic", "editorial_status", "published"))[:40]:
            output.append(
                _raw_candidate(
                    label=topic.name,
                    value={"entity_id": str(topic.pk), "label": topic.name},
                    source_type="local_topic",
                    source_id=topic.pk,
                    evidence=[_evidence("馆内已有记录", "馆内已有主题，可直接关联")],
                    entity_type="topic",
                    entity_id=topic.pk,
                    formal=topic.editorial_status == "published",
                )
            )
    elif policy.entity_type == "theory":
        theory_query = Q()
        node_query = Q()
        for term in terms:
            theory_query |= Q(name__icontains=term) | Q(foreign_name__icontains=term)
            node_query |= Q(canonical_name_zh__icontains=term) | Q(canonical_name_en__icontains=term)
        for theory in TheorySchool.objects.filter(theory_query, eligible("theory_school", "editorial_status", "published"))[:30]:
            output.append(
                _raw_candidate(
                    label=theory.name,
                    value={"entity_id": str(theory.pk), "label": theory.name},
                    source_type="local_theory_school",
                    source_id=theory.pk,
                    evidence=[_evidence("馆内已有记录", "馆内已有理论传统")],
                    entity_type="theory_school",
                    entity_id=theory.pk,
                    formal=theory.editorial_status == "published",
                )
            )
        for node in KnowledgeNode.objects.filter(
            node_query,
            eligible("knowledge_node", "status", "published"),
            node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        )[:30]:
            label = node.canonical_name_zh or node.canonical_name_en
            output.append(
                _raw_candidate(
                    label=label,
                    value={"entity_id": str(node.pk), "label": label},
                    source_type="local_knowledge_node",
                    source_id=node.pk,
                    evidence=[_evidence("馆内已有记录", "馆内已有理论节点")],
                    entity_type="knowledge_node",
                    entity_id=node.pk,
                    formal=node.status == KnowledgePublicationStatus.PUBLISHED,
                )
            )
    return output


def _feedback_context(edition, policy):
    from catalog.services.field_decisions import formal_field_values

    values, _ = formal_field_values(edition)
    context = {name: values.get(name) for name in ("title", "isbn10", "isbn13", "publisher", "publication_year")}
    if policy.key != "author":
        context["authors"] = values.get("authors")
    return hashlib.sha256(json.dumps(context, sort_keys=True, default=str).encode()).hexdigest()


def _without_rejected_matches(rows, edition, policy):
    feedback = AuditEvent.objects.filter(
        action="field_assistant_local_rejected", object_type="Edition", object_id=str(edition.pk),
        after__field_name=policy.key, after__context=_feedback_context(edition, policy),
    ).values_list("after", flat=True)
    rejected_ids, rejected_labels = set(), set()
    for row in feedback:
        rejected_ids.add((row["entity_type"], row["entity_id"]))
        rejected_labels.add(_normalized(row["label"]))
    return [row for row in rows if (row["entity_type"], row["entity_id"]) not in rejected_ids
            and (row["entity_id"] or _normalized(row["label"]) not in rejected_labels)]


def _deduplicate_evidence(rows: Iterable[dict]) -> list[dict]:
    output: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        key = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def _aggregate_candidates(rows: list[dict], *, default_limit: int) -> tuple[tuple[dict, ...], tuple[dict, ...]]:
    identity_by_label: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row["entity_id"]:
            key = f"entity:{row['entity_type']}:{row['entity_id']}"
            identity_by_label[_normalized(row["label"])].add(key)

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["entity_id"]:
            key = f"entity:{row['entity_type']}:{row['entity_id']}"
        else:
            identities = identity_by_label.get(_normalized(row["label"]), set())
            key = next(iter(identities)) if len(identities) == 1 else f"value:{_normalized(row['label'])}"
        grouped[key].append(row)

    ambiguous_labels = {
        label for label, keys in identity_by_label.items() if len(keys) > 1
    }
    preference = {
        "entity_resolution": 1,
        "enrichment": 2,
        "metadata": 3,
        "local_person": 0,
        "local_publisher": 0,
        "local_topic": 0,
        "local_theory_school": 0,
        "local_knowledge_node": 0,
    }
    results: list[dict] = []
    for key, members in grouped.items():
        members.sort(key=lambda row: preference.get(row["ref"]["source_type"], 9))
        primary = members[0]
        conflicts = [item for row in members for item in row["conflicts"]]
        if _normalized(primary["label"]) in ambiguous_labels:
            conflicts.append("馆内存在同名对象，请确认具体身份。")
        evidence = _deduplicate_evidence(
            item for row in members for item in row["evidence"]
        )
        formal = any(row["formal"] for row in members)
        categories = {row["category"] for row in evidence}
        if conflicts:
            status = "conflict"
            status_label = "存在冲突"
        elif formal or len(categories) > 1:
            status = "recommended"
            status_label = "建议采用"
        else:
            status = "needs_review"
            status_label = "需要确认"
        stable_key = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        results.append(
            {
                "id": stable_key,
                "label": primary["label"],
                "value": primary["value"],
                "entity": (
                    {
                        "type": primary["entity_type"],
                        "id": primary["entity_id"],
                        "existing": formal,
                    }
                    if primary["entity_id"]
                    else None
                ),
                "status": status,
                "status_label": status_label,
                "summary": (
                    "馆内已有对象，多个依据与当前作品一致"
                    if formal and len(categories) > 1
                    else "馆内已有对象，可直接关联"
                    if formal
                    else "需要管理员核对后采用"
                ),
                "evidence": evidence,
                "conflicts": sorted(set(conflicts)),
                "source_count": len(members),
                "action": {
                    **primary["ref"],
                    "selected_value": primary["label"],
                },
            }
        )
    status_order = {"recommended": 0, "needs_review": 1, "conflict": 2}
    results.sort(
        key=lambda row: (
            status_order.get(row["status"], 9),
            0 if row["entity"] and row["entity"]["existing"] else 1,
            -row["source_count"],
            _normalized(row["label"]),
        )
    )
    limit = max(1, min(int(default_limit or 3), 3))
    return tuple(results[:limit]), tuple(results[limit:])


def _current_value(edition, policy: AssistantFieldPolicy) -> Any:
    if _requires_editorial_revision(edition):
        draft_value = _draft_field_value(edition, policy)
        if draft_value is not None:
            return draft_value
    field = _canonical_field(policy)
    if field in {"authors", "translators"}:
        role = (
            Contribution.Role.AUTHOR
            if field == "authors"
            else Contribution.Role.TRANSLATOR
        )
        return [
            {
                "id": str(row.person_id),
                "name": row.person.preferred_name,
                "role": row.role,
            }
            for row in edition.contributions.filter(role=role, approved=True)
            .select_related("person")
            .order_by("order", "created_at", "pk")
        ]
    if field == "publisher":
        return {
            "id": str(edition.publisher_authority_id or ""),
            "name": edition.publisher,
        }
    if field == "topics":
        return [
            {"id": str(row.topic_id), "name": row.topic.name}
            for row in edition.work.topic_relations.filter(
                review_status=RelationReviewStatus.APPROVED
            ).select_related("topic")
        ]
    if field == "theories":
        nodes = [
            {"id": str(row.node_id), "name": row.node.canonical_name_zh or row.node.canonical_name_en}
            for row in edition.work.node_relations.filter(
                status__in={
                    KnowledgePublicationStatus.PENDING,
                    KnowledgePublicationStatus.PUBLISHED,
                }
            ).select_related("node")
        ]
        legacy = [
            {"id": str(row.theory_school_id), "name": row.theory_school.name}
            for row in edition.work.knowledge_relations.filter(
                kind=WorkKnowledgeRelation.Kind.THEORY_SCHOOL,
                approved=True,
            ).select_related("theory_school")
            if row.theory_school_id
        ]
        return [*nodes, *legacy]
    if hasattr(edition, field):
        return getattr(edition, field)
    if hasattr(edition.work, field):
        return getattr(edition.work, field)
    return None


def _requires_editorial_revision(edition) -> bool:
    return edition.state == PublicationState.PUBLISHED or edition.work.editions.filter(
        state=PublicationState.PUBLISHED
    ).exists()


def _latest_editorial_revision(edition):
    return EditorialRevision.objects.filter(
        target_type=EditorialRevision.TargetType.WORK,
        target_id=edition.work_id,
        status=EditorialRevision.Status.DRAFT,
    ).order_by("-revision").first()


def _edition_section_values(edition, section: str) -> dict:
    from catalog.services.editorial_revision import _work_edition_section_snapshot

    values = deepcopy(_work_edition_section_snapshot(edition, section))
    revision = _latest_editorial_revision(edition)
    patch = (revision.patch or {}).get(section) if revision else None
    if patch:
        if str(patch.get("edition_id")) != str(edition.pk):
            raise FieldAssistantError("当前作品另一个版本已有编辑草稿，请先完成或撤销该草稿。")
        values.update(deepcopy(patch.get("values") or {}))
    return values


def _knowledge_values(edition) -> dict:
    snapshot = editorial_target_snapshot(
        target_type=EditorialRevision.TargetType.WORK, target=edition.work,
    )
    revision = _latest_editorial_revision(edition)
    return deepcopy(
        (revision.patch or {}).get("knowledge", snapshot["knowledge"])
        if revision else snapshot["knowledge"]
    )


def _draft_field_value(edition, policy: AssistantFieldPolicy):
    revision = _latest_editorial_revision(edition)
    if revision is None:
        return None
    patch = revision.patch or {}
    if policy.contribution_role and "contributors" in patch:
        rows = _edition_section_values(edition, "contributors").get("contributors", [])
        people = Person.objects.in_bulk([row["person_id"] for row in rows])
        by_id = {str(key): value for key, value in people.items()}
        return [
            {"id": str(row["person_id"]), "name": by_id[str(row["person_id"])].preferred_name, "role": row["role"]}
            for row in rows
            if row["role"] == policy.contribution_role and str(row["person_id"]) in by_id
        ]
    if policy.key in {"publisher", "publication_year"} and "bibliography" in patch:
        values = _edition_section_values(edition, "bibliography")
        if policy.key == "publisher":
            return {"id": str(values.get("publisher_authority_id") or ""), "name": values.get("publisher", "")}
        return values.get(policy.key)
    if policy.key in {"topic", "theory"} and "knowledge" in patch:
        values = _knowledge_values(edition)
        collections = [("topics", Topic)] if policy.key == "topic" else [("nodes", KnowledgeNode), ("theories", TheorySchool)]
        result = []
        for field, model in collections:
            ids = [row["id"] for row in values.get(field, [])]
            entities = {str(key): entity for key, entity in model.objects.in_bulk(ids).items()}
            for identifier in ids:
                entity = entities.get(str(identifier))
                if entity is not None:
                    label = (entity.canonical_name_zh or entity.canonical_name_en) if isinstance(entity, KnowledgeNode) else entity.name
                    result.append({"id": str(identifier), "name": label})
        return result
    return patch.get(_canonical_field(policy))


def _stage_entity(edition, policy, entity, *, actor):
    if policy.contribution_role and isinstance(entity, Person):
        values = _edition_section_values(edition, "contributors")
        rows = values.setdefault("contributors", [])
        if not any(str(row["person_id"]) == str(entity.pk) and row["role"] == policy.contribution_role for row in rows):
            rows.append({"person_id": str(entity.pk), "role": policy.contribution_role, "order": max((row.get("order", 0) for row in rows), default=-1) + 1})
        patch = {"contributors": {"edition_id": str(edition.pk), "values": values}}
    elif policy.key == "publisher" and isinstance(entity, PublisherAuthority):
        values = _edition_section_values(edition, "bibliography")
        values.update(publisher=entity.canonical_name, publisher_authority_id=str(entity.pk))
        patch = {"bibliography": {"edition_id": str(edition.pk), "values": values}}
    elif policy.key == "topic" and isinstance(entity, Topic) or policy.key == "theory" and isinstance(entity, (KnowledgeNode, TheorySchool)):
        values = _knowledge_values(edition)
        field = "topics" if isinstance(entity, Topic) else "nodes" if isinstance(entity, KnowledgeNode) else "theories"
        rows = values.setdefault(field, [])
        if not any(str(row["id"]) == str(entity.pk) for row in rows):
            row = {"id": str(entity.pk), "is_primary": False}
            if field == "nodes":
                row["role"] = WorkNodeRelation.Role.GENERAL_MENTION
            rows.append(row)
        patch = {"knowledge": values}
    else:
        raise FieldAssistantError("当前候选不是可关联的馆内对象。")
    return save_workflow_editorial_revision(
        work_id=edition.work_id, section_patch=patch, actor=actor,
        change_note=f"在{policy.label}字段确认关联",
    )


def _decision_provenance(edition, **values) -> dict:
    revision = _latest_editorial_revision(edition) if _requires_editorial_revision(edition) else None
    if revision is not None:
        values.update(editorial_revision_id=str(revision.pk), canonical_write_deferred=True)
    return values


def _revision_response(edition) -> dict:
    revision = _latest_editorial_revision(edition) if _requires_editorial_revision(edition) else None
    return {
        "canonical_write_deferred": revision is not None,
        "editorial_revision": serialize_editorial_revision(revision) if revision else None,
    }


def _link_entity(edition, policy: AssistantFieldPolicy, entity, *, actor, source: str) -> None:
    if isinstance(entity, Person):
        if entity.authority_status in {Person.AuthorityStatus.ARCHIVED, Person.AuthorityStatus.MERGED, Person.AuthorityStatus.REJECTED}:
            raise FieldAssistantError("该学者已撤回或合并，请选择当前馆内对象。")
        formal = entity.authority_status == Person.AuthorityStatus.VERIFIED and ScholarProfile.objects.filter(person=entity, editorial_status="published").exists()
    elif isinstance(entity, KnowledgeNode):
        if entity.status not in {KnowledgePublicationStatus.DRAFT, KnowledgePublicationStatus.PENDING, KnowledgePublicationStatus.PUBLISHED}:
            raise FieldAssistantError("该理论节点已撤回，请选择当前馆内对象。")
        formal = entity.status == KnowledgePublicationStatus.PUBLISHED
    else:
        if getattr(entity, "editorial_status", "draft") not in {"draft", "pending", "published"}:
            raise FieldAssistantError("该对象已撤回，请选择当前馆内对象。")
        formal = getattr(entity, "editorial_status", "draft") == "published"
    if not formal:
        _bundle_created_entity(ensure_publication_bundle(edition, actor=actor), entity, label=str(entity))
    if _requires_editorial_revision(edition):
        _stage_entity(edition, policy, entity, actor=actor)
        return
    now = timezone.now()
    if policy.contribution_role:
        if not isinstance(entity, Person):
            raise FieldAssistantError("当前候选不是可关联的学者。")
        relation, _created = Contribution.objects.update_or_create(
            edition=edition,
            person=entity,
            role=policy.contribution_role,
            defaults={
                "source": source,
                "confidence": 1,
                "approved": True,
            },
        )
        if not relation.approved:
            raise FieldAssistantError("作者或译者关系未能写入正式草稿。")
        return
    if policy.key == "publisher":
        if not isinstance(entity, PublisherAuthority):
            raise FieldAssistantError("当前候选不是可关联的出版社。")
        edition.publisher_authority = entity
        edition.publisher = entity.canonical_name
        edition.save(update_fields=["publisher_authority", "publisher", "updated_at"])
        return
    if policy.key == "topic":
        if not isinstance(entity, Topic):
            raise FieldAssistantError("当前候选不是可关联的主题。")
        WorkTopicRelation.objects.update_or_create(
            work=edition.work,
            topic=entity,
            defaults={
                "source": source,
                "confidence": 1,
                "review_status": RelationReviewStatus.APPROVED,
                "reviewed_by": actor,
                "reviewed_at": now,
            },
        )
        return
    if policy.key == "theory" and isinstance(entity, KnowledgeNode):
        WorkNodeRelation.objects.update_or_create(
            work=edition.work,
            node=entity,
            role=WorkNodeRelation.Role.GENERAL_MENTION,
            defaults={
                "source": source,
                "confidence": 1,
                "status": (
                    KnowledgePublicationStatus.PUBLISHED
                    if entity.status == KnowledgePublicationStatus.PUBLISHED
                    else KnowledgePublicationStatus.PENDING
                ),
                "reviewed_by": actor,
                "reviewed_at": now,
            },
        )
        return
    if policy.key == "theory" and isinstance(entity, TheorySchool):
        WorkKnowledgeRelation.objects.update_or_create(
            work=edition.work,
            kind=WorkKnowledgeRelation.Kind.THEORY_SCHOOL,
            theory_school=entity,
            defaults={
                "source": source,
                "confidence": 1,
                "approved": True,
                "review_status": RelationReviewStatus.APPROVED,
                "reviewed_by": actor,
                "reviewed_at": now,
            },
        )
        return
    raise FieldAssistantError("当前字段暂不支持关联这种馆内对象。")


def _local_entity(source_type: str, source_id):
    models = {
        "local_person": Person,
        "local_publisher": PublisherAuthority,
        "local_topic": Topic,
        "local_theory_school": TheorySchool,
        "local_knowledge_node": KnowledgeNode,
    }
    model = models.get(source_type)
    if model is None:
        raise FieldAssistantError("未知的馆内对象候选。")
    try:
        return model.objects.select_for_update().get(pk=source_id)
    except (model.DoesNotExist, ValueError, TypeError):
        raise FieldAssistantError("馆内对象已变化，请重新查找。") from None


def _apply_scalar(edition, policy: AssistantFieldPolicy, value: Any, *, actor) -> None:
    field_name = _canonical_field(policy)
    target = edition if hasattr(edition, field_name) else edition.work
    if not hasattr(target, field_name):
        raise FieldAssistantError("该字段不能直接采用值候选。")
    try:
        model_field = target._meta.get_field(field_name)
    except Exception as exc:
        raise FieldAssistantError("该字段不能直接采用值候选。") from exc
    if getattr(model_field, "many_to_many", False) or getattr(model_field, "is_relation", False):
        raise FieldAssistantError("该字段必须先确认馆内对象身份。")
    try:
        converted = model_field.to_python(value)
        model_field.run_validators(converted)
        if field_name == "publication_year" and not 1000 <= converted <= 2100:
            raise ValueError("year out of range")
    except Exception as exc:
        raise FieldAssistantError("建议值的格式不适用于当前字段。") from exc
    if _requires_editorial_revision(edition):
        if target is edition:
            values = _edition_section_values(edition, "bibliography")
            values[field_name] = converted
            if field_name == "publisher":
                values["publisher_authority_id"] = None
            patch = {"bibliography": {"edition_id": str(edition.pk), "values": values}}
        else:
            patch = {field_name: converted}
        save_workflow_editorial_revision(
            work_id=edition.work_id,
            section_patch=patch,
            actor=actor,
            change_note=f"在{policy.label}字段采用建议",
        )
        return
    setattr(target, field_name, converted)
    target.save(update_fields=[field_name, "updated_at"])


def _accept_metadata_candidate(candidate: MetadataCandidate, *, actor) -> None:
    if candidate.lifecycle == MetadataCandidate.Lifecycle.ACCEPTED:
        return
    if candidate.lifecycle != MetadataCandidate.Lifecycle.PROPOSED:
        raise FieldAssistantError("该字段建议已经失效，请重新查找。")
    now = timezone.now()
    siblings = MetadataCandidate.objects.select_for_update().filter(
        upload_item=candidate.upload_item,
        field_name=candidate.field_name,
        lifecycle=MetadataCandidate.Lifecycle.ACCEPTED,
    ).exclude(pk=candidate.pk)
    siblings.update(
        lifecycle=MetadataCandidate.Lifecycle.SUPERSEDED,
        selected=False,
        updated_at=now,
    )
    before = {"lifecycle": candidate.lifecycle, "selected": candidate.selected}
    candidate.lifecycle = MetadataCandidate.Lifecycle.ACCEPTED
    candidate.selected = True
    candidate.accepted_by = actor
    candidate.accepted_at = now
    candidate.rejected_by = None
    candidate.rejected_at = None
    candidate.save(
        update_fields=[
            "lifecycle",
            "selected",
            "accepted_by",
            "accepted_at",
            "rejected_by",
            "rejected_at",
            "updated_at",
        ]
    )
    DecisionLog.objects.create(
        upload_item=candidate.upload_item,
        metadata_candidate=candidate,
        actor=actor,
        action="accept_metadata_candidate",
        target_type="catalog_field",
        target_id=candidate.field_name,
        before=before,
        after={
            "lifecycle": candidate.lifecycle,
            "selected": True,
            "value": candidate.value,
        },
        reason="通过字段助手采用",
    )


def _resolution_entity(candidate: EntityResolutionCandidate):
    models = {
        "person": Person,
        "publisher": PublisherAuthority,
        "knowledge_node": KnowledgeNode,
    }
    model = models.get(candidate.target_type)
    if model is None or not candidate.candidate_entity_id:
        raise FieldAssistantError("实体建议没有形成可关联的馆内对象。")
    try:
        return model.objects.select_for_update().get(pk=candidate.candidate_entity_id)
    except (model.DoesNotExist, ValueError, TypeError):
        raise FieldAssistantError("实体建议指向的馆内对象不存在。") from None


def _adopt_resolution_in_revision(service, candidate, *, edition, policy, actor, action, reason):
    """Confirm identity without invoking legacy canonical relation writes."""
    from ingestion.services.entity_resolution_decisions import _review_task_for

    candidate = EntityResolutionCandidate.objects.select_for_update().get(pk=candidate.pk)
    if candidate.status in {EntityResolutionCandidate.Status.LINKED, EntityResolutionCandidate.Status.CREATE_DRAFT}:
        entity = _resolution_entity(candidate)
        _link_entity(edition, policy, entity, actor=actor, source="field_assistant")
        return entity
    if candidate.status != EntityResolutionCandidate.Status.PROPOSED or action not in available_resolution_actions(candidate):
        raise FieldAssistantError("该建议尚无可采用的证据，或已经失效，请重新查找。")
    before = {"status": candidate.status, "entity_id": candidate.candidate_entity_id}
    if action == "create_draft":
        result = service.create_and_link(
            edition_id=edition.pk, field_name=policy.key,
            label=candidate.source_name or candidate.label,
            actor=actor, details=dict(candidate.supporting_properties or {}),
        )
        candidate.candidate_entity_id = result["entity"]["id"]
        candidate.candidate_entity_type = (
            "knowledge_node" if policy.entity_type == "theory" else policy.entity_type
        )
        candidate.target_type = "knowledge_node" if policy.entity_type == "theory" else candidate.target_type
        entity = _resolution_entity(candidate)
        candidate.status = EntityResolutionCandidate.Status.CREATE_DRAFT
    else:
        entity = _resolution_entity(candidate)
        _link_entity(edition, policy, entity, actor=actor, source="field_assistant")
        candidate.status = EntityResolutionCandidate.Status.LINKED
    now = timezone.now()
    candidate.supporting_properties = {
        **dict(candidate.supporting_properties or {}),
        **_decision_provenance(edition, source="field_assistant"),
    }
    candidate.reviewed_by = actor
    candidate.reviewed_at = now
    candidate.save(update_fields=[
        "candidate_entity_id", "candidate_entity_type", "target_type", "status",
        "supporting_properties", "reviewed_by", "reviewed_at", "updated_at",
    ])
    EntityResolutionCandidate.objects.select_for_update().filter(
        upload_item=candidate.upload_item, target_type=candidate.target_type,
        source_name=candidate.source_name, status=EntityResolutionCandidate.Status.PROPOSED,
    ).exclude(pk=candidate.pk).update(
        status=EntityResolutionCandidate.Status.REJECTED, reviewed_by=actor,
        reviewed_at=now, updated_at=now,
    )
    review_task = _review_task_for(candidate, lock=True)
    if review_task is not None:
        review_task.status = ReviewTask.Status.COMPLETED
        review_task.completed_by = actor
        review_task.completed_at = now
        review_task.details = {
            **dict(review_task.details or {}), "decision": action,
            "resolution_candidate_id": str(candidate.pk),
            "resolved_entity_id": str(entity.pk),
            **_decision_provenance(edition),
        }
        review_task.save(update_fields=["status", "completed_by", "completed_at", "details", "updated_at"])
    DecisionLog.objects.create(
        upload_item=candidate.upload_item, resolution_candidate=candidate,
        review_task=review_task, actor=actor, action=action,
        target_type=candidate.target_type, target_id=str(entity.pk), before=before,
        after={"status": candidate.status, "entity_id": str(entity.pk), **_decision_provenance(edition)},
        reason=reason or "在字段中确认身份，等待发布编辑草稿",
    )
    return entity


def _adopt_enrichment_value(candidate, *, edition, policy, actor, reason):
    """Reuse evidence rules while making the write destination explicit."""
    from catalog.services.field_enrichment.mutations import (
        _research_context_stale_reason, _validate_evidence,
    )
    from catalog.services.field_enrichment.policies import FIELD_POLICIES
    from catalog.services.field_enrichment.targets import current_field_value, get_target
    from catalog.services.field_enrichment.values import normalize_candidate_value, stable_json

    if candidate.status == EnrichmentCandidate.Status.ACCEPTED:
        if policy.value_kind in {"value", "entity_or_value"}:
            existing = _current_value(edition, policy)
            if policy.key == "publisher" and isinstance(existing, dict):
                existing = existing.get("name")
            if stable_json(existing) == stable_json(candidate.proposed_value):
                return
        raise FieldAssistantError("该建议已用于早前的编辑，请重新查找或手工编辑。")
    if candidate.status != EnrichmentCandidate.Status.PENDING:
        raise FieldAssistantError("该字段建议已经失效，请重新查找。")
    source_policy = FIELD_POLICIES.get(candidate.target_type, candidate.field_name)
    if candidate.candidate_kind != source_policy.candidate_kind or candidate.policy_version != source_policy.policy_version:
        raise FieldAssistantError("字段采用规则已变化，请重新查找。")
    if candidate.refresh_after and candidate.refresh_after < timezone.now():
        raise FieldAssistantError("建议依据已过期，请重新查找。")
    if candidate.identity_status not in {EnrichmentCandidate.IdentityStatus.CONFIRMED, EnrichmentCandidate.IdentityStatus.NOT_REQUIRED}:
        raise FieldAssistantError("请先确认当前对象的身份。")
    run_id = str((candidate.request_context or {}).get("research_run_id") or "")
    run = ResearchRun.objects.filter(pk=run_id).first() if run_id else None
    if _research_context_stale_reason(candidate, run):
        raise FieldAssistantError("当前编目信息已变化，请重新查找。")
    _validate_evidence(candidate, source_policy)
    value = normalize_candidate_value(source_policy.mutation_adapter, candidate.proposed_value)
    target = get_target(candidate.target_type, candidate.target_id, for_update=True)
    current = current_field_value(candidate.target_type, target, candidate.field_name)
    if stable_json(current) != stable_json(candidate.current_value):
        raise FieldAssistantError("字段已在建议产生后变化，请重新核对。")
    if policy.value_kind in {"value", "entity_or_value"}:
        _apply_scalar(edition, policy, value, actor=actor)
    else:
        names = _value_rows(value)
        entity = _metadata_entity(policy, names[0][0]) if len(names) == 1 else None
        if entity is None:
            raise FieldAssistantError("请先搜索并确认馆内对象，或创建后关联。")
        _link_entity(edition, policy, entity, actor=actor, source="field_assistant")
    revision = _latest_editorial_revision(edition) if _requires_editorial_revision(edition) else None
    candidate.proposed_value = value
    candidate.normalized_value = value
    candidate.status = EnrichmentCandidate.Status.ACCEPTED
    candidate.reviewed_by = actor
    candidate.reviewed_at = timezone.now()
    candidate.review_reason = str(reason or "")[:4000]
    candidate.accepted_authority_model = "catalog.EditorialRevision" if revision else target._meta.label
    candidate.accepted_authority_id = revision.pk if revision else target.pk
    candidate.save(update_fields=[
        "proposed_value", "normalized_value", "status", "reviewed_by", "reviewed_at",
        "review_reason", "accepted_authority_model", "accepted_authority_id", "updated_at",
    ])
    AuditEvent.objects.create(
        actor=actor, action="accept_field_enrichment_candidate",
        object_type="catalog.EnrichmentCandidate", object_id=str(candidate.pk),
        before={"status": EnrichmentCandidate.Status.PENDING},
        after={"status": candidate.status, "value": value, **_decision_provenance(edition)},
        request_id=str(candidate.request_id),
    )


def _metadata_entity(policy: AssistantFieldPolicy, label: str):
    normalized = _normalized(label)
    if policy.entity_type == "person":
        rows = [
            row
            for row in Person.objects.exclude(
                authority_status__in={
                    Person.AuthorityStatus.REJECTED,
                    Person.AuthorityStatus.MERGED,
                    Person.AuthorityStatus.ARCHIVED,
                }
            ).filter(Q(preferred_name__icontains=label) | Q(original_name__icontains=label))
            if normalized in {_normalized(row.preferred_name), _normalized(row.original_name)}
        ]
    elif policy.entity_type == "topic":
        rows = [row for row in Topic.objects.filter(name__icontains=label) if _normalized(row.name) == normalized]
    elif policy.entity_type == "publisher":
        rows = [
            row
            for row in PublisherAuthority.objects.filter(canonical_name__icontains=label)
            if _normalized(row.canonical_name) == normalized
        ]
    else:
        rows = []
    if len(rows) > 1:
        raise FieldAssistantError("馆内存在多个同名对象，请先确认具体身份。")
    return rows[0] if rows else None


def _bundle_created_entity(bundle, entity, *, label: str, confirmed_aliases=None, actor=None) -> None:
    object_types = {
        Person: "person",
        Topic: "topic",
        TheorySchool: "theory_school",
        KnowledgeNode: "knowledge_node",
        PublisherAuthority: "publisher",
    }
    object_type = next(
        (value for model, value in object_types.items() if isinstance(entity, model)),
        entity.__class__.__name__.casefold(),
    )
    previous = PublicationBundleItem.objects.filter(bundle=bundle, object_type=object_type, object_id=entity.pk).first()
    snapshot = {**(dict(previous.snapshot or {}) if previous else {}), "id": str(entity.pk), "label": label, "status": "draft"}
    if confirmed_aliases is not None and actor is not None:
        if not isinstance(confirmed_aliases, list) or any(not isinstance(value, str) for value in confirmed_aliases):
            raise FieldAssistantError("别名必须填写为名称列表。")
        snapshot["confirmed_aliases"] = [str(value).strip() for value in confirmed_aliases if str(value).strip()]
        snapshot["aliases_confirmed_by"] = str(actor.pk)
        snapshot["aliases_confirmed_at"] = timezone.now().isoformat()
    PublicationBundleItem.objects.update_or_create(
        bundle=bundle,
        object_type=object_type,
        object_id=entity.pk,
        defaults={
            "action": PublicationBundleItem.Action.CREATE,
            "label": label,
            "snapshot": snapshot,
            "minimum_complete": bool(label.strip()),
            "blockers": [] if label.strip() else ["名称不能为空"],
        },
    )


def _unique_named_slug(model, label: str) -> str:
    base = slugify(label, allow_unicode=True)[:160] or "catalog-entity"
    candidate = base
    counter = 1
    while model.objects.filter(slug=candidate).exists():
        counter += 1
        candidate = f"{base}-{counter}"
    return candidate


def _inline_duplicates(policy: AssistantFieldPolicy, label: str) -> list[dict[str, str]]:
    normalized = _normalized(label)
    rows: list[tuple[str, Any]] = []
    if policy.entity_type == "person":
        rows = [
            (row.preferred_name, row)
            for row in Person.objects.filter(
                Q(preferred_name__icontains=label) | Q(original_name__icontains=label)
            )[:10]
        ]
    elif policy.entity_type == "publisher":
        rows = [
            (row.canonical_name, row)
            for row in PublisherAuthority.objects.filter(canonical_name__icontains=label)[:10]
        ]
    elif policy.entity_type == "topic":
        rows = [(row.name, row) for row in Topic.objects.filter(name__icontains=label)[:10]]
    elif policy.entity_type == "theory":
        rows = [
            (row.name, row)
            for row in TheorySchool.objects.filter(
                Q(name__icontains=label) | Q(foreign_name__icontains=label)
            )[:10]
        ]
        rows.extend(
            (
                row.canonical_name_zh or row.canonical_name_en,
                row,
            )
            for row in KnowledgeNode.objects.filter(
                Q(canonical_name_zh__icontains=label)
                | Q(canonical_name_en__icontains=label),
                node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
            )[:10]
        )
    return [
        {"id": str(row.pk), "label": row_label, "exact": _normalized(row_label) == normalized}
        for row_label, row in rows
    ]


class FieldAssistantService:
    """Field-level facade over existing discovery and evidence stores.

    It never performs an external request while rendering a field and never
    publishes a projection. Mutations are explicit and transactional.
    """

    def lookup(self, request: FieldAssistantRequest) -> FieldAssistantResult:
        policy = get_field_policy(request.field_name)
        edition = _edition_for_request(request)
        item = _upload_item(edition, request.upload_item_id)
        prepared = _prepared_candidates(policy, edition, item)
        local = _local_candidates(policy, _search_terms(request, prepared), edition=edition)
        local = _without_rejected_matches(local, edition, policy)
        prepared = _without_rejected_matches(prepared, edition, policy)
        fingerprint = _context_fingerprint(request, edition)
        # Candidate/evidence content participates in the key, so accept/reject,
        # publication and a changed draft cannot reuse a prior aggregation.
        signature = json.dumps([fingerprint, request.default_limit, local, prepared], sort_keys=True, ensure_ascii=False, default=str)
        cache_key = "field-assistant:v304:" + hashlib.sha256(signature.encode("utf-8")).hexdigest()
        try:
            cached = cache.get(cache_key)
        except Exception:
            logger.warning("Field assistant cache unavailable; using current evidence", exc_info=True)
            cached = None
        if isinstance(cached, FieldAssistantResult):
            return cached
        results, more = _aggregate_candidates(
            [*local, *prepared],
            default_limit=request.default_limit,
        )
        result = FieldAssistantResult(
            field={
                "key": _canonical_field(policy),
                "label": policy.label,
                "lookup_label": policy.lookup_label,
                "adopt_label": policy.action_label,
                "create_label": f"创建{policy.create_label}" if policy.create_label else "",
                "strategy": list(policy.strategy_labels),
            },
            context_fingerprint=fingerprint,
            results=results,
            more_results=more,
            warnings=(),
        )
        try:
            cache.set(cache_key, result, timeout=60)
        except Exception:
            logger.warning("Field assistant result could not be cached", exc_info=True)
        return result

    def duplicate_check(
        self,
        *,
        field_name: str,
        label: str,
    ) -> list[dict[str, str]]:
        policy = get_field_policy(field_name)
        clean_label = " ".join(str(label or "").split()).strip()
        if not clean_label:
            raise FieldAssistantError("名称不能为空。")
        return _inline_duplicates(policy, clean_label)

    @transaction.atomic
    def create_and_link(
        self,
        *,
        edition_id,
        field_name: str,
        label: str,
        actor,
        details: dict[str, Any] | None = None,
        allow_possible_duplicate: bool = False,
    ) -> dict[str, Any]:
        """Create one draft authority inside the current cataloguing context.

        The entity and relation remain draft knowledge.  A publication bundle
        records that both must be reviewed and promoted with the holding.
        """

        from catalog.models import Edition

        policy = get_field_policy(field_name)
        clean_label = " ".join(str(label or "").split()).strip()
        if not clean_label:
            raise FieldAssistantError("名称不能为空。")
        edition = Edition.objects.select_for_update().select_related("work").get(pk=edition_id)
        edition.work = Work.objects.select_for_update().get(pk=edition.work_id)
        duplicates = _inline_duplicates(policy, clean_label)
        if duplicates and not allow_possible_duplicate:
            raise FieldAssistantError("馆内已有相近对象，请先确认是否为同一对象。")
        details = dict(details or {})
        if policy.entity_type == "person":
            entity = Person.objects.create(
                preferred_name=clean_label,
                sort_name=str(details.get("sort_name") or clean_label),
                original_name=str(details.get("original_name") or "").strip(),
                aliases=list(details.get("aliases") or []),
                authority_status=Person.AuthorityStatus.DRAFT,
            )
            ScholarProfile.objects.create(
                person=entity,
                slug=_unique_named_slug(ScholarProfile, clean_label),
                editorial_status="draft",
            )
        elif policy.entity_type == "publisher":
            entity = PublisherAuthority.objects.create(
                canonical_name=clean_label,
                aliases=list(details.get("aliases") or []),
                country=str(details.get("country") or "").strip(),
                editorial_status="draft",
            )
        elif policy.entity_type == "topic":
            entity = Topic.objects.create(
                name=clean_label,
                slug=_unique_named_slug(Topic, clean_label),
                description=str(details.get("description") or "").strip(),
                editorial_status="draft",
            )
        elif policy.entity_type == "theory":
            entity = KnowledgeNode.objects.create(
                canonical_name_zh=clean_label,
                canonical_name_en=str(details.get("foreign_name") or "").strip(),
                slug=_unique_named_slug(KnowledgeNode, clean_label),
                summary=str(details.get("description") or "").strip(),
                node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
                status=KnowledgePublicationStatus.DRAFT,
                created_by=actor,
            )
        else:
            raise FieldAssistantError("当前字段暂不支持在编目中创建对象。")

        _link_entity(edition, policy, entity, actor=actor, source="field_assistant_inline")
        bundle = ensure_publication_bundle(edition, actor=actor)
        _bundle_created_entity(bundle, entity, label=clean_label, confirmed_aliases=details.get("aliases"), actor=actor)
        value = _current_value(edition, policy)
        decision = record_edition_field_decision(
            edition,
            _canonical_field(policy),
            status=CatalogFieldDecision.Status.CONFIRMED,
            value=value,
            actor=actor,
            confirmation_method=CatalogFieldDecision.ConfirmationMethod.MANUAL,
            provenance=_decision_provenance(edition, source="field_assistant_inline", draft_entity=True),
            reason="在当前编目中创建并关联",
        )
        invalidated = invalidate_dependent_fields(
            edition,
            [_canonical_field(policy)],
            actor=actor,
        )
        return {
            "saved": True,
            "entity": {
                "type": policy.entity_type,
                "id": str(entity.pk),
                "label": clean_label,
                "status": "draft",
            },
            "decision_id": str(decision.pk),
            "bundle_id": str(bundle.pk),
            "invalidated_fields": invalidated,
            **_revision_response(edition),
        }

    @transaction.atomic
    def adopt(
        self,
        *,
        edition_id,
        field_name: str,
        source_type: str,
        source_id,
        actor,
        selected_value: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        from catalog.models import Edition

        policy = get_field_policy(field_name)
        source_type = str(source_type or "").strip()
        evidence: list[dict] = []
        if source_type == "enrichment":
            context = EnrichmentCandidate.objects.only("request_context").get(pk=source_id).request_context or {}
            if context.get("research_run_id"):
                ResearchRun.objects.select_for_update().filter(pk=context["research_run_id"]).first()
        edition = Edition.objects.select_for_update().select_related("work").get(pk=edition_id)
        edition.work = Work.objects.select_for_update().get(pk=edition.work_id)

        if source_type == "entity_resolution":
            candidate = (
                EntityResolutionCandidate.objects.select_related("upload_item")
                .prefetch_related()
                .get(pk=source_id)
            )
            if candidate.upload_item.edition_id != edition.pk:
                raise FieldAssistantError("实体建议不属于当前版本。")
            if candidate.target_type not in policy.entity_target_types:
                raise FieldAssistantError("实体建议不适用于当前字段。")
            if policy.contribution_role:
                role = str(
                    (candidate.supporting_properties or {}).get("contribution_role")
                    or Contribution.Role.AUTHOR
                )
                if role != policy.contribution_role:
                    raise FieldAssistantError("贡献角色与当前字段不一致。")
            evidence = _entity_evidence(candidate)
            action = (
                "create_draft"
                if candidate.candidate_entity_type.endswith("_draft")
                else "link_existing"
            )
            if _requires_editorial_revision(edition):
                entity = _adopt_resolution_in_revision(
                    self, candidate, edition=edition, policy=policy, actor=actor,
                    action=action, reason=reason,
                )
            else:
                try:
                    decide_entity_resolution(
                        candidate,
                        action=action,
                        target_type=candidate.target_type,
                        target_id=(candidate.candidate_entity_id if action == "link_existing" else ""),
                        confirm_identity=bool(candidate.target_type == "person"),
                        actor=actor,
                        reason=reason or "通过字段助手采用",
                    )
                except ResolutionDecisionError as exc:
                    raise FieldAssistantError(str(exc)) from exc
                candidate.refresh_from_db()
                entity = _resolution_entity(candidate)
                _link_entity(edition, policy, entity, actor=actor, source="field_assistant")
            if action == "create_draft":
                bundle = ensure_publication_bundle(edition, actor=actor)
                _bundle_created_entity(bundle, entity, label=str(entity))
        elif source_type.startswith("local_"):
            entity = _local_entity(source_type, source_id)
            state = entity.authority_status if isinstance(entity, Person) else getattr(entity, "editorial_status", getattr(entity, "status", "draft"))
            if state not in {"verified", "published"}:
                if state not in {"draft", "pending", "needs_review"} or not PublicationBundleItem.objects.filter(
                    bundle__edition=edition, bundle__status="draft", object_id=entity.pk,
                ).exists():
                    raise FieldAssistantError("该对象不是正式馆内记录或当前编目中的草稿，请重新查找。")
            evidence = [_evidence("馆内已有记录", "管理员从馆内对象中确认并关联")]
            _link_entity(edition, policy, entity, actor=actor, source="field_assistant")
        elif source_type == "metadata":
            candidate = MetadataCandidate.objects.select_for_update().select_related(
                "upload_item"
            ).prefetch_related("evidence_records").get(pk=source_id)
            if candidate.upload_item.edition_id != edition.pk:
                raise FieldAssistantError("字段建议不属于当前版本。")
            if candidate.field_name not in policy.metadata_fields:
                raise FieldAssistantError("字段建议不适用于当前字段。")
            evidence = _metadata_evidence(candidate)
            values = _metadata_value_rows(candidate, policy)
            chosen = selected_value or (values[0][0] if len(values) == 1 else "")
            if chosen and not any(_normalized(label) == _normalized(chosen) for label, _value in values):
                raise FieldAssistantError("所选值不属于当前建议，请重新查找或手工编辑字段。")
            if policy.value_kind in {"entity", "entity_or_value"} and chosen:
                entity = _metadata_entity(policy, chosen)
            else:
                entity = None
            if entity is not None:
                _link_entity(edition, policy, entity, actor=actor, source="field_assistant")
            elif policy.value_kind == "entity":
                raise FieldAssistantError("请先关联馆内对象，或新建后再采用。")
            else:
                if len(values) != 1 and not chosen:
                    raise FieldAssistantError("请先选择要采用的字段值。")
                raw_value = chosen or values[0][0]
                _apply_scalar(edition, policy, raw_value, actor=actor)
            _accept_metadata_candidate(candidate, actor=actor)
        elif source_type == "enrichment":
            candidate = EnrichmentCandidate.objects.select_for_update().prefetch_related(
                "evidence_records"
            ).get(pk=source_id)
            if not (
                candidate.field_name in policy.enrichment_fields
                and (
                    candidate.target_type == EnrichmentCandidate.TargetType.WORK
                    and candidate.target_id == edition.work_id
                    or candidate.target_type == EnrichmentCandidate.TargetType.EDITION
                    and candidate.target_id == edition.pk
                )
            ):
                raise FieldAssistantError("补充建议不属于当前字段或版本。")
            evidence = _enrichment_evidence(candidate)
            _adopt_enrichment_value(candidate, edition=edition, policy=policy, actor=actor, reason=reason)
        else:
            raise FieldAssistantError("未知的字段建议来源。")

        edition.refresh_from_db()
        value = _current_value(edition, policy)
        if value in (None, "", [], {}):
            raise FieldAssistantError("建议未能写入正式草稿字段。")
        decision = record_edition_field_decision(
            edition,
            _canonical_field(policy),
            status=CatalogFieldDecision.Status.CONFIRMED,
            value=value,
            actor=actor,
            confirmation_method=CatalogFieldDecision.ConfirmationMethod.CANDIDATE,
            provenance=_decision_provenance(
                edition, source="field_assistant", source_type=source_type,
                content_provenance="AI-assisted" if any(row.get("category") == "AI整理" for row in evidence) else "editorial",
            ),
            evidence_summary=evidence,
            candidate_type=source_type,
            candidate_id=source_id,
            reason=reason or "通过字段助手采用",
        )
        invalidated = invalidate_dependent_fields(
            edition,
            [_canonical_field(policy)],
            actor=actor,
        )
        return {
            "saved": True,
            "field": _canonical_field(policy),
            "value": value,
            "decision_id": str(decision.pk),
            "invalidated_fields": invalidated,
            **_revision_response(edition),
        }

    @transaction.atomic
    def reject(
        self,
        *,
        edition_id,
        field_name: str,
        source_type: str,
        source_id,
        actor,
        reason: str = "",
    ) -> dict[str, Any]:
        policy = get_field_policy(field_name)
        if source_type.startswith("local_"):
            from catalog.models import Edition

            edition = Edition.objects.select_for_update().select_related("work").get(pk=edition_id)
            entity = _local_entity(source_type, source_id)
            entity_type = source_type.removeprefix("local_")
            expected = {"theory_school", "knowledge_node"} if policy.entity_type == "theory" else {policy.entity_type}
            if entity_type not in expected:
                raise FieldAssistantError("该对象不属于当前字段。")
            label = str(getattr(entity, "preferred_name", None) or getattr(entity, "canonical_name", None)
                        or getattr(entity, "name", None) or getattr(entity, "canonical_name_zh", None)
                        or getattr(entity, "canonical_name_en", ""))
            AuditEvent.objects.create(
                actor=actor, action="field_assistant_local_rejected", object_type="Edition", object_id=str(edition.pk),
                after={"field_name": policy.key, "entity_type": entity_type, "entity_id": str(entity.pk),
                       "label": label, "context": _feedback_context(edition, policy), "reason": str(reason or "不是此对象")[:1000],
                       "knowledge_write": False},
            )
            status = "rejected"
        elif source_type == "metadata":
            candidate = MetadataCandidate.objects.select_related("upload_item").get(pk=source_id)
            if candidate.upload_item.edition_id != edition_id or candidate.field_name not in policy.metadata_fields:
                raise FieldAssistantError("字段建议不属于当前版本。")
            candidate = set_candidate_decision(candidate, action="reject", actor=actor)
            status = candidate.lifecycle
        elif source_type == "enrichment":
            candidate = EnrichmentCandidate.objects.get(pk=source_id)
            valid_target = (
                candidate.target_type == EnrichmentCandidate.TargetType.EDITION
                and str(candidate.target_id) == str(edition_id)
            )
            if not valid_target:
                from catalog.models import Edition

                work_id = Edition.objects.values_list("work_id", flat=True).get(pk=edition_id)
                valid_target = (
                    candidate.target_type == EnrichmentCandidate.TargetType.WORK
                    and candidate.target_id == work_id
                )
            if not valid_target or candidate.field_name not in policy.enrichment_fields:
                raise FieldAssistantError("补充建议不属于当前字段或版本。")
            candidate, _repeated = reject_enrichment_candidate(
                candidate,
                actor=actor,
                reason=reason,
            )
            status = candidate.status
        elif source_type == "entity_resolution":
            candidate = EntityResolutionCandidate.objects.select_related("upload_item").get(pk=source_id)
            if candidate.upload_item.edition_id != edition_id or candidate.target_type not in policy.entity_target_types:
                raise FieldAssistantError("实体建议不属于当前字段或版本。")
            try:
                result = decide_entity_resolution(
                    candidate,
                    action="reject",
                    target_type=candidate.target_type,
                    actor=actor,
                    reason=reason or "不是此对象",
                )
            except ResolutionDecisionError as exc:
                raise FieldAssistantError(str(exc)) from exc
            status = result.candidate.status
        else:
            raise FieldAssistantError("该建议已经变化，请重新查找。")
        return {"rejected": True, "status": status}
