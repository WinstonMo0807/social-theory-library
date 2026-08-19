from __future__ import annotations

from collections import Counter
from typing import Any

from django.db.models import Count, Q

from common.capabilities import Capability, capability_snapshot, has_capability
from ingestion.models import EntityResolutionCandidate, MetadataCandidate, UploadItem

from catalog.models import (
    Asset,
    Edition,
    EnrichmentCandidate,
    KnowledgePublicationStatus,
    PublicationState,
    ReadingPathItem,
    RecommendationOverride,
    RelationReviewStatus,
    TheoryReviewTask,
    Work,
    WorkKnowledgeRelation,
)
from catalog.services.admin_workflow import (
    BIBLIOGRAPHY_FIELDS,
    WORK_FIELDS,
    build_edition_workflow,
    build_intake_workflow,
    publication_issue_target,
)
from catalog.services.work_curation import (
    WORK_RECOMMENDATION_PLACEMENTS,
    build_work_curation_summary,
)


QUEUE_STATUSES = (
    UploadItem.Status.NEEDS_REVIEW,
    UploadItem.Status.READY,
    UploadItem.Status.FAILED,
)


def _step_status(workflow: dict[str, Any], step_key: str) -> str:
    return next(
        (row["status"] for row in workflow["steps"] if row["key"] == step_key),
        "pending",
    )


def _candidate_evidence(candidate: MetadataCandidate) -> list[dict[str, Any]]:
    return [
        {
            "id": str(row.id),
            "source": row.source_kind,
            "page_number": row.page_number,
            "text_quote": row.text_quote,
            "external_identifier": row.external_identifier,
        }
        for row in candidate.evidence_records.all()[:20]
    ]


def _metadata_candidates(item: UploadItem | None) -> list[dict[str, Any]]:
    if item is None:
        return []
    rows = item.metadata_candidates.prefetch_related("evidence_records").order_by(
        "field_name", "-confidence", "created_at"
    )
    return [
        {
            "id": str(row.id),
            "field_name": row.field_name,
            "value": row.value,
            "proposed_value": row.value,
            "status": "pending" if row.lifecycle == MetadataCandidate.Lifecycle.PROPOSED else row.lifecycle,
            "lifecycle": row.lifecycle,
            "source": row.source,
            "confidence": row.confidence,
            "evidence": row.evidence,
            "evidence_records": _candidate_evidence(row),
            "is_locked": row.is_locked,
            "decision_url": f"/ingestion/items/{item.id}/metadata-candidates/{row.id}/decision/",
            "available_actions": (
                ["reject"]
                if row.lifecycle == MetadataCandidate.Lifecycle.PROPOSED
                else ["reopen"]
                if row.lifecycle in {
                    MetadataCandidate.Lifecycle.REJECTED,
                    MetadataCandidate.Lifecycle.SUPERSEDED,
                }
                else []
            ),
        }
        for row in rows
    ]


def _entity_candidates(item: UploadItem | None) -> list[dict[str, Any]]:
    if item is None:
        return []
    rows = item.entity_resolution_candidates.order_by(
        "target_type", "source_name", "-match_score", "created_at"
    )
    return [
        {
            "id": str(row.id),
            "field_name": "contributors" if row.target_type == "person" else row.target_type,
            "source_name": row.source_name,
            "label": row.label,
            "target_type": row.target_type,
            "candidate_entity_type": row.candidate_entity_type,
            "candidate_entity_id": row.candidate_entity_id,
            "status": "pending" if row.status == EntityResolutionCandidate.Status.PROPOSED else row.status,
            "source": "entity_resolution",
            "confidence": row.match_score,
            "evidence": {
                "match_reasons": row.match_reasons,
                "conflicts": row.conflicts,
                "preview": row.preview_data,
                "supporting_properties": row.supporting_properties,
            },
            "decision_url": f"/ingestion/items/{item.id}/entity-resolution-candidates/{row.id}/decision/",
            "available_actions": (
                ["link_existing", "create_draft", "keep_unresolved", "reject"]
                if row.status == EntityResolutionCandidate.Status.PROPOSED
                else []
            ),
        }
        for row in rows
    ]


def _enrichment_candidates(work: Work, edition: Edition) -> list[dict[str, Any]]:
    rows = EnrichmentCandidate.objects.filter(
        Q(target_type=EnrichmentCandidate.TargetType.WORK, target_id=work.id)
        | Q(target_type=EnrichmentCandidate.TargetType.EDITION, target_id=edition.id)
    ).prefetch_related("evidence_records").order_by("field_name", "-confidence", "created_at")[:100]
    return [
        {
            "id": str(row.id),
            "field_name": row.field_name,
            "proposed_value": row.proposed_value,
            "current_value": row.current_value,
            "status": row.status,
            "source": row.source_class,
            "confidence": row.confidence,
            "evidence_records": [
                {
                    "id": str(evidence.id),
                    "source_title": evidence.source_title,
                    "canonical_url": evidence.canonical_url,
                    "supporting_text": evidence.supporting_text,
                    "source_class": evidence.source_class,
                    "retrieved_at": evidence.retrieved_at,
                }
                for evidence in row.evidence_records.filter(is_current=True)[:20]
            ],
            "decision_url": f"/catalog/admin/field-enrichment/candidates/{row.id}/decision/",
            "available_actions": ["accept", "reject"] if row.status == EnrichmentCandidate.Status.PENDING else [],
        }
        for row in rows
    ]


def _file_data(item: UploadItem | None, edition: Edition) -> dict[str, Any]:
    original = edition.assets.filter(kind=Asset.Kind.ORIGINAL, is_current=True).order_by("-version").first()
    normalized = edition.assets.filter(kind=Asset.Kind.NORMALIZED, is_current=True).order_by("-version").first()
    anchor = normalized or original
    summary = item.preflight_summary if item else {}
    return {
        "filename": item.source_filename if item else (anchor.original_filename if anchor else ""),
        "status": item.status if item else (anchor.status if anchor else "pending"),
        "workflow_state": item.workflow_state if item else "maintenance",
        "validation": anchor.validation_status if anchor else "pending",
        "is_valid_pdf": bool(anchor and anchor.validation_status != Asset.ValidationStatus.INVALID),
        "page_count": anchor.page_count if anchor else 0,
        "mime_type": anchor.mime_type if anchor else "",
        "sha256": anchor.sha256 if anchor else "",
        "text_profile": (summary or {}).get("text_profile", ""),
        "ocr_strategy": item.batch.ocr_strategy if item else "maintenance",
        "exact_duplicate": bool((summary or {}).get("exact_duplicate")),
        "duplicate_status": (summary or {}).get("catalog_reconciliation", {}).get("mode", ""),
        "error_code": item.error_code if item else "",
        "error_message": item.error_message if item else "",
        "can_retry": bool(item and item.status == UploadItem.Status.FAILED),
        "can_resume": bool(item and item.status in {UploadItem.Status.FAILED, UploadItem.Status.NEEDS_REVIEW}),
        "can_replace": bool(item and edition.state == PublicationState.PUBLISHED),
        "original_asset_id": str(original.id) if original else None,
        "normalized_asset_id": str(normalized.id) if normalized else None,
    }


def _work_data(work: Work, edition: Edition) -> dict[str, Any]:
    return {
        **{field: getattr(work, field) for field in WORK_FIELDS if not field.endswith("_id")},
        "translation_of": str(work.translation_of_id) if work.translation_of_id else None,
        "expected_updated_at": edition.updated_at,
        "expected_work_updated_at": work.updated_at,
    }


def _bibliography_data(work: Work, edition: Edition) -> dict[str, Any]:
    return {
        **{field: getattr(edition, field) for field in BIBLIOGRAPHY_FIELDS},
        "document_type": work.document_type,
        "expected_updated_at": edition.updated_at,
        "expected_work_updated_at": work.updated_at,
    }


def _contributors_data(edition: Edition, item: UploadItem | None) -> dict[str, Any]:
    rows = [
        {
            "id": str(contribution.id),
            "person_id": str(contribution.person_id),
            "display_name": contribution.person.preferred_name,
            "role": contribution.role,
            "order": contribution.order,
            "approved": contribution.approved,
            "resolution_state": "confirmed" if contribution.approved else "candidate",
            "candidate_count": 0,
        }
        for contribution in edition.contributions.select_related("person").order_by("order", "created_at")
    ]
    if item:
        candidate_rows = list(item.entity_resolution_candidates.filter(target_type="person"))
        counts = Counter(row.source_name for row in candidate_rows)
        linked_names = {str(row["display_name"]).casefold() for row in rows}
        linked_person_ids = {str(row["person_id"]) for row in rows if row["person_id"]}
        for candidate in candidate_rows:
            if (
                candidate.source_name.casefold() in linked_names
                or (
                    candidate.status in {
                        EntityResolutionCandidate.Status.LINKED,
                        EntityResolutionCandidate.Status.CREATE_DRAFT,
                    }
                    and candidate.candidate_entity_id in linked_person_ids
                )
            ):
                continue
            rows.append(
                {
                    "id": None,
                    "person_id": None,
                    "display_name": candidate.source_name,
                    "role": "author",
                    "order": len(rows),
                    "approved": False,
                    "resolution_state": candidate.status,
                    "candidate_count": counts[candidate.source_name],
                }
            )
            linked_names.add(candidate.source_name.casefold())
    return {
        "items": rows,
        "expected_updated_at": edition.updated_at,
        "expected_work_updated_at": edition.work.updated_at,
    }


def _classification_data(workflow: dict[str, Any], edition: Edition) -> dict[str, Any]:
    primary = []
    related = []
    for relation in edition.work.discipline_relations.select_related("discipline").order_by(
        "-is_primary", "discipline__name"
    ):
        row = {
            "id": str(relation.discipline_id),
            "name": relation.discipline.name,
            "slug": relation.discipline.slug,
            "is_primary": relation.is_primary,
            "review_status": relation.review_status,
            "evidence_page": relation.evidence_page,
            "evidence_printed_label": relation.evidence_printed_label,
            "evidence_text": relation.evidence_text,
        }
        (primary if relation.is_primary else related).append(row)
    subdisciplines = [
        {
            "id": str(relation.subdiscipline_id),
            "name": relation.subdiscipline.name,
            "slug": relation.subdiscipline.slug,
            "is_primary": relation.is_primary,
            "strength": relation.strength,
            "review_status": relation.review_status,
            "evidence_page": relation.evidence_page,
            "evidence_printed_label": relation.evidence_printed_label,
            "evidence_text": relation.evidence_text,
        }
        for relation in edition.work.subdiscipline_relations.select_related("subdiscipline").order_by(
            "-is_primary", "subdiscipline__name"
        )
    ]
    return {
        "primary_disciplines": primary,
        "related_disciplines": related,
        "subdisciplines": subdisciplines,
        "confirmed": _step_status(workflow, "classification") == "complete",
        "expected_updated_at": edition.updated_at,
        "expected_work_updated_at": edition.work.updated_at,
    }


def _knowledge_data(workflow: dict[str, Any], edition: Edition) -> dict[str, Any]:
    relations: list[dict[str, Any]] = []
    for relation in edition.work.knowledge_relations.select_related(
        "theory_school", "topic", "concept"
    ).order_by("kind", "created_at"):
        if relation.theory_school_id:
            target_type = "theory"
            target = relation.theory_school
        elif relation.topic_id:
            target_type = "topic"
            target = relation.topic
        else:
            target_type = "concept"
            target = relation.concept
        if target is None:
            continue
        relations.append(
            {
                "id": str(relation.id),
                "target_type": target_type,
                "target_id": str(target.id),
                "name": target.name,
                "role": relation.role or "local_mention",
                "strength": relation.strength,
                "is_primary": relation.is_primary,
                "review_status": relation.review_status,
                "approved": relation.approved,
                "evidence_asset": str(relation.evidence_asset_id) if relation.evidence_asset_id else None,
                "evidence_page": relation.evidence_page,
                "evidence_printed_label": relation.evidence_printed_label,
                "evidence_text": relation.evidence_text,
                "evidence_summary": relation.evidence_text,
            }
        )
    for relation in edition.work.node_relations.select_related("node").order_by("node__canonical_name_zh"):
        relations.append(
            {
                "id": str(relation.id),
                "target_type": "knowledge_node",
                "target_id": str(relation.node_id),
                "name": relation.node.canonical_name_zh,
                "role": relation.role,
                "strength": relation.strength,
                "is_primary": relation.is_primary,
                "review_status": relation.status,
                "approved": relation.status == KnowledgePublicationStatus.PUBLISHED,
                "evidence_summary": "",
            }
        )
    return {
        "relations": relations,
        "confirmed": _step_status(workflow, "knowledge") == "complete",
        "expected_updated_at": edition.updated_at,
        "expected_work_updated_at": edition.work.updated_at,
    }


def _reader_data(edition: Edition) -> dict[str, Any]:
    assets = list(
        edition.assets.filter(is_current=True).order_by("kind", "-version").values(
            "id", "kind", "status", "validation_status", "page_count", "mime_type"
        )
    )
    normalized = next((row for row in assets if row["kind"] == Asset.Kind.NORMALIZED), None)
    original = next((row for row in assets if row["kind"] == Asset.Kind.ORIGINAL), None)
    return {
        "readable": bool(normalized and normalized["status"] == Asset.Status.READY),
        "original_asset_status": original["status"] if original else "pending",
        "reader_rendition_policy": edition.reader_rendition_policy,
        "text_layer_status": edition.ocr_status,
        "ocr_status": edition.ocr_status,
        "page_label_status": edition.page_label_status,
        "semantic_index_status": edition.semantic_index_status,
        "full_text_index_status": "ready" if edition.search_indexed_at else "pending",
        "assets": assets,
        "expected_updated_at": edition.updated_at,
        "expected_work_updated_at": edition.work.updated_at,
    }


def _curation_data(workflow: dict[str, Any], work: Work) -> dict[str, Any]:
    summary = build_work_curation_summary(work.id)
    placements = [
        {
            "id": str(item.id),
            "path_id": str(item.reading_path_id),
            "path_title": item.reading_path.title,
            "path_status": item.reading_path.status,
            "path_updated_at": item.reading_path.updated_at,
            "stage_id": str(item.stage_id) if item.stage_id else None,
            "stage_name": item.stage.name if item.stage_id else item.stage_name,
            "recommendation_reason": item.recommendation_reason,
            "is_required": item.is_required,
            "editorial_note": item.editorial_note,
        }
        for item in summary.placements
    ]
    active_overrides = {
        row.policy.placement: row for row in summary.overrides if row.active
    }
    recommendation_placements = [
        {
            "placement": policy.placement,
            "title": policy.title,
            "enabled": policy.enabled,
            "override_enabled": policy.placement in active_overrides,
            "override_action": active_overrides[policy.placement].action
            if policy.placement in active_overrides
            else None,
            "position": active_overrides[policy.placement].position
            if policy.placement in active_overrides
            else None,
        }
        for policy in summary.policies
    ]
    return {
        "reading_path_placements": placements,
        "recommendation_placements": recommendation_placements,
        "skipped": _step_status(workflow, "curation") == "skipped",
    }


def _publication_data(workflow: dict[str, Any], edition: Edition) -> dict[str, Any]:
    preflight = workflow["publication_preflight"]
    def issue(message: str, severity: str) -> dict[str, Any]:
        step, field = publication_issue_target(message)
        return {
            "message": message,
            "severity": severity,
            "step": step,
            "field": field,
            "action_target": f"#{step}{f':{field}' if field else ''}",
        }

    blockers = [issue(message, "blocker") for message in preflight["blockers"]]
    warnings = [issue(message, "warning") for message in preflight["warnings"]]
    background_tasks = [
        issue(message, "info") for message in preflight["background_tasks"]
    ]
    return {
        "publication_state": edition.state,
        "preflight": {
            "blockers": blockers,
            "warnings": warnings,
            "background_tasks": background_tasks,
        },
        "blockers": blockers,
        "warnings": warnings,
        "background_tasks": background_tasks,
        "reader_state": "ready"
        if edition.assets.filter(
            kind=Asset.Kind.NORMALIZED,
            is_current=True,
            status=Asset.Status.READY,
        ).exists()
        else "pending",
        "curation_summary": (
            "已加入阅读路径"
            if ReadingPathItem.objects.filter(work=edition.work).exists()
            else "尚未策展，不阻止发布"
        ),
        "first_published_at": edition.first_published_at,
        "last_published_at": edition.last_published_at,
    }


def _queue_for(item: UploadItem | None) -> dict[str, Any]:
    queryset = UploadItem.objects.filter(status__in=QUEUE_STATUSES, edition__isnull=False)
    if item:
        queryset = queryset.exclude(pk=item.pk)
    next_item = queryset.order_by("-priority", "updated_at", "created_at").first()
    return {
        "next_item_id": str(next_item.id) if next_item else None,
        "next_work_id": str(next_item.edition.work_id) if next_item and next_item.edition_id else None,
        "return_href": "/admin/review",
        "remaining_count": queryset.count(),
    }


def _permissions(user) -> dict[str, Any]:
    snapshot = capability_snapshot(user)
    return {
        "can_edit": has_capability(user, Capability.EDIT_METADATA),
        "can_confirm": has_capability(user, Capability.EDIT_METADATA),
        "can_manage_publication": has_capability(user, Capability.PUBLISH_WORK),
        "can_publish": has_capability(user, Capability.PUBLISH_WORK),
        "can_withdraw": has_capability(user, Capability.PUBLISH_WORK),
        "can_manage_curation": has_capability(user, Capability.EDIT_DRAFT_AUTHORITY),
        "can_review_candidate": has_capability(user, Capability.REVIEW_CANDIDATE),
        "capabilities": list(snapshot.capabilities),
    }


def build_admin_workspace(
    edition: Edition,
    *,
    user,
    mode: str,
    item: UploadItem | None = None,
) -> dict[str, Any]:
    edition = Edition.objects.select_related("work").get(pk=edition.pk)
    work = edition.work
    workflow = build_intake_workflow(item) if item else build_edition_workflow(edition)
    normalized = edition.assets.filter(
        kind=Asset.Kind.NORMALIZED,
        is_current=True,
    ).order_by("-version").first()
    candidates = {
        "metadata": _metadata_candidates(item),
        "entities": _entity_candidates(item),
        "enrichment": _enrichment_candidates(work, edition),
        "theory": [
            {
                "id": str(row.id),
                "field_name": "relations",
                "label": row.suggested_node_name or (row.candidate_node.canonical_name_zh if row.candidate_node else "知识关系"),
                "status": "pending" if row.status == TheoryReviewTask.TaskStatus.PENDING else row.status,
                "source": "theory_review",
                "confidence": row.confidence,
                "evidence": {"pages": row.evidence_pages, "text": row.evidence_text},
                "available_actions": [],
            }
            for row in TheoryReviewTask.objects.filter(work=work).select_related("candidate_node")[:100]
        ],
    }
    return {
        "mode": mode,
        "context": {
            "item_id": str(item.id) if item else None,
            "work_id": str(work.id),
            "edition_id": str(edition.id),
            "title": work.title,
            "filename": item.source_filename if item else (normalized.original_filename if normalized else ""),
            "document_type": work.document_type,
            "publication_state": edition.state,
            "preview_url": f"/ingestion/items/{item.id}/preview/" if item else (
                f"/distribution/assets/{normalized.id}/file/" if normalized else ""
            ),
            "public_url": f"/works/{edition.public_slug}" if edition.public_slug else "",
            "return_href": "/admin/review" if item else "/admin/library",
        },
        "workflow": workflow,
        "data": {
            "file": _file_data(item, edition),
            "work": _work_data(work, edition),
            "edition": _bibliography_data(work, edition),
            "bibliography": _bibliography_data(work, edition),
            "contributors": _contributors_data(edition, item),
            "classification": _classification_data(workflow, edition),
            "knowledge": _knowledge_data(workflow, edition),
            "reader": _reader_data(edition),
            "curation": _curation_data(workflow, work),
            "publication": _publication_data(workflow, edition),
        },
        "candidates": candidates,
        "permissions": _permissions(user),
        "queue": _queue_for(item),
    }


def work_library_queryset(*, query: str = "", view: str = ""):
    queryset = Work.objects.all().annotate(
        edition_count_value=Count("editions", distinct=True)
    ).prefetch_related(
        "editions__assets",
        "editions__contributions__person",
        "knowledge_relations",
        "node_relations",
        "reading_path_items",
        "recommendationoverride_set__policy",
    )
    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(subtitle__icontains=query)
            | Q(original_title__icontains=query)
            | Q(editions__isbn__icontains=query)
            | Q(editions__isbn10__icontains=query)
            | Q(editions__isbn13__icontains=query)
            | Q(editions__doi__icontains=query)
            | Q(editions__contributions__person__preferred_name__icontains=query)
        ).distinct()
    if view == "published":
        queryset = queryset.filter(editions__state=PublicationState.PUBLISHED).distinct()
    elif view == "withdrawn":
        queryset = queryset.filter(editions__state=PublicationState.WITHDRAWN).distinct()
    elif view == "draft":
        queryset = queryset.filter(editions__state__in=[PublicationState.DRAFT, PublicationState.READY]).distinct()
    elif view in {"attention", "quality"}:
        queryset = queryset.filter(
            Q(editions__review_status__in=["not_started", "in_progress"])
            | Q(editions__assets__status=Asset.Status.FAILED)
        ).distinct()
    return queryset.order_by("title", "id")


def serialize_work_library_row(work: Work) -> dict[str, Any]:
    editions = list(work.editions.all())
    primary = max(
        editions,
        key=lambda edition: (
            bool(edition.is_primary),
            edition.last_published_at.isoformat() if edition.last_published_at else "",
            edition.publication_year or 0,
            edition.updated_at.isoformat(),
        ),
        default=None,
    )
    if primary is None:
        publication_state = "draft"
        asset_state = "pending"
        contributors: list[str] = []
        primary_label = "尚无版本"
    else:
        publication_state = primary.state
        assets = [row for row in primary.assets.all() if row.is_current]
        normalized_assets = [row for row in assets if row.kind == Asset.Kind.NORMALIZED]
        asset = max(normalized_assets or assets, key=lambda row: row.version, default=None)
        asset_state = asset.status if asset else "pending"
        contributors = [
            row.person.preferred_name
            for row in sorted(primary.contributions.all(), key=lambda value: value.order)
            if row.approved
        ]
        primary_label = primary.version_label or (
            str(primary.publication_year) if primary.publication_year else "主版本"
        )
    legacy_relations = list(work.knowledge_relations.all())
    node_relations = list(work.node_relations.all())
    knowledge_pending = any(
        not row.approved or row.review_status == RelationReviewStatus.SUGGESTED
        for row in legacy_relations
    ) or any(
        row.status in {KnowledgePublicationStatus.DRAFT, KnowledgePublicationStatus.PENDING}
        for row in node_relations
    )
    knowledge_count = sum(row.approved for row in legacy_relations)
    knowledge_count += sum(
        row.status == KnowledgePublicationStatus.PUBLISHED for row in node_relations
    )
    knowledge_status = "attention" if knowledge_pending else "complete" if knowledge_count else "draft"
    curated = bool(list(work.reading_path_items.all())) or any(
        row.active and row.policy.placement in WORK_RECOMMENDATION_PLACEMENTS
        for row in work.recommendationoverride_set.all()
    )
    return {
        "id": str(work.id),
        "title": work.title,
        "document_type": work.document_type,
        "language": work.language,
        "contributors": contributors,
        "edition_count": getattr(work, "edition_count_value", len(editions)),
        "primary_edition": {
            "id": str(primary.id) if primary else None,
            "label": primary_label,
            "version_label": primary.version_label if primary else "",
        },
        "publication_state": publication_state,
        "asset_state": asset_state,
        "knowledge_status": knowledge_status,
        "curation_status": "complete" if curated else "attention",
        "updated_at": work.updated_at,
    }


def serialize_workflow_queue_item(item: UploadItem) -> dict[str, Any]:
    workflow = build_intake_workflow(item)
    current = next(
        (row for row in workflow["steps"] if row["key"] == workflow["current_step"]),
        {"label": workflow["current_step"]},
    )
    work = item.edition.work if item.edition_id else None
    return {
        "item_id": str(item.id),
        "work_id": str(work.id) if work else None,
        "title": work.title if work else item.source_filename,
        "source_filename": item.source_filename,
        "document_type": work.document_type if work else item.document_type_hint,
        "current_step": workflow["current_step"],
        "current_step_label": current["label"],
        "overall_status": workflow["overall_status"],
        "unresolved_count": workflow["unresolved_count"],
        "warnings_count": workflow["warnings_count"],
        "blockers_count": workflow["blockers_count"],
        "updated_at": item.updated_at,
    }
