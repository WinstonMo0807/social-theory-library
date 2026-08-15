from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from ingestion.models import DecisionLog, MetadataCandidate, UploadItem

from .candidate_store import normalized_value
from .metadata_scoring import normalized_candidate_value


FIELD_PAYLOAD_MAP = {
    "title": "title",
    "subtitle": "subtitle",
    "document_type": "document_type",
    "language": "language",
    "abstract": "abstract",
    "version_label": "version_label",
    "publication_year": "publication_year",
    "publisher": "publisher",
    "publication_place": "publication_place",
    "journal_title": "journal_title",
    "volume": "volume",
    "issue": "issue",
    "page_range": "page_range",
    "degree_institution": "degree_institution",
    "degree_type": "degree_type",
    "report_institution": "report_institution",
    "isbn": "isbn",
    "doi": "doi",
    "authors": "authors",
    "disciplines": "disciplines",
    "subdisciplines": "subdisciplines",
    "theory_schools": "theory_schools",
    "topics": "topics",
}


def _submitted_value(field_name: str, payload: dict):
    key = FIELD_PAYLOAD_MAP.get(field_name)
    if not key or key not in payload:
        return None, False
    value = payload[key]
    if field_name == "publication_year" and value in ("", None):
        return None, True
    return value, True


def _candidate_matches(candidate: MetadataCandidate, submitted) -> bool:
    if candidate.field_name in {"disciplines", "subdisciplines", "theory_schools", "topics"}:
        submitted_values = submitted if isinstance(submitted, list) else [submitted]
        candidate_values = candidate.value if isinstance(candidate.value, list) else [candidate.value]
        submitted_keys = {normalized_candidate_value(value) for value in submitted_values}
        return any(normalized_candidate_value(value) in submitted_keys for value in candidate_values)
    return normalized_candidate_value(candidate.value) == normalized_candidate_value(submitted)


@transaction.atomic
def accept_candidates_from_review(
    item: UploadItem,
    payload: dict,
    *,
    actor,
    locked_fields: set[str],
) -> int:
    """Record only candidates that match the administrator's saved values."""

    accepted_count = 0
    now = timezone.now()
    candidates = list(item.metadata_candidates.select_for_update().order_by("field_name", "-confidence"))
    by_field: dict[str, list[MetadataCandidate]] = {}
    for candidate in candidates:
        by_field.setdefault(candidate.field_name, []).append(candidate)

    for field_name, field_candidates in by_field.items():
        submitted, present = _submitted_value(field_name, payload)
        if not present:
            continue
        matches = [candidate for candidate in field_candidates if _candidate_matches(candidate, submitted)]
        if not matches:
            continue
        chosen = sorted(matches, key=lambda value: value.confidence, reverse=True)[0]
        for candidate in field_candidates:
            if candidate.pk == chosen.pk:
                continue
            if candidate.lifecycle == MetadataCandidate.Lifecycle.ACCEPTED:
                candidate.lifecycle = MetadataCandidate.Lifecycle.SUPERSEDED
                candidate.selected = False
                candidate.save(update_fields=["lifecycle", "selected", "updated_at"])
        before = {
            "lifecycle": chosen.lifecycle,
            "selected": chosen.selected,
            "is_locked": chosen.is_locked,
        }
        changed = chosen.lifecycle != MetadataCandidate.Lifecycle.ACCEPTED or not chosen.selected
        chosen.lifecycle = MetadataCandidate.Lifecycle.ACCEPTED
        chosen.selected = True
        chosen.is_locked = field_name in locked_fields
        chosen.accepted_by = actor
        chosen.accepted_at = now
        chosen.rejected_by = None
        chosen.rejected_at = None
        chosen.normalized_value = normalized_value(chosen.value)
        chosen.save(
            update_fields=[
                "lifecycle",
                "selected",
                "is_locked",
                "accepted_by",
                "accepted_at",
                "rejected_by",
                "rejected_at",
                "normalized_value",
                "updated_at",
            ]
        )
        if changed:
            DecisionLog.objects.create(
                upload_item=item,
                metadata_candidate=chosen,
                actor=actor,
                action="accept_metadata_candidate",
                target_type="metadata_field",
                target_id=field_name,
                before=before,
                after={
                    "lifecycle": chosen.lifecycle,
                    "selected": True,
                    "is_locked": chosen.is_locked,
                    "value": chosen.value,
                },
                reason="管理员保存元数据复核",
            )
            accepted_count += 1
    return accepted_count


@transaction.atomic
def set_candidate_decision(candidate: MetadataCandidate, *, action: str, actor) -> MetadataCandidate:
    candidate = MetadataCandidate.objects.select_for_update().get(pk=candidate.pk)
    before = {
        "lifecycle": candidate.lifecycle,
        "selected": candidate.selected,
        "is_locked": candidate.is_locked,
    }
    if action == "reject":
        if candidate.is_locked or candidate.lifecycle == MetadataCandidate.Lifecycle.ACCEPTED:
            raise ValueError("已接受或锁定的候选需先在元数据表单中改选并保存。")
        candidate.lifecycle = MetadataCandidate.Lifecycle.REJECTED
        candidate.selected = False
        candidate.rejected_by = actor
        candidate.rejected_at = timezone.now()
    elif action == "reopen":
        if candidate.lifecycle not in {
            MetadataCandidate.Lifecycle.REJECTED,
            MetadataCandidate.Lifecycle.SUPERSEDED,
        }:
            raise ValueError("只有已拒绝或已被替代的候选可以恢复待审。")
        candidate.lifecycle = MetadataCandidate.Lifecycle.PROPOSED
        candidate.selected = False
        candidate.rejected_by = None
        candidate.rejected_at = None
    else:
        raise ValueError("不支持的候选决定。")
    candidate.save(
        update_fields=[
            "lifecycle",
            "selected",
            "rejected_by",
            "rejected_at",
            "updated_at",
        ]
    )
    DecisionLog.objects.create(
        upload_item=candidate.upload_item,
        metadata_candidate=candidate,
        actor=actor,
        action=f"{action}_metadata_candidate",
        target_type="metadata_candidate",
        target_id=str(candidate.id),
        before=before,
        after={
            "lifecycle": candidate.lifecycle,
            "selected": candidate.selected,
            "is_locked": candidate.is_locked,
        },
    )
    return candidate
