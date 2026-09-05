from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable
import uuid

from django.db import transaction
from django.utils import timezone

from catalog.models import (
    Asset,
    CatalogFieldDecision,
    CatalogFieldDecisionLog,
    Contribution,
    DocumentType,
    Edition,
    KnowledgePublicationStatus,
    PublicationBundle,
    PublicationState,
    ReadingPathItem,
    RecommendationOverride,
    RelationReviewStatus,
    WorkKnowledgeRelation,
)


SECTION_FIELDS: dict[str, tuple[str, ...]] = {
    "file": ("file",),
    "work": (
        "title",
        "subtitle",
        "original_title",
        "uniform_title",
        "document_type",
        "language",
        "original_language",
        "first_publication_date",
        "translation_of",
        "abstract",
        "cover",
    ),
    "bibliography": (
        "journal_contents",
        "version_label",
        "publication_date",
        "publication_year",
        "publisher",
        "publication_place",
        "isbn10",
        "isbn13",
        "series",
        "extent",
        "journal_title",
        "volume",
        "issue",
        "page_range",
        "doi",
        "degree_institution",
        "degree_type",
        "report_institution",
    ),
    "contributors": (
        "authors",
        "translators",
        "chief_editors",
        "editors",
        "annotators",
        "photographers",
        "other_contributors",
    ),
    "classification": ("disciplines", "subdisciplines"),
    "knowledge": ("topics", "theories"),
    "reader": ("reader_asset", "ocr_text", "page_labels"),
    "curation": ("curation",),
}


# Downstream fields are invalidated when any listed upstream field changes.
FIELD_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "edition_match": ("title", "authors", "isbn10", "isbn13", "publisher", "publication_year"),
    "translators": ("title", "authors", "isbn10", "isbn13", "publisher", "publication_year"),
    "publisher": ("title", "isbn10", "isbn13", "publication_year"),
    "publication_year": ("title", "isbn10", "isbn13", "publisher"),
    "cover": ("title", "authors", "isbn10", "isbn13", "publisher", "publication_year"),
    "abstract": ("title", "authors", "isbn10", "isbn13", "publisher", "publication_year"),
    "disciplines": ("title", "authors", "abstract"),
    "subdisciplines": ("title", "authors", "abstract", "disciplines"),
    "topics": ("title", "authors", "abstract", "disciplines"),
    "theories": ("title", "authors", "abstract", "disciplines", "topics"),
}


REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    DocumentType.BOOK: ("file", "title", "document_type", "language", "authors"),
    DocumentType.JOURNAL_ARTICLE: (
        "file",
        "title",
        "document_type",
        "language",
        "authors",
        "journal_title",
        "publication_year",
    ),
    DocumentType.JOURNAL_ISSUE: (
        "file",
        "title",
        "document_type",
        "language",
        "journal_title",
        "publication_year",
        "volume",
        "issue",
    ),
    DocumentType.THESIS: (
        "file",
        "title",
        "document_type",
        "language",
        "authors",
        "degree_institution",
    ),
    DocumentType.REPORT: (
        "file",
        "title",
        "document_type",
        "language",
        "authors",
        "report_institution",
    ),
}


REVIEWABLE_OPTIONAL_FIELDS = (
    "translators",
    "disciplines",
    "subdisciplines",
    "topics",
    "theories",
)


@dataclass(frozen=True)
class FieldReadiness:
    field_name: str
    status: str
    value: Any
    required: bool
    stale_reason: str


def _user_id(actor):
    return getattr(actor, "pk", None)


def _json_fingerprint(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def edition_context(edition: Edition) -> tuple[str, uuid.UUID]:
    return "edition", edition.id


@transaction.atomic
def ensure_publication_bundle(edition: Edition, *, actor=None) -> PublicationBundle:
    context_type, context_id = edition_context(edition)
    bundle, _created = PublicationBundle.objects.select_for_update().get_or_create(
        context_type=context_type,
        context_id=context_id,
        status=PublicationBundle.Status.DRAFT,
        defaults={
            "edition": edition,
            "label": edition.work.title,
            "created_by_id": _user_id(actor),
        },
    )
    updates = []
    if bundle.edition_id != edition.id:
        bundle.edition = edition
        updates.append("edition")
    if bundle.label != edition.work.title:
        bundle.label = edition.work.title
        updates.append("label")
    if updates:
        bundle.save(update_fields=[*updates, "updated_at"])
    return bundle


def dependency_snapshot(edition: Edition, field_name: str) -> dict[str, Any]:
    dependencies = FIELD_DEPENDENCIES.get(field_name, ())
    values, _confirmed = formal_field_values(edition)
    return {name: values.get(name) for name in dependencies}


def dependency_fingerprint(edition: Edition, field_name: str) -> str:
    return _json_fingerprint(dependency_snapshot(edition, field_name))


@transaction.atomic
def record_field_decision(
    *,
    context_type: str,
    context_id,
    target_type: str,
    target_id,
    field_name: str,
    status: str,
    value: Any,
    actor=None,
    edition: Edition | None = None,
    bundle: PublicationBundle | None = None,
    confirmation_method: str = CatalogFieldDecision.ConfirmationMethod.MANUAL,
    provenance: dict[str, Any] | None = None,
    evidence_summary: list[dict[str, Any]] | None = None,
    candidate_type: str = "",
    candidate_id=None,
    dependency_fields: Iterable[str] | None = None,
    dependency_hash: str = "",
    stale_reason: str = "",
    reason: str = "",
) -> CatalogFieldDecision:
    if status not in CatalogFieldDecision.Status.values:
        raise ValueError("未知字段状态。")
    lookup = {
        "context_type": context_type,
        "context_id": context_id,
        "target_type": target_type,
        "target_id": target_id,
        "field_name": field_name,
    }
    current = CatalogFieldDecision.objects.select_for_update().filter(**lookup).first()
    old_value = current.value if current else None
    defaults = {
        "edition": edition,
        "bundle": bundle,
        "status": status,
        "value": value,
        "previous_value": old_value,
        "provenance": provenance or {},
        "evidence_summary": evidence_summary or [],
        "candidate_type": candidate_type,
        "candidate_id": candidate_id,
        "dependency_fields": list(dependency_fields or ()),
        "dependency_fingerprint": dependency_hash,
        "stale_reason": stale_reason,
        "confirmation_method": confirmation_method,
        "confirmed_by_id": _user_id(actor),
        "confirmed_at": (
            timezone.now()
            if status
            in {
                CatalogFieldDecision.Status.CONFIRMED,
                CatalogFieldDecision.Status.NOT_APPLICABLE,
                CatalogFieldDecision.Status.STALE,
            }
            else None
        ),
    }
    if current is None:
        decision = CatalogFieldDecision.objects.create(**lookup, **defaults)
    else:
        for name, field_value in defaults.items():
            setattr(current, name, field_value)
        current.save()
        decision = current
    CatalogFieldDecisionLog.objects.create(
        decision=decision,
        action=("create" if current is None else "update"),
        old_value=old_value,
        new_value=value,
        candidate_type=candidate_type,
        candidate_id=candidate_id,
        source_summary=evidence_summary or [],
        reason=reason,
        actor_id=_user_id(actor),
    )
    return decision


@transaction.atomic
def record_edition_field_decision(
    edition: Edition,
    field_name: str,
    *,
    status: str,
    value: Any,
    actor=None,
    target_type: str = "edition",
    target_id=None,
    confirmation_method: str = CatalogFieldDecision.ConfirmationMethod.MANUAL,
    provenance: dict[str, Any] | None = None,
    evidence_summary: list[dict[str, Any]] | None = None,
    candidate_type: str = "",
    candidate_id=None,
    reason: str = "",
) -> CatalogFieldDecision:
    locked = Edition.objects.select_for_update().select_related("work").get(pk=edition.pk)
    bundle = ensure_publication_bundle(locked, actor=actor)
    dependencies = FIELD_DEPENDENCIES.get(field_name, ())
    return record_field_decision(
        context_type="edition",
        context_id=locked.id,
        target_type=target_type,
        target_id=target_id or locked.id,
        field_name=field_name,
        status=status,
        value=value,
        actor=actor,
        edition=locked,
        bundle=bundle,
        confirmation_method=confirmation_method,
        provenance=provenance,
        evidence_summary=evidence_summary,
        candidate_type=candidate_type,
        candidate_id=candidate_id,
        dependency_fields=dependencies,
        dependency_hash=dependency_fingerprint(locked, field_name),
        reason=reason,
    )


@transaction.atomic
def invalidate_dependent_fields(
    edition: Edition,
    changed_fields: Iterable[str],
    *,
    actor=None,
) -> list[str]:
    changed = set(changed_fields)
    affected = {
        field_name
        for field_name, upstream in FIELD_DEPENDENCIES.items()
        if changed.intersection(upstream)
    }
    if not affected:
        return []
    rows = list(
        CatalogFieldDecision.objects.select_for_update().filter(
            context_type="edition",
            context_id=edition.id,
            field_name__in=affected,
        )
    )
    invalidated: list[str] = []
    for decision in rows:
        next_hash = dependency_fingerprint(edition, decision.field_name)
        if decision.dependency_fingerprint == next_hash:
            continue
        old_status = decision.status
        old_value = decision.value
        if old_status in {
            CatalogFieldDecision.Status.CONFIRMED,
            CatalogFieldDecision.Status.NOT_APPLICABLE,
            CatalogFieldDecision.Status.STALE,
        }:
            decision.status = CatalogFieldDecision.Status.STALE
            decision.stale_reason = "上游信息已变化，建议重新检查。"
        else:
            decision.status = CatalogFieldDecision.Status.SUGGESTED
            decision.candidate_type = ""
            decision.candidate_id = None
            decision.evidence_summary = []
            decision.stale_reason = "上游信息已变化，旧建议已失效。"
        decision.dependency_fingerprint = next_hash
        decision.save(
            update_fields=[
                "status",
                "candidate_type",
                "candidate_id",
                "evidence_summary",
                "stale_reason",
                "dependency_fingerprint",
                "updated_at",
            ]
        )
        CatalogFieldDecisionLog.objects.create(
            decision=decision,
            action="dependency_invalidated",
            old_value=old_value,
            new_value=decision.value,
            reason=decision.stale_reason,
            actor_id=_user_id(actor),
        )
        invalidated.append(decision.field_name)
    return sorted(invalidated)


def field_value_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    if isinstance(value, bool):
        return value
    return True


def formal_field_values(edition: Edition, *, include_editorial_draft: bool = True) -> tuple[dict[str, Any], set[str]]:
    """Read the current catalog draft without consulting discovery queues.

    The second return value records fields whose related rows are already
    editor-approved. Scalar Work and Edition values are canonical draft data,
    but only published historical values and explicit field locks provide
    compatibility confirmation. Unreviewed machine-filled drafts do not.
    """

    work = edition.work
    current_assets = edition.assets.filter(is_current=True)
    original = current_assets.filter(
        kind=Asset.Kind.ORIGINAL,
        status=Asset.Status.READY,
    ).exclude(validation_status=Asset.ValidationStatus.INVALID).first()
    normalized = current_assets.filter(
        kind=Asset.Kind.NORMALIZED,
        status=Asset.Status.READY,
    ).exclude(validation_status=Asset.ValidationStatus.INVALID).first()

    contributions = list(
        edition.contributions.filter(approved=True)
        .order_by("order", "created_at")
        .values_list("role", "person_id")
    )
    role_values: dict[str, list[str]] = {
        "authors": [],
        "translators": [],
        "chief_editors": [],
        "editors": [],
        "annotators": [],
        "photographers": [],
        "other_contributors": [],
    }
    role_fields = {
        Contribution.Role.AUTHOR: "authors",
        Contribution.Role.TRANSLATOR: "translators",
        Contribution.Role.CHIEF_EDITOR: "chief_editors",
        Contribution.Role.EDITOR: "editors",
        Contribution.Role.ANNOTATOR: "annotators",
        Contribution.Role.PHOTOGRAPHER: "photographers",
    }
    for role, person_id in contributions:
        role_values[role_fields.get(role, "other_contributors")].append(str(person_id))

    discipline_rows = list(
        work.discipline_relations.exclude(
            review_status=RelationReviewStatus.REJECTED
        ).values_list("discipline_id", "review_status")
    )
    subdiscipline_rows = list(
        work.subdiscipline_relations.exclude(
            review_status=RelationReviewStatus.REJECTED
        ).values_list("subdiscipline_id", "review_status")
    )
    topic_rows = list(
        work.topic_relations.exclude(
            review_status=RelationReviewStatus.REJECTED
        ).values_list("topic_id", "review_status")
    )
    legacy_topic_rows = list(
        work.knowledge_relations.filter(
            kind=WorkKnowledgeRelation.Kind.TOPIC,
        )
        .exclude(review_status=RelationReviewStatus.REJECTED)
        .values_list("topic_id", "review_status", "approved")
    )
    theory_rows = list(
        work.node_relations.exclude(
            status__in=[
                KnowledgePublicationStatus.REJECTED,
                KnowledgePublicationStatus.ARCHIVED,
            ]
        ).values_list("node_id", "status")
    )
    legacy_theory_rows = list(
        work.knowledge_relations.filter(
            kind=WorkKnowledgeRelation.Kind.THEORY_SCHOOL,
        )
        .exclude(review_status=RelationReviewStatus.REJECTED)
        .values_list("theory_school_id", "review_status", "approved")
    )

    values: dict[str, Any] = {
        "file": [str(original.id), str(normalized.id)] if original and normalized else [],
        "title": work.title,
        "subtitle": work.subtitle,
        "original_title": work.original_title,
        "uniform_title": work.uniform_title,
        "document_type": work.document_type,
        "language": work.language,
        "original_language": work.original_language,
        "first_publication_date": work.first_publication_date,
        "translation_of": str(work.translation_of_id) if work.translation_of_id else None,
        "abstract": work.abstract,
        "cover": work.cover.name if work.cover else "",
        **{
            field_name: getattr(edition, field_name)
            for field_name in SECTION_FIELDS["bibliography"] if field_name != "journal_contents"
        },
        **role_values,
        "disciplines": [str(row[0]) for row in discipline_rows],
        "subdisciplines": [str(row[0]) for row in subdiscipline_rows],
        "topics": list(
            dict.fromkeys(
                [str(row[0]) for row in topic_rows if row[0]]
                + [str(row[0]) for row in legacy_topic_rows if row[0]]
            )
        ),
        "theories": list(
            dict.fromkeys(
                [str(row[0]) for row in theory_rows if row[0]]
                + [str(row[0]) for row in legacy_theory_rows if row[0]]
            )
        ),
        "reader_asset": str(normalized.id) if normalized else None,
        "ocr_text": edition.ocr_status in {"succeeded", "not_required"},
        "page_labels": edition.page_label_status == "ready",
        "curation": bool(
            ReadingPathItem.objects.filter(work=work).exists()
            or RecommendationOverride.objects.filter(work=work, active=True).exists()
        ),
    }
    from catalog.services.journal_issues import journal_contents_snapshot

    values["journal_contents"] = journal_contents_snapshot(edition)
    historical_published = edition.state == PublicationState.PUBLISHED or bool(edition.active_catalog_revision_id)
    from ingestion.models import FieldLock
    locked_fields = set(FieldLock.objects.filter(edition=edition).values_list("field_name", flat=True))
    formally_confirmed = {
        field_name
        for field_name, value in values.items()
        if field_name
        not in {
            "disciplines",
            "subdisciplines",
            "topics",
            "theories",
        }
        and field_value_present(value)
        and (historical_published or field_name in locked_fields or field_name in {"file", "reader_asset", "authors", "translators", "chief_editors", "editors", "annotators", "photographers", "other_contributors"})
    }
    if discipline_rows and all(row[1] == RelationReviewStatus.APPROVED for row in discipline_rows):
        formally_confirmed.add("disciplines")
    if subdiscipline_rows and all(row[1] == RelationReviewStatus.APPROVED for row in subdiscipline_rows):
        formally_confirmed.add("subdisciplines")
    if (topic_rows or legacy_topic_rows) and all(row[1] == RelationReviewStatus.APPROVED for row in topic_rows) and all(
        row[1] == RelationReviewStatus.APPROVED and row[2]
        for row in legacy_topic_rows
    ):
        formally_confirmed.add("topics")
    if (theory_rows or legacy_theory_rows) and all(row[1] == KnowledgePublicationStatus.PUBLISHED for row in theory_rows) and all(
        row[1] == RelationReviewStatus.APPROVED and row[2]
        for row in legacy_theory_rows
    ):
        formally_confirmed.add("theories")
    if include_editorial_draft:
        from catalog.models import EditorialRevision

        draft = EditorialRevision.objects.filter(
            target_type="work", target_id=work.pk, status=EditorialRevision.Status.DRAFT,
        ).order_by("-revision").first()
        if draft is not None:
            original_values = dict(values)
            patch = dict(draft.patch or {})
            for name in SECTION_FIELDS["work"]:
                if name in patch:
                    values[name] = patch[name]
            bibliography = patch.get("bibliography") or {}
            if str(bibliography.get("edition_id")) == str(edition.pk):
                values.update({k: v for k, v in (bibliography.get("values") or {}).items() if k in SECTION_FIELDS["bibliography"]})
            contributors = patch.get("contributors") or {}
            if str(contributors.get("edition_id")) == str(edition.pk) and "contributors" in (contributors.get("values") or {}):
                values.update({name: [] for name in role_values})
                for row in contributors["values"]["contributors"]:
                    values[role_fields.get(row["role"], "other_contributors")].append(str(row["person_id"]))
            for name, rows in (patch.get("classification") or {}).items():
                if name in {"disciplines", "subdisciplines"}:
                    values[name] = [str(row["id"]) for row in rows]
            knowledge = patch.get("knowledge") or {}
            if "topics" in knowledge:
                values["topics"] = [str(row["id"]) for row in knowledge["topics"]]
            if "nodes" in knowledge or "theories" in knowledge:
                values["theories"] = [str(row["id"]) for row in [*knowledge.get("nodes", []), *knowledge.get("theories", [])]]
            formally_confirmed.difference_update(name for name in values if original_values.get(name) != values[name])
    return values, formally_confirmed


def _decision_map(edition: Edition) -> dict[str, CatalogFieldDecision]:
    return {
        row.field_name: row
        for row in edition.field_decisions.all()
    }


def field_readiness(edition: Edition) -> list[FieldReadiness]:
    decisions = _decision_map(edition)
    values, formally_confirmed = formal_field_values(edition)
    required = set(REQUIRED_FIELDS.get(values.get("document_type"), REQUIRED_FIELDS[DocumentType.BOOK]))
    field_names = sorted(required | set(REVIEWABLE_OPTIONAL_FIELDS) | set(decisions) | set(values))
    result = []
    for field_name in field_names:
        decision = decisions.get(field_name)
        value = values.get(field_name)
        present = field_value_present(value)
        if decision is None:
            status = (
                CatalogFieldDecision.Status.CONFIRMED if field_name in formally_confirmed
                else CatalogFieldDecision.Status.NEEDS_REVIEW if present
                else CatalogFieldDecision.Status.EMPTY
            )
        else:
            status = decision.status
            if status == CatalogFieldDecision.Status.CONFIRMED and not present:
                status = CatalogFieldDecision.Status.CONFLICT
            elif status == CatalogFieldDecision.Status.NOT_APPLICABLE and present:
                status = CatalogFieldDecision.Status.CONFLICT
            elif status == CatalogFieldDecision.Status.NOT_APPLICABLE and field_name in required:
                status = CatalogFieldDecision.Status.EMPTY
        result.append(
            FieldReadiness(
                field_name=field_name,
                status=status,
                value=value,
                required=field_name in required,
                stale_reason=(decision.stale_reason if decision else ""),
            )
        )
    return result


def section_statuses(edition: Edition) -> dict[str, dict[str, Any]]:
    readiness = {row.field_name: row for row in field_readiness(edition)}
    output: dict[str, dict[str, Any]] = {}
    for section, fields in SECTION_FIELDS.items():
        rows = [readiness[field] for field in fields if field in readiness]
        blockers = [
            row.field_name
            for row in rows
            if row.required
            and row.status
            not in {
                CatalogFieldDecision.Status.CONFIRMED,
                CatalogFieldDecision.Status.STALE,
            }
        ]
        conflicts = [
            row.field_name
            for row in rows
            if row.status == CatalogFieldDecision.Status.CONFLICT
        ]
        stale = [
            row.field_name
            for row in rows
            if row.status == CatalogFieldDecision.Status.STALE
        ]
        if conflicts:
            status = "conflict"
        elif blockers:
            status = "incomplete"
        elif stale:
            status = "needs_review"
        elif any(row.status in {CatalogFieldDecision.Status.SUGGESTED, CatalogFieldDecision.Status.NEEDS_REVIEW} for row in rows):
            status = "needs_review"
        elif any(row.status in {CatalogFieldDecision.Status.CONFIRMED, CatalogFieldDecision.Status.NOT_APPLICABLE} for row in rows):
            status = "complete"
        else:
            status = "available"
        output[section] = {
            "status": status,
            "blockers": blockers,
            "conflicts": conflicts,
            "stale": stale,
        }
    return output


def publication_field_check(edition: Edition) -> dict[str, Any]:
    rows = field_readiness(edition)
    blockers = []
    warnings = []
    for row in rows:
        if row.status == CatalogFieldDecision.Status.CONFLICT:
            blockers.append({"field": row.field_name, "code": "field_conflict"})
        elif row.required and (not field_value_present(row.value) or row.status not in {
            CatalogFieldDecision.Status.CONFIRMED,
            CatalogFieldDecision.Status.STALE,
        }):
            blockers.append({"field": row.field_name, "code": "required_field_incomplete"})
        elif row.status == CatalogFieldDecision.Status.STALE:
            warnings.append({"field": row.field_name, "code": "field_stale"})
    return {
        "blockers": blockers,
        "warnings": warnings,
        "can_publish": not blockers,
    }
