"""Bounded, read-only aggregation for the Knowledge Studio workspace.

The studio is an editorial view over existing canonical, derived and candidate
stores.  It intentionally does not provide a second mutation path: editors
continue to use the established node, scholar, topic, relation and revision
endpoints linked from each object.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.db.models import Prefetch, Q, QuerySet

from catalog.models import (
    ClaimEvidence,
    CanonicalObjectRevision,
    CuratedClaim,
    DebateCandidate,
    DerivedClaim,
    EditorialRevision,
    EnrichmentCandidate,
    EvidenceSnippet,
    KnowledgeNode,
    KnowledgePublicationStatus,
    ProjectionState,
    PublicationState,
    ReadingPath,
    ReadingPathCandidate,
    ScholarProfile,
    Subdiscipline,
    TheoryReviewTask,
    Topic,
    Work,
)
from catalog.services.evidence_envelope import evidence_span_envelope
from catalog.services.reading_paths import reading_path_stage_groups


NODE_OBJECT_TYPES = {
    "theory": KnowledgeNode.NodeType.THEORY_TRADITION,
    "concept": KnowledgeNode.NodeType.CONCEPT,
    "debate": KnowledgeNode.NodeType.DEBATE,
    "research_problem": KnowledgeNode.NodeType.RESEARCH_PROBLEM,
}
OBJECT_TYPES = (
    *NODE_OBJECT_TYPES,
    "scholar",
    "subdiscipline",
    "topic",
    "reading_path",
    "work",
)
DEFAULT_DIRECTORY_LIMIT = 40
MAX_DIRECTORY_LIMIT = 50
MAX_SECTION_ROWS = 12


def _bounded_limit(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_DIRECTORY_LIMIT
    return max(1, min(parsed, MAX_DIRECTORY_LIMIT))


def _valid_uuid(value: Any) -> str | None:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return None


def _clip(value: Any, limit: int = 1200) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _bounded_json(value: Any, *, depth: int = 0) -> Any:
    """Keep stored preview/candidate JSON useful without returning an unbounded blob."""

    # Reading path stages and Work editions both have one meaningful nested
    # row level below their grouping object.  Keep those structured while the
    # row/count caps above still bound the response.
    if depth >= 6:
        return _clip(value, 300)
    if isinstance(value, dict):
        return {
            str(key): _bounded_json(item, depth=depth + 1)
            for key, item in list(value.items())[:30]
        }
    if isinstance(value, (list, tuple)):
        return [_bounded_json(item, depth=depth + 1) for item in list(value)[:20]]
    if isinstance(value, str):
        return _clip(value)
    return value


def _node_directory(query: str, object_type: str, limit: int) -> list[dict[str, Any]]:
    queryset = KnowledgeNode.objects.select_related("primary_discipline").filter(
        node_type=NODE_OBJECT_TYPES[object_type]
    )
    if query:
        queryset = queryset.filter(
            Q(canonical_name_zh__icontains=query)
            | Q(canonical_name_en__icontains=query)
            | Q(slug__icontains=query)
            | Q(aliases__alias__icontains=query)
        ).distinct()
    return [
        {
            "id": str(row.id),
            "object_type": object_type,
            "label": row.canonical_name_zh,
            "secondary_label": row.canonical_name_en,
            "status": row.status,
            "updated_at": row.updated_at,
        }
        for row in queryset.order_by("sort_order", "canonical_name_zh")[:limit]
    ]


def _scholar_directory(query: str, limit: int) -> list[dict[str, Any]]:
    queryset = ScholarProfile.objects.select_related("person")
    if query:
        queryset = queryset.filter(
            Q(person__preferred_name__icontains=query)
            | Q(person__original_name__icontains=query)
            | Q(slug__icontains=query)
        )
    return [
        {
            "id": str(row.id),
            "object_type": "scholar",
            "label": row.person.preferred_name,
            "secondary_label": row.person.original_name,
            "status": row.editorial_status,
            "updated_at": row.updated_at,
        }
        for row in queryset.order_by("person__sort_name", "person__preferred_name")[:limit]
    ]


def _topic_directory(query: str, limit: int) -> list[dict[str, Any]]:
    queryset = Topic.objects.all()
    if query:
        queryset = queryset.filter(
            Q(name__icontains=query)
            | Q(slug__icontains=query)
            | Q(search_aliases__icontains=query)
        )
    return [
        {
            "id": str(row.id),
            "object_type": "topic",
            "label": row.name,
            "secondary_label": "",
            "status": row.editorial_status,
            "updated_at": row.updated_at,
        }
        for row in queryset.order_by("name")[:limit]
    ]


def _subdiscipline_directory(query: str, limit: int) -> list[dict[str, Any]]:
    queryset = Subdiscipline.objects.select_related("discipline", "parent")
    if query:
        queryset = queryset.filter(
            Q(name__icontains=query)
            | Q(foreign_name__icontains=query)
            | Q(slug__icontains=query)
            | Q(search_aliases__icontains=query)
        )
    return [
        {
            "id": str(row.id),
            "object_type": "subdiscipline",
            "label": row.name,
            "secondary_label": row.foreign_name or row.discipline.name,
            "status": row.editorial_status,
            "updated_at": row.updated_at,
        }
        for row in queryset.order_by(
            "discipline__sort_order", "discipline__name", "name"
        )[:limit]
    ]


def _reading_path_directory(query: str, limit: int) -> list[dict[str, Any]]:
    queryset = ReadingPath.objects.select_related("primary_discipline")
    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(introduction__icontains=query)
            | Q(audience__icontains=query)
            | Q(slug__icontains=query)
        )
    return [
        {
            "id": str(row.id),
            "object_type": "reading_path",
            "label": row.title,
            "secondary_label": (
                row.primary_discipline.name
                if row.primary_discipline_id
                else row.audience
            ),
            "status": row.status,
            "updated_at": row.updated_at,
        }
        for row in queryset.order_by("sort_order", "title")[:limit]
    ]


def _important_work_queryset() -> QuerySet[Work]:
    """Works with an explicit Knowledge Core or public-curation signal."""

    return Work.objects.filter(
        Q(is_featured=True)
        | Q(curated_claims__isnull=False)
        | Q(node_relations__isnull=False)
        | Q(topic_relations__isnull=False)
        | Q(reading_path_items__isnull=False)
    ).distinct()


def _work_status(work: Work) -> str:
    states = [edition.state for edition in work.editions.all()]
    if PublicationState.PUBLISHED in states:
        return PublicationState.PUBLISHED
    if PublicationState.READY in states:
        return PublicationState.READY
    return PublicationState.DRAFT


def _work_directory(query: str, limit: int) -> list[dict[str, Any]]:
    queryset = _important_work_queryset().prefetch_related("editions")
    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(subtitle__icontains=query)
            | Q(original_title__icontains=query)
            | Q(uniform_title__icontains=query)
            | Q(search_aliases__icontains=query)
        )
    return [
        {
            "id": str(row.id),
            "object_type": "work",
            "label": row.title,
            "secondary_label": row.original_title or row.get_document_type_display(),
            "status": _work_status(row),
            "updated_at": row.updated_at,
        }
        for row in queryset.order_by("title")[:limit]
    ]


def _directory(*, query: str, object_type: str, limit: int) -> tuple[list[dict[str, Any]], dict[str, int]]:
    node_counts = {
        key: KnowledgeNode.objects.filter(node_type=node_type).count()
        for key, node_type in NODE_OBJECT_TYPES.items()
    }
    counts = {
        **node_counts,
        "scholar": ScholarProfile.objects.count(),
        "subdiscipline": Subdiscipline.objects.count(),
        "topic": Topic.objects.count(),
        "reading_path": ReadingPath.objects.count(),
        "work": _important_work_queryset().count(),
    }
    requested_types = [object_type] if object_type in OBJECT_TYPES else list(OBJECT_TYPES)
    rows: list[dict[str, Any]] = []
    # Each source is sliced before materialization and the combined result is
    # sliced again.  An `all` request therefore cannot fan out without bound.
    for kind in requested_types:
        if kind in NODE_OBJECT_TYPES:
            rows.extend(_node_directory(query, kind, limit))
        elif kind == "scholar":
            rows.extend(_scholar_directory(query, limit))
        elif kind == "topic":
            rows.extend(_topic_directory(query, limit))
        elif kind == "subdiscipline":
            rows.extend(_subdiscipline_directory(query, limit))
        elif kind == "reading_path":
            rows.extend(_reading_path_directory(query, limit))
        else:
            rows.extend(_work_directory(query, limit))
    rows.sort(key=lambda row: (str(row["label"]).casefold(), row["object_type"], row["id"]))
    return rows[:limit], counts


def _evidence_payload(span) -> dict[str, Any]:
    payload = evidence_span_envelope(span).as_dict()
    payload["text"] = _clip(payload["text"], 1600)
    return payload


def _snippet_payload(snippet: EvidenceSnippet) -> dict[str, Any]:
    page = snippet.page_number
    return {
        "id": str(snippet.id),
        "kind": "collection_text_compat",
        "source": {
            "work_id": str(snippet.work_id),
            "work_title": snippet.work.title,
            "asset_id": str(snippet.file_id),
        },
        "text": _clip(snippet.quote, 1600),
        "locator": {
            "page": page,
            "printed_page_label": snippet.printed_page_label,
            "bbox": snippet.bounding_box,
        },
        "quality": {
            "ocr_confidence": snippet.ocr_confidence,
            "semantic_confidence": snippet.semantic_confidence,
            "review_status": snippet.review_status,
        },
        "provenance": {"extraction_method": snippet.extraction_method},
        "reader_url": f"/reader/{snippet.file_id}?page={page}",
        "pdf_url": f"/api/catalog/assets/{snippet.file_id}/manifest/",
    }


def _claim_evidence_prefetch() -> Prefetch:
    return Prefetch(
        "evidence_links",
        queryset=ClaimEvidence.objects.select_related(
            "evidence_span__page",
            "evidence_span__document_revision__asset__edition__work",
        ).prefetch_related(
            "evidence_span__document_revision__asset__edition__contributions__person"
        ).order_by("sort_order", "created_at")[:MAX_SECTION_ROWS],
        to_attr="studio_evidence_links",
    )


def _curated_claims(queryset: QuerySet[CuratedClaim]) -> list[dict[str, Any]]:
    rows = queryset.prefetch_related(_claim_evidence_prefetch()).order_by(
        "kind", "sort_order", "created_at"
    )[:MAX_SECTION_ROWS]
    return [
        {
            "id": str(row.id),
            "kind": row.kind,
            "title": row.title,
            "proposition": _clip(row.proposition, 1600),
            "editorial_note": _clip(row.editorial_note, 800),
            "status": row.status,
            "adopted_from": str(row.adopted_from_id) if row.adopted_from_id else None,
            "evidence": [
                {
                    **_evidence_payload(link.evidence_span),
                    "claim_role": link.role,
                    "claim_confidence": link.confidence,
                }
                for link in row.studio_evidence_links
            ],
        }
        for row in rows
    ]


def _derived_claims(queryset: QuerySet[DerivedClaim]) -> list[dict[str, Any]]:
    rows = queryset.filter(status=DerivedClaim.Status.ACTIVE).select_related(
        "primary_evidence__page",
        "primary_evidence__document_revision__asset__edition__work",
    ).prefetch_related(
        "primary_evidence__document_revision__asset__edition__contributions__person"
    ).order_by("-importance_score", "-quality_score", "created_at")[:MAX_SECTION_ROWS]
    return [
        {
            "id": str(row.id),
            "proposition": _clip(row.proposition, 1600),
            "claim_type": row.claim_type,
            "attribution": row.attribution,
            "polarity": row.polarity,
            "qualifiers": _bounded_json(row.qualifiers),
            "quality_score": row.quality_score,
            "importance_score": row.importance_score,
            "shadow": row.shadow,
            "document_revision_id": str(row.document_revision_id),
            "evidence": _evidence_payload(row.primary_evidence),
        }
        for row in rows
    ]


def _claim_evidence(
    *,
    curated: list[dict[str, Any]],
    derived: list[dict[str, Any]],
    existing: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    rows = list(existing or [])
    for claim in curated:
        rows.extend(claim.get("evidence") or [])
    for claim in derived:
        evidence = claim.get("evidence")
        if evidence:
            rows.append(evidence)
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (str(row.get("kind") or ""), str(row.get("id") or ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
        if len(result) >= MAX_SECTION_ROWS:
            break
    return result


def _projection_payload(object_type: str, object_id) -> tuple[list[str], list[dict[str, Any]]]:
    from catalog.services.dependency_engine import projection_types_for

    projection_types = projection_types_for(object_type)
    labels = dict(ProjectionState.ProjectionType.choices)
    names = {
        ProjectionState.ProjectionType.QUERY_LEXICON: "QueryLexicon",
        ProjectionState.ProjectionType.FULLTEXT: "Fulltext",
        ProjectionState.ProjectionType.SEMANTIC: "Semantic",
        ProjectionState.ProjectionType.CLAIM_INDEX: "Claim Index",
        ProjectionState.ProjectionType.KNOWLEDGE_GRAPH: "Knowledge Graph",
        ProjectionState.ProjectionType.TIMELINE: "Timeline",
        ProjectionState.ProjectionType.RECOMMENDATION: "Recommendation",
        ProjectionState.ProjectionType.READING_PATH_SUPPORT: "Reading Path support",
        ProjectionState.ProjectionType.PUBLIC: "Public",
    }
    state_by_type = {
        row.projection_type: row
        for row in ProjectionState.objects.filter(
            object_type=object_type,
            object_id=object_id,
            projection_type__in=projection_types,
        )
    }
    rows: list[dict[str, Any]] = []
    for projection_type in projection_types:
        state = state_by_type.get(projection_type)
        rows.append(
            {
                "type": projection_type,
                "label": labels.get(projection_type, projection_type),
                "name": names.get(projection_type, projection_type),
                "status": state.status if state else "not_materialized",
                "source_revision": state.source_revision if state else 0,
                "projected_revision": state.projected_revision if state else 0,
                "lag": (
                    max(0, state.source_revision - state.projected_revision)
                    if state
                    else 0
                ),
                "last_error_code": state.last_error_code if state else "",
            }
        )
    return [names.get(value, value) for value in projection_types], rows


def _frontend_impact(
    *,
    object_type: str,
    object_id,
    public_visibility: bool,
    modules: list[str],
    targets: list[dict[str, Any]],
) -> dict[str, Any]:
    projections, states = _projection_payload(object_type, object_id)
    return {
        "public_visibility": public_visibility,
        "modules": modules,
        "projections": projections,
        "projection_states": states,
        "targets": targets[:MAX_SECTION_ROWS],
    }


def _mutation_contract(
    target_type: str,
    target_id,
    *,
    published: bool,
) -> dict[str, Any]:
    current_revision = (
        CanonicalObjectRevision.objects.filter(
            object_type=target_type,
            object_id=target_id,
        )
        .values_list("current_revision", flat=True)
        .first()
        or 0
    )
    return {
        "target_type": target_type,
        "target_id": str(target_id),
        "current_revision": current_revision,
        "published_changes_require_revision": published,
        "draft_url": "/catalog/admin/editorial-revisions/",
        "revisions_url": (
            "/catalog/admin/editorial-revisions/"
            f"?target_type={target_type}&target_id={target_id}"
        ),
        "single_editor_publish": True,
        "canonical_commit_is_atomic": True,
        "dependency_propagation_on_publish": True,
    }


def _revision_rows(target_type: str, target_id) -> list[dict[str, Any]]:
    current_revision = (
        CanonicalObjectRevision.objects.filter(
            object_type=target_type,
            object_id=target_id,
        )
        .values_list("current_revision", flat=True)
        .first()
        or 0
    )
    return [
        {
            "id": str(row.id),
            "revision": row.revision,
            "base_revision": row.base_revision,
            "status": row.status,
            "changed_fields": row.changed_fields,
            "change_note": row.change_note,
            "created_at": row.created_at,
            "published_at": row.published_at,
            "patch": _bounded_json(row.patch),
            "has_conflict": (
                row.status == EditorialRevision.Status.DRAFT
                and row.base_revision != current_revision
            ),
            "publish_url": (
                f"/catalog/admin/editorial-revisions/{row.id}/publish/"
                if row.status == EditorialRevision.Status.DRAFT
                else ""
            ),
        }
        for row in EditorialRevision.objects.filter(
            target_type=target_type,
            target_id=target_id,
        ).order_by("-revision")[:MAX_SECTION_ROWS]
    ]


def _latest_preview(target_type: str, target_id, canonical: dict[str, Any]) -> dict[str, Any]:
    draft = EditorialRevision.objects.filter(
        target_type=target_type,
        target_id=target_id,
        status=EditorialRevision.Status.DRAFT,
    ).order_by("-revision").first()
    return {
        "source": "editorial_revision" if draft else "canonical",
        "revision_id": str(draft.id) if draft else None,
        "materialized": _bounded_json(draft.materialized_preview if draft else canonical),
    }


def _enrichment_candidates(target_type: str, target_id) -> list[dict[str, Any]]:
    return [
        {
            "id": str(row.id),
            "candidate_type": "enrichment",
            "field_name": row.field_name,
            "candidate_kind": row.candidate_kind,
            "proposed_value": _bounded_json(row.proposed_value),
            "confidence": row.confidence,
            "conflicts": _bounded_json(row.conflicts),
            "status": row.status,
            "source": row.source_class,
        }
        for row in EnrichmentCandidate.objects.filter(
            target_type=target_type,
            target_id=target_id,
            status=EnrichmentCandidate.Status.PENDING,
        ).order_by("-confidence", "created_at")[:MAX_SECTION_ROWS]
    ]


def _node_selection(node: KnowledgeNode, object_type: str) -> dict[str, Any]:
    canonical = {
        "canonical_name_zh": node.canonical_name_zh,
        "canonical_name_en": node.canonical_name_en,
        "node_type": node.node_type,
        "slug": node.slug,
        "summary": node.summary,
        "definition": node.definition,
        "core_questions": node.core_questions,
        "basic_propositions": node.basic_propositions,
        "theoretical_boundary": node.theoretical_boundary,
        "period": {"start_year": node.start_year, "end_year": node.end_year, "label": node.period_label},
        "primary_discipline": node.primary_discipline.name if node.primary_discipline_id else None,
    }
    relations: list[dict[str, Any]] = [
        {
            "id": str(row.id),
            "kind": "node_discipline",
            "label": row.get_relation_type_display(),
            "target": row.discipline.name,
            "status": row.status,
            "description": _clip(row.discipline_specific_summary, 600),
        }
        for row in node.discipline_links.select_related("discipline").order_by(
            "sort_order", "discipline__name"
        )[:MAX_SECTION_ROWS]
    ]
    for row in node.subdiscipline_links.select_related(
        "subdiscipline__discipline"
    ).order_by("sort_order", "subdiscipline__name")[:MAX_SECTION_ROWS]:
        relations.append(
            {
                "id": str(row.id),
                "kind": "node_subdiscipline",
                "label": row.relation_role or "相关子学科",
                "target": row.subdiscipline.name,
                "status": row.status,
                "is_primary": row.is_primary,
                "description": row.source,
            }
        )
    for row in node.topic_links.select_related("topic").order_by(
        "sort_order", "topic__name"
    )[:MAX_SECTION_ROWS]:
        relations.append(
            {
                "id": str(row.id),
                "kind": "node_topic",
                "label": row.relation_label or "相关主题",
                "target": row.topic.name,
                "status": row.status,
                "description": row.source,
            }
        )
    relation_limit = MAX_SECTION_ROWS * 3
    outgoing_limit = max(0, relation_limit - len(relations))
    for row in node.outgoing_relations.select_related("target_node").order_by(
        "relation_type"
    )[:outgoing_limit]:
        relations.append({
            "id": str(row.id), "kind": "knowledge_relation", "direction": "outgoing",
            "label": row.get_relation_type_display(), "target": row.target_node.canonical_name_zh,
            "status": row.status, "description": _clip(row.description, 600),
        })
    remaining = max(0, relation_limit - len(relations))
    if remaining:
        for row in node.incoming_relations.select_related("source_node").order_by("relation_type")[:remaining]:
            relations.append({
                "id": str(row.id), "kind": "knowledge_relation", "direction": "incoming",
                "label": row.get_relation_type_display(), "target": row.source_node.canonical_name_zh,
                "status": row.status, "description": _clip(row.description, 600),
            })
    work_relations = [
        {
            "id": str(row.id), "kind": "work_node", "label": row.get_role_display(),
            "target": row.work.title, "status": row.status, "is_primary": row.is_primary,
        }
        for row in node.work_relations.select_related("work").order_by("-is_primary", "work__title")[:MAX_SECTION_ROWS]
    ]
    people = [
        {
            "id": str(row.id), "kind": "person_node", "label": row.relation_label or "相关学者",
            "target": row.person.preferred_name, "status": row.status,
            "is_representative": row.is_representative,
        }
        for row in node.person_relations.select_related("person").order_by("sort_order")[:MAX_SECTION_ROWS]
    ]
    snippets = [
        _snippet_payload(row)
        for row in node.evidence.select_related("work", "file").order_by("page_number", "created_at")[:MAX_SECTION_ROWS]
    ]
    derived = DerivedClaim.objects.filter(work__node_relations__node=node).distinct()
    curated_claims = _curated_claims(CuratedClaim.objects.filter(node=node))
    derived_claims = _derived_claims(derived)
    candidates = _enrichment_candidates(EnrichmentCandidate.TargetType.KNOWLEDGE_NODE, node.id)
    candidates.extend(
        {
            "id": str(row.id),
            "candidate_type": "theory_review",
            "field_name": row.task_type,
            "proposed_value": row.suggested_node_name or row.suggested_relation_type,
            "confidence": row.confidence,
            "conflicts": [],
            "status": row.status,
            "source": "library_research",
            "evidence": _clip(row.evidence_text, 1200),
            "evidence_pages": row.evidence_pages[:20],
        }
        for row in node.review_tasks.filter(
            status__in=[TheoryReviewTask.TaskStatus.PENDING, TheoryReviewTask.TaskStatus.NEEDS_CHANGES]
        ).order_by("-confidence", "created_at")[:MAX_SECTION_ROWS]
    )
    if object_type == "debate":
        candidates.extend(
            {
                "id": str(row.id),
                "candidate_type": "debate_discovery",
                "field_name": "canonical_question",
                "proposed_value": _clip(row.canonical_question, 1200),
                "confidence": row.quality_score,
                "importance": row.importance_score,
                "conflicts": {"score": row.conflict_score},
                "status": row.status,
                "source": "debate_discovery",
            }
            for row in DebateCandidate.objects.filter(
                suggested_node=node,
                status=DebateCandidate.Status.PENDING,
            ).order_by("-importance_score", "created_at")[:MAX_SECTION_ROWS]
        )
    target_type = EditorialRevision.TargetType.KNOWLEDGE_NODE
    public_modules = {
        "theory": ["定义", "核心问题", "发展脉络", "人物", "概念", "主要批评", "阅读路径"],
        "concept": ["定义", "相关理论", "相关作品", "原文证据"],
        "debate": ["规范问题", "支持", "相斥", "限定", "代表作品", "原文证据"],
        "research_problem": ["问题定义", "理论解释", "相关作品", "原文证据"],
    }[object_type]
    return {
        "id": str(node.id),
        "object_type": object_type,
        "label": node.canonical_name_zh,
        "status": node.status,
        "canonical": _bounded_json(canonical),
        "relations": (relations + work_relations + people)[: MAX_SECTION_ROWS * 3],
        "evidence": _claim_evidence(
            curated=curated_claims,
            derived=derived_claims,
            existing=snippets,
        ),
        "claims": {
            "curated": curated_claims,
            "derived": derived_claims,
            "derived_is_machine_only": True,
        },
        "ai_candidates": candidates[:MAX_SECTION_ROWS],
        "revisions": _revision_rows(target_type, node.id),
        "preview": _latest_preview(target_type, node.id, canonical),
        "frontend_impact": _frontend_impact(
            object_type=EditorialRevision.TargetType.KNOWLEDGE_NODE,
            object_id=node.id,
            public_visibility=node.status == KnowledgePublicationStatus.PUBLISHED,
            modules=public_modules,
            targets=[
                {
                    "label": f"{node.get_node_type_display()}公开页",
                    "url": f"/theories/nodes/{node.slug}",
                    "modules": public_modules,
                },
                {
                    "label": "知识图谱",
                    "url": f"/theories/graph?center={node.slug}",
                    "modules": ["关系", "关联人物", "关联作品"],
                },
            ],
        ),
        "mutation_contract": _mutation_contract(
            EditorialRevision.TargetType.KNOWLEDGE_NODE,
            node.id,
            published=node.status == KnowledgePublicationStatus.PUBLISHED,
        ),
        "editor_url": f"/admin/theory-nodes?node={node.id}&node_type={node.node_type}",
        "preview_url": f"/theories/nodes/{node.slug}",
        "related_editor_urls": [
            {"label": "关系", "url": f"/admin/theory-relations?node={node.id}"},
            {"label": "时间轴", "url": f"/admin/theory-timeline?node={node.id}"},
            {"label": "阅读路径", "url": "/admin/reading-paths"},
        ],
    }


def _scholar_selection(profile: ScholarProfile) -> dict[str, Any]:
    person = profile.person
    canonical = {
        "preferred_name": person.preferred_name,
        "original_name": person.original_name,
        "aliases": person.aliases,
        "birth_year": person.birth_year,
        "death_year": person.death_year,
        "biography": person.biography,
        "slug": profile.slug,
        "short_description": profile.short_description,
        "affiliations": profile.affiliations,
        "key_concerns": profile.key_concerns,
        "timeline": profile.timeline,
        "featured_quote": profile.featured_quote,
        "quote_source": profile.quote_source,
    }
    node_relations = [
        {
            "id": str(row.id), "kind": "person_node", "label": row.relation_label or "学术关系",
            "target": row.node.canonical_name_zh, "status": row.status,
            "is_representative": row.is_representative,
        }
        for row in person.node_relations.select_related("node").order_by("sort_order")[:MAX_SECTION_ROWS]
    ]
    topic_relations = [
        {
            "id": str(row.id), "kind": "person_topic", "label": row.relation_label or "相关主题",
            "target": row.topic.name, "status": row.review_status, "is_primary": row.is_primary,
        }
        for row in person.topic_relations.select_related("topic").order_by("-is_primary", "topic__name")[:MAX_SECTION_ROWS]
    ]
    work_ids = person.contributions.filter(approved=True).values_list("edition__work_id", flat=True)
    derived = DerivedClaim.objects.filter(work_id__in=work_ids).distinct()
    curated_claims = _curated_claims(CuratedClaim.objects.filter(scholar=profile))
    derived_claims = _derived_claims(derived)
    target_type = EditorialRevision.TargetType.SCHOLAR_PROFILE
    return {
        "id": str(profile.id),
        "object_type": "scholar",
        "label": person.preferred_name,
        "status": profile.editorial_status,
        "canonical": _bounded_json(canonical),
        "relations": (node_relations + topic_relations)[: MAX_SECTION_ROWS * 2],
        "evidence": _claim_evidence(curated=curated_claims, derived=derived_claims),
        "claims": {
            "curated": curated_claims,
            "derived": derived_claims,
            "derived_is_machine_only": True,
        },
        "ai_candidates": _enrichment_candidates(EnrichmentCandidate.TargetType.PERSON, person.id),
        "revisions": _revision_rows(target_type, profile.id),
        "preview": _latest_preview(target_type, profile.id, canonical),
        "frontend_impact": _frontend_impact(
            object_type=EditorialRevision.TargetType.SCHOLAR_PROFILE,
            object_id=profile.id,
            public_visibility=profile.editorial_status == KnowledgePublicationStatus.PUBLISHED,
            modules=["学术位置", "核心作品", "核心观点", "主要贡献", "批评与回应", "建议阅读顺序"],
            targets=[
                {
                    "label": "学者公开页",
                    "url": f"/scholars/{profile.slug}",
                    "modules": ["身份与译名", "作品", "核心观点", "理论贡献", "批评与回应", "阅读顺序"],
                },
            ],
        ),
        "mutation_contract": _mutation_contract(
            EditorialRevision.TargetType.SCHOLAR_PROFILE,
            profile.id,
            published=profile.editorial_status == KnowledgePublicationStatus.PUBLISHED,
        ),
        "editor_url": f"/admin/scholars/{profile.id}",
        "preview_url": f"/scholars/{profile.slug}",
        "related_editor_urls": [
            {"label": "理论关系", "url": f"/admin/theory-relations?scholar={profile.id}"},
            {"label": "阅读路径", "url": "/admin/reading-paths"},
        ],
    }


def _topic_selection(topic: Topic) -> dict[str, Any]:
    canonical = {
        "name": topic.name,
        "slug": topic.slug,
        "description": topic.description,
        "problem_statement": topic.problem_statement,
        "core_questions": topic.core_questions,
        "research_dimensions": topic.research_dimensions,
        "methods": topic.methods,
        "formation_context": topic.formation_context,
        "key_concepts": topic.key_concepts,
    }
    node_relations = [
        {
            "id": str(row.id), "kind": "node_topic", "label": row.relation_label or "相关知识节点",
            "target": row.node.canonical_name_zh, "status": row.status,
        }
        for row in topic.knowledge_node_links.select_related("node").order_by("sort_order")[:MAX_SECTION_ROWS]
    ]
    work_relations = [
        {
            "id": str(row.id), "kind": "work_topic", "label": "相关作品",
            "target": row.work.title, "status": row.review_status, "is_primary": row.is_primary,
        }
        for row in topic.work_relations.select_related("work").order_by("-is_primary", "work__title")[:MAX_SECTION_ROWS]
    ]
    derived = DerivedClaim.objects.filter(work__topic_relations__topic=topic).distinct()
    curated_claims = _curated_claims(CuratedClaim.objects.filter(topic=topic))
    derived_claims = _derived_claims(derived)
    target_type = EditorialRevision.TargetType.TOPIC
    return {
        "id": str(topic.id),
        "object_type": "topic",
        "label": topic.name,
        "status": topic.editorial_status,
        "canonical": _bounded_json(canonical),
        "relations": (node_relations + work_relations)[: MAX_SECTION_ROWS * 2],
        "evidence": _claim_evidence(curated=curated_claims, derived=derived_claims),
        "claims": {
            "curated": curated_claims,
            "derived": derived_claims,
            "derived_is_machine_only": True,
        },
        "ai_candidates": _enrichment_candidates(EnrichmentCandidate.TargetType.TOPIC, topic.id),
        "revisions": _revision_rows(target_type, topic.id),
        "preview": _latest_preview(target_type, topic.id, canonical),
        "frontend_impact": _frontend_impact(
            object_type=EditorialRevision.TargetType.TOPIC,
            object_id=topic.id,
            public_visibility=topic.editorial_status == KnowledgePublicationStatus.PUBLISHED,
            modules=["核心研究问题", "不同理论解释", "相关作品", "观点", "阅读入口"],
            targets=[
                {
                    "label": "主题公开页",
                    "url": f"/topics/{topic.slug}",
                    "modules": ["问题范围", "理论视角", "学者", "作品", "Claims", "争论", "阅读路径"],
                },
            ],
        ),
        "mutation_contract": _mutation_contract(
            EditorialRevision.TargetType.TOPIC,
            topic.id,
            published=topic.editorial_status == KnowledgePublicationStatus.PUBLISHED,
        ),
        "editor_url": f"/admin/topics/{topic.id}",
        "preview_url": f"/topics/{topic.slug}",
        "related_editor_urls": [
            {"label": "关系", "url": f"/admin/theory-relations?topic={topic.id}"},
            {"label": "阅读路径", "url": "/admin/reading-paths"},
        ],
    }


def _subdiscipline_selection(subdiscipline: Subdiscipline) -> dict[str, Any]:
    canonical = {
        "name": subdiscipline.name,
        "foreign_name": subdiscipline.foreign_name,
        "slug": subdiscipline.slug,
        "description": subdiscipline.description,
        "discipline": subdiscipline.discipline.name,
        "parent": subdiscipline.parent.name if subdiscipline.parent_id else None,
        "research_object": subdiscipline.research_object,
        "core_questions": subdiscipline.core_questions,
        "formation_period": subdiscipline.formation_period,
        "research_directions": subdiscipline.research_directions,
        "methods": subdiscipline.methods,
        "representative_issues": subdiscipline.representative_issues,
    }
    node_relations = [
        {
            "id": str(row.id),
            "kind": "node_subdiscipline",
            "label": row.relation_role or "相关理论或概念",
            "target": row.node.canonical_name_zh,
            "status": row.status,
            "description": row.source,
        }
        for row in subdiscipline.knowledge_node_links.select_related("node").order_by(
            "sort_order", "node__canonical_name_zh"
        )[:MAX_SECTION_ROWS]
    ]
    work_relations = [
        {
            "id": str(row.id),
            "kind": "work_subdiscipline",
            "label": "主要作品" if row.is_primary else "相关作品",
            "target": row.work.title,
            "status": row.review_status,
            "description": _clip(row.evidence_text or row.source, 600),
        }
        for row in subdiscipline.work_relations.select_related("work").order_by(
            "-is_primary", "work__title"
        )[:MAX_SECTION_ROWS]
    ]
    person_relations = [
        {
            "id": str(row.id),
            "kind": "person_subdiscipline",
            "label": row.relation_label or "相关学者",
            "target": row.person.preferred_name,
            "status": row.review_status,
            "description": row.source,
        }
        for row in subdiscipline.person_relations.select_related("person").order_by(
            "person__sort_name", "person__preferred_name"
        )[:MAX_SECTION_ROWS]
    ]
    topic_relations = [
        {
            "id": str(row.id),
            "kind": "topic_subdiscipline",
            "label": row.relation_label or "相关主题",
            "target": row.topic.name,
            "status": row.review_status,
        }
        for row in subdiscipline.topic_relations.select_related("topic").order_by(
            "topic__name"
        )[:MAX_SECTION_ROWS]
    ]
    work_ids = subdiscipline.work_relations.values_list("work_id", flat=True)
    node_ids = subdiscipline.knowledge_node_links.values_list("node_id", flat=True)
    curated_claims = _curated_claims(
        CuratedClaim.objects.filter(
            Q(work_id__in=work_ids) | Q(node_id__in=node_ids)
        ).distinct()
    )
    derived_claims = _derived_claims(
        DerivedClaim.objects.filter(work_id__in=work_ids).distinct()
    )
    target_type = EditorialRevision.TargetType.SUBDISCIPLINE
    modules = [
        "研究对象与核心问题",
        "形成与发展",
        "主要研究方向",
        "常用方法",
        "代表性议题",
        "相关理论传统",
        "精选文献导读",
    ]
    return {
        "id": str(subdiscipline.id),
        "object_type": "subdiscipline",
        "label": subdiscipline.name,
        "status": subdiscipline.editorial_status,
        "canonical": _bounded_json(canonical),
        "relations": (
            node_relations + work_relations + person_relations + topic_relations
        )[: MAX_SECTION_ROWS * 3],
        "evidence": _claim_evidence(
            curated=curated_claims,
            derived=derived_claims,
        ),
        "claims": {
            "curated": curated_claims,
            "derived": derived_claims,
            "derived_is_machine_only": True,
        },
        "ai_candidates": _enrichment_candidates(
            EnrichmentCandidate.TargetType.SUBDISCIPLINE,
            subdiscipline.id,
        ),
        "revisions": _revision_rows(target_type, subdiscipline.id),
        "preview": _latest_preview(target_type, subdiscipline.id, canonical),
        "frontend_impact": _frontend_impact(
            object_type=target_type,
            object_id=subdiscipline.id,
            public_visibility=(
                subdiscipline.editorial_status
                == KnowledgePublicationStatus.PUBLISHED
            ),
            modules=modules,
            targets=[
                {
                    "label": "子学科公开页",
                    "url": f"/subdisciplines/{subdiscipline.slug}",
                    "modules": modules,
                },
                {
                    "label": "学科入口",
                    "url": f"/theories/disciplines/{subdiscipline.discipline.slug}",
                    "modules": ["子学科目录", "相关作品"],
                },
            ],
        ),
        "mutation_contract": _mutation_contract(
            target_type,
            subdiscipline.id,
            published=(
                subdiscipline.editorial_status
                == KnowledgePublicationStatus.PUBLISHED
            ),
        ),
        "editor_url": f"/admin/subdisciplines?subdiscipline={subdiscipline.id}",
        "preview_url": f"/subdisciplines/{subdiscipline.slug}",
        "related_editor_urls": [
            {"label": "关系", "url": f"/admin/theory-relations?subdiscipline={subdiscipline.id}"},
            {"label": "阅读路径", "url": "/admin/reading-paths"},
        ],
    }


def _reading_path_selection(path: ReadingPath) -> dict[str, Any]:
    stage_groups = reading_path_stage_groups(path)
    canonical = {
        "title": path.title,
        "slug": path.slug,
        "introduction": path.introduction,
        "learning_goal": path.learning_goal,
        "primary_discipline": (
            path.primary_discipline.name if path.primary_discipline_id else None
        ),
        "audience": path.audience,
        "difficulty": path.difficulty,
        "estimated_reading": path.estimated_reading,
        "stages": stage_groups,
    }
    items = list(
        path.items.select_related("stage", "work", "node").order_by(
            "reading_order", "position", "created_at"
        )[: MAX_SECTION_ROWS * 3]
    )
    relations = [
        {
            "id": str(row.id),
            "kind": "reading_path_item",
            "label": row.stage.name if row.stage_id else row.stage_name,
            "target": (
                row.work.title
                if row.work_id
                else row.node.canonical_name_zh
                if row.node_id
                else "未关联对象"
            ),
            "status": "published" if path.status == "published" else "draft",
            "description": _clip(row.recommendation_reason, 600),
            "prerequisite": _clip(row.prerequisite, 600),
            "is_required": row.is_required,
        }
        for row in items
    ]
    work_ids = [row.work_id for row in items if row.work_id]
    node_ids = [row.node_id for row in items if row.node_id]
    curated_claims = _curated_claims(
        CuratedClaim.objects.filter(
            Q(work_id__in=work_ids) | Q(node_id__in=node_ids)
        ).distinct()
    )
    derived_claims = _derived_claims(
        DerivedClaim.objects.filter(work_id__in=work_ids).distinct()
    )
    candidates = _enrichment_candidates(
        EnrichmentCandidate.TargetType.READING_PATH,
        path.id,
    )
    candidates.extend(
        {
            "id": str(row.id),
            "candidate_type": "reading_path_generation",
            "field_name": "stage_groups",
            "proposed_value": _bounded_json(row.stages),
            "confidence": row.quality_score,
            "importance": row.importance_score,
            "conflicts": [],
            "status": row.status,
            "source": "reading_path_generation",
        }
        for row in path.source_candidates.select_related("evidence_pack").order_by(
            "-importance_score", "created_at"
        )[:MAX_SECTION_ROWS]
    )
    target_type = EditorialRevision.TargetType.READING_PATH
    modules = ["目标读者", "学习目标", "阶段", "作品与节点", "推荐理由", "先后逻辑"]
    return {
        "id": str(path.id),
        "object_type": "reading_path",
        "label": path.title,
        "status": path.status,
        "canonical": _bounded_json(canonical),
        "relations": relations,
        "evidence": _claim_evidence(
            curated=curated_claims,
            derived=derived_claims,
        ),
        "claims": {
            "curated": curated_claims,
            "derived": derived_claims,
            "derived_is_machine_only": True,
        },
        "ai_candidates": candidates[:MAX_SECTION_ROWS],
        "revisions": _revision_rows(target_type, path.id),
        "preview": _latest_preview(target_type, path.id, canonical),
        "frontend_impact": _frontend_impact(
            object_type=target_type,
            object_id=path.id,
            public_visibility=path.status == KnowledgePublicationStatus.PUBLISHED,
            modules=modules,
            targets=[
                {
                    "label": "阅读路径公开页",
                    "url": f"/theories/reading-paths/{path.slug}",
                    "modules": modules,
                },
            ],
        ),
        "mutation_contract": _mutation_contract(
            target_type,
            path.id,
            published=path.status == KnowledgePublicationStatus.PUBLISHED,
        ),
        "editor_url": f"/admin/reading-paths?path={path.id}",
        "preview_url": f"/theories/reading-paths/{path.slug}",
        "related_editor_urls": [
            {"label": "作品策展", "url": "/admin/library"},
            {"label": "理论节点", "url": "/admin/theory-nodes"},
        ],
    }


def _work_selection(work: Work) -> dict[str, Any]:
    editions = list(
        work.editions.prefetch_related("contributions__person").order_by(
            "-published_at", "-publication_year", "-created_at"
        )
    )
    published_edition = next(
        (row for row in editions if row.state == PublicationState.PUBLISHED),
        None,
    )
    primary_edition = published_edition or (editions[0] if editions else None)
    canonical = {
        "title": work.title,
        "subtitle": work.subtitle,
        "original_title": work.original_title,
        "canonical_title": work.uniform_title,
        "abstract": work.abstract,
        "document_type": work.document_type,
        "language": work.language,
        "original_language": work.original_language,
        "first_publication_date": work.first_publication_date,
        "is_featured": work.is_featured,
        "editions": [
            {
                "id": str(edition.id),
                "edition_statement": edition.version_label,
                "publication_date": edition.publication_date,
                "publication_year": edition.publication_year,
                "publisher": edition.publisher,
                "publication_place": edition.publication_place,
                "isbn10": edition.isbn10,
                "isbn13": edition.isbn13,
                "series": edition.series,
                "state": edition.state,
                "contributors": [
                    {
                        "name": contribution.person.preferred_name,
                        "role": contribution.role,
                        "approved": contribution.approved,
                    }
                    for contribution in edition.contributions.all()
                ],
            }
            for edition in editions[:MAX_SECTION_ROWS]
        ],
    }
    relations: list[dict[str, Any]] = []
    relations.extend(
        {
            "id": str(row.id),
            "kind": "work_node",
            "label": row.get_role_display(),
            "target": row.node.canonical_name_zh,
            "status": row.status,
            "description": "主要关系" if row.is_primary else "",
        }
        for row in work.node_relations.select_related("node").order_by(
            "-is_primary", "node__canonical_name_zh"
        )[:MAX_SECTION_ROWS]
    )
    for relation_name, kind, target_attr in (
        ("discipline_relations", "work_discipline", "discipline"),
        ("subdiscipline_relations", "work_subdiscipline", "subdiscipline"),
        ("topic_relations", "work_topic", "topic"),
    ):
        queryset = getattr(work, relation_name).select_related(target_attr).order_by(
            "-is_primary", f"{target_attr}__name"
        )[:MAX_SECTION_ROWS]
        relations.extend(
            {
                "id": str(row.id),
                "kind": kind,
                "label": "主要归类" if row.is_primary else "相关归类",
                "target": getattr(row, target_attr).name,
                "status": row.review_status,
                "description": _clip(row.evidence_text or row.source, 600),
            }
            for row in queryset
        )
    path_items = list(
        work.reading_path_items.select_related("reading_path", "stage").order_by(
            "reading_path__sort_order", "reading_order"
        )[:MAX_SECTION_ROWS]
    )
    relations.extend(
        {
            "id": str(row.id),
            "kind": "reading_path_item",
            "label": row.stage.name if row.stage_id else row.stage_name,
            "target": row.reading_path.title,
            "status": row.reading_path.status,
            "description": _clip(row.recommendation_reason, 600),
        }
        for row in path_items
    )
    curated_claims = _curated_claims(CuratedClaim.objects.filter(work=work))
    derived_claims = _derived_claims(DerivedClaim.objects.filter(work=work))
    candidates = _enrichment_candidates(EnrichmentCandidate.TargetType.WORK, work.id)
    candidates.extend(
        {
            "id": str(row.id),
            "candidate_type": "theory_review",
            "field_name": row.task_type,
            "proposed_value": row.suggested_node_name or row.suggested_relation_type,
            "confidence": row.confidence,
            "conflicts": [],
            "status": row.status,
            "source": "library_research",
            "evidence": _clip(row.evidence_text, 1200),
            "evidence_pages": row.evidence_pages[:20],
        }
        for row in work.theory_review_tasks.filter(
            status__in=[
                TheoryReviewTask.TaskStatus.PENDING,
                TheoryReviewTask.TaskStatus.NEEDS_CHANGES,
            ]
        ).order_by("-confidence", "created_at")[:MAX_SECTION_ROWS]
    )
    status_value = _work_status(work)
    public_url = (
        f"/works/{published_edition.public_slug}"
        if published_edition and published_edition.public_slug
        else ""
    )
    preview_url = public_url or (
        f"/admin/preview/works/{primary_edition.id}" if primary_edition else ""
    )
    contributor_targets: list[dict[str, Any]] = []
    seen_scholars: set[str] = set()
    for edition in editions:
        for contribution in edition.contributions.all():
            try:
                profile = contribution.person.scholar_profile
            except ScholarProfile.DoesNotExist:
                continue
            if str(profile.id) in seen_scholars:
                continue
            seen_scholars.add(str(profile.id))
            contributor_targets.append(
                {
                    "label": f"学者页 · {contribution.person.preferred_name}",
                    "url": f"/scholars/{profile.slug}",
                    "modules": ["核心作品", "核心观点", "阅读顺序"],
                }
            )
    modules = ["书目与阅读", "核心观点", "主要批评", "主要回应", "原文依据"]
    targets = [
        {
            "label": "作品公开页" if public_url else "作品认证预览",
            "url": preview_url,
            "modules": modules,
        },
        *contributor_targets,
    ]
    targets.extend(
        {
            "label": f"知识页 · {row.node.canonical_name_zh}",
            "url": f"/theories/nodes/{row.node.slug}",
            "modules": ["代表作品", "Claims", "原文证据"],
        }
        for row in work.node_relations.select_related("node").order_by(
            "-is_primary", "node__canonical_name_zh"
        )[:5]
    )
    target_type = EditorialRevision.TargetType.WORK
    return {
        "id": str(work.id),
        "object_type": "work",
        "label": work.title,
        "status": status_value,
        "canonical": _bounded_json(canonical),
        "relations": relations[: MAX_SECTION_ROWS * 3],
        "evidence": _claim_evidence(
            curated=curated_claims,
            derived=derived_claims,
        ),
        "claims": {
            "curated": curated_claims,
            "derived": derived_claims,
            "derived_is_machine_only": True,
        },
        "ai_candidates": candidates[:MAX_SECTION_ROWS],
        "revisions": _revision_rows(target_type, work.id),
        "preview": _latest_preview(target_type, work.id, canonical),
        "frontend_impact": _frontend_impact(
            object_type=target_type,
            object_id=work.id,
            public_visibility=bool(public_url),
            modules=modules,
            targets=targets,
        ),
        "mutation_contract": _mutation_contract(
            target_type,
            work.id,
            published=bool(public_url),
        ),
        "editor_url": (
            f"/admin/library/works/{work.id}"
            + (f"?edition={primary_edition.id}#work" if primary_edition else "#work")
        ),
        "preview_url": preview_url,
        "related_editor_urls": [
            {"label": "知识策展", "url": f"/admin/library/works/{work.id}#curation"},
            {"label": "阅读路径", "url": "/admin/reading-paths"},
        ],
    }


def _selection(object_type: str, object_id: str) -> dict[str, Any] | None:
    identifier = _valid_uuid(object_id)
    if object_type not in OBJECT_TYPES or identifier is None:
        return None
    if object_type in NODE_OBJECT_TYPES:
        node = KnowledgeNode.objects.select_related("primary_discipline").filter(
            pk=identifier,
            node_type=NODE_OBJECT_TYPES[object_type],
        ).first()
        return _node_selection(node, object_type) if node else None
    if object_type == "scholar":
        profile = ScholarProfile.objects.select_related("person").filter(pk=identifier).first()
        return _scholar_selection(profile) if profile else None
    if object_type == "topic":
        topic = Topic.objects.filter(pk=identifier).first()
        return _topic_selection(topic) if topic else None
    if object_type == "subdiscipline":
        subdiscipline = Subdiscipline.objects.select_related(
            "discipline", "parent"
        ).filter(pk=identifier).first()
        return _subdiscipline_selection(subdiscipline) if subdiscipline else None
    if object_type == "reading_path":
        path = ReadingPath.objects.select_related("primary_discipline").filter(
            pk=identifier
        ).first()
        return _reading_path_selection(path) if path else None
    work = Work.objects.prefetch_related(
        "editions__contributions__person",
    ).filter(pk=identifier).first()
    return _work_selection(work) if work else None


def knowledge_studio_workspace(
    *,
    query: str = "",
    object_type: str = "",
    selected_type: str = "",
    selected_id: str = "",
    limit: Any = DEFAULT_DIRECTORY_LIMIT,
) -> dict[str, Any]:
    """Return the read-only Knowledge Studio directory and selected object."""

    normalized_query = _clip(query, 160)
    normalized_type = object_type if object_type in OBJECT_TYPES else "all"
    bounded = _bounded_limit(limit)
    objects, counts = _directory(
        query=normalized_query,
        object_type=normalized_type,
        limit=bounded,
    )
    explicit_selection = bool(str(selected_type).strip() or str(selected_id).strip())
    selection = _selection(selected_type, selected_id)
    if selection is None and objects and not explicit_selection:
        selection = _selection(objects[0]["object_type"], objects[0]["id"])
    return {
        "object_types": [
            {"value": "all", "label": "全部对象"},
            {"value": "theory", "label": "理论"},
            {"value": "concept", "label": "概念"},
            {"value": "debate", "label": "争论"},
            {"value": "research_problem", "label": "研究问题"},
            {"value": "scholar", "label": "学者"},
            {"value": "subdiscipline", "label": "子学科"},
            {"value": "topic", "label": "主题"},
            {"value": "reading_path", "label": "阅读路径"},
            {"value": "work", "label": "重要作品"},
        ],
        "filters": {"query": normalized_query, "object_type": normalized_type, "limit": bounded},
        "counts": counts,
        "objects": objects,
        "selection": selection,
        "selection_error": "not_found_or_type_mismatch" if explicit_selection and selection is None else "",
        "candidate_overview": {
            "debates": DebateCandidate.objects.filter(status=DebateCandidate.Status.PENDING).count(),
            "reading_paths": ReadingPathCandidate.objects.filter(status=ReadingPathCandidate.Status.PENDING).count(),
        },
        "read_only_aggregation": True,
        "machine_claims_are_canonical": False,
    }
