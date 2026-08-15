from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Iterable
import uuid

from django.db import transaction

from catalog.models import Contribution, Person
from ingestion.models import (
    CandidateEvidence,
    DecisionLog,
    FieldLock,
    MetadataCandidate,
    ReviewTask,
    SourceRecord,
    UploadItem,
)

from .candidate_store import normalized_value
from .metadata import Candidate
from .metadata_scoring import calibrate_candidate, normalized_candidate_value
from .reconciliation import normalized_label, persist_resolution_candidates


BACKFILL_VERSION = "admin-foundation-v1"
MULTI_VALUE_REVIEW_FIELDS = {
    "disciplines",
    "subdisciplines",
    "theory_schools",
    "topics",
}
EXTERNAL_SOURCE_MAP = {
    "crossref": ("crossref", "lookup_doi"),
    "crossref_title": ("crossref", "search_book"),
    "openlibrary": ("openlibrary", "lookup_isbn"),
    "openlibrary_search": ("openlibrary", "search_book"),
    "openlibrary_title": ("openlibrary", "search_book"),
    "google_books": ("google_books", "lookup_isbn"),
    "google_books_title": ("google_books", "search_book"),
}


@dataclass(frozen=True, slots=True)
class BackfillAction:
    code: str
    target_type: str
    target_id: str
    reason: str
    details: dict

    def as_dict(self) -> dict:
        return asdict(self)


def _limited(queryset, limit: int):
    return queryset if limit == 0 else queryset[:limit]


def _stable_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _conflict_group(item_id, field_name: str) -> str:
    return sha256(f"{item_id}:{field_name}".encode("utf-8")).hexdigest()[:32]


def _matching_values(first, second) -> bool:
    if first is True or second is True or first is None or second is None:
        return False
    if isinstance(first, list) or isinstance(second, list):
        first_values = first if isinstance(first, list) else [first]
        second_values = second if isinstance(second, list) else [second]
        return {
            normalized_candidate_value(value) for value in first_values
        } == {
            normalized_candidate_value(value) for value in second_values
        }
    return normalized_candidate_value(first) == normalized_candidate_value(second)


def _author_names(value) -> list[str]:
    if isinstance(value, str):
        return [" ".join(value.split()).strip()] if value.strip() else []
    if isinstance(value, dict):
        name = value.get("preferred_name") or value.get("name") or value.get("literal")
        return _author_names(name)
    if not isinstance(value, list):
        return []
    names = []
    for entry in value:
        names.extend(_author_names(entry))
    return names


def _source_spec(candidate: MetadataCandidate) -> tuple[str, str, dict, str] | None:
    source = candidate.source.casefold().strip()
    spec = EXTERNAL_SOURCE_MAP.get(source)
    if spec is None:
        return None
    evidence = candidate.evidence if isinstance(candidate.evidence, dict) else {}
    query = {
        key: evidence[key]
        for key in ("doi", "isbn", "record_url", "key", "query", "query_title", "volume_id", "edition_key")
        if evidence.get(key) not in (None, "", [], {})
    }
    if candidate.field_name in {"doi", "isbn"} and candidate.value:
        query.setdefault(candidate.field_name, candidate.value)
    if not query:
        return None
    external_id = str(
        query.get("doi")
        or query.get("isbn")
        or query.get("key")
        or query.get("record_url")
        or ""
    )[:255]
    return spec[0], spec[1], query, external_id


def _source_record_id_from_evidence(candidate: MetadataCandidate) -> str:
    evidence = candidate.evidence if isinstance(candidate.evidence, dict) else {}
    value = str(evidence.get("source_record_id") or "").strip()
    if not value:
        return ""
    try:
        identifier = str(uuid.UUID(value))
    except (TypeError, ValueError, AttributeError):
        return ""
    return (
        identifier
        if SourceRecord.objects.filter(
            pk=identifier,
            upload_item_id=candidate.upload_item_id,
        ).exists()
        else ""
    )


def _active_task_exists(*, task_type: str, target_type: str, target_id: str) -> bool:
    return ReviewTask.objects.filter(
        task_type=task_type,
        target_type=target_type,
        target_id=target_id,
    ).exists()


def _candidate_object(row: MetadataCandidate) -> Candidate:
    return Candidate(
        field_name=row.field_name,
        value=row.value,
        source=row.source,
        confidence=row.confidence,
        evidence=row.evidence if isinstance(row.evidence, dict) else {},
    )


def _candidate_needs_evidence(row: MetadataCandidate) -> bool:
    return bool(row.evidence) and not row.evidence_records.exists()


def plan_admin_foundation_backfill(
    *,
    item_ids: Iterable[str] = (),
    person_ids: Iterable[str] = (),
    limit: int = 500,
) -> list[BackfillAction]:
    actions: list[BackfillAction] = []
    person_queryset = Person.objects.prefetch_related("contributions", "scholar_profile")
    if person_ids:
        person_queryset = person_queryset.filter(pk__in=person_ids)
    people = list(_limited(person_queryset.order_by("created_at", "id"), limit))

    people_by_name: dict[str, list[Person]] = defaultdict(list)
    for person in people:
        name_key = normalized_label(person.preferred_name)
        if name_key:
            people_by_name[name_key].append(person)
        has_approved_contribution = person.contributions.filter(
            role=Contribution.Role.AUTHOR,
            approved=True,
        ).exists()
        signals = []
        if has_approved_contribution:
            signals.append("已有审核通过的作者贡献")
        if hasattr(person, "scholar_profile"):
            signals.append("已有学者档案")
        if person.external_ids:
            signals.append("已有外部权威标识符")
        if signals and person.authority_status == Person.AuthorityStatus.DRAFT:
            actions.append(
                BackfillAction(
                    "person_mark_needs_review",
                    "person",
                    str(person.id),
                    "既有人物已被馆藏使用，但身份不能仅凭名称自动核验",
                    {"signals": signals, "from": "draft", "to": "needs_review"},
                )
            )
        if signals and person.authority_status in {
            Person.AuthorityStatus.DRAFT,
            Person.AuthorityStatus.NEEDS_REVIEW,
        } and not _active_task_exists(
            task_type="authority_reconciliation",
            target_type="person",
            target_id=str(person.id),
        ):
            actions.append(
                BackfillAction(
                    "person_review_task",
                    "person",
                    str(person.id),
                    "需要人工核对人物身份与外部标识符",
                    {"preferred_name": person.preferred_name, "signals": signals},
                )
            )

    for name_key, duplicates in people_by_name.items():
        if len(duplicates) < 2:
            continue
        group_id = sha256(name_key.encode("utf-8")).hexdigest()[:32]
        if _active_task_exists(
            task_type="duplicate_person_authority",
            target_type="person_duplicate",
            target_id=group_id,
        ):
            continue
        actions.append(
            BackfillAction(
                "person_duplicate_review",
                "person_duplicate",
                group_id,
                "规范化姓名相同，禁止自动合并",
                {
                    "normalized_name": name_key,
                    "people": [
                        {
                            "id": str(person.id),
                            "preferred_name": person.preferred_name,
                            "authority_status": person.authority_status,
                            "external_ids": person.external_ids,
                        }
                        for person in duplicates
                    ],
                    "automatic_merge_allowed": False,
                },
            )
        )

    item_queryset = UploadItem.objects.select_related("edition", "asset").prefetch_related(
        "metadata_candidates__evidence_records",
        "metadata_candidates__source_record",
        "entity_resolution_candidates",
        "review_tasks",
    )
    if item_ids:
        item_queryset = item_queryset.filter(pk__in=item_ids)
    items = list(_limited(item_queryset.order_by("created_at", "id"), limit))
    for item in items:
        existing_author_keys = {
            normalized_label(row.source_name)
            for row in item.entity_resolution_candidates.all()
            if row.target_type == "person"
        }
        authors = _author_names((item.recognized_metadata or {}).get("authors", []))
        candidates = list(item.metadata_candidates.all())
        for candidate in candidates:
            if candidate.field_name == "authors":
                authors.extend(_author_names(candidate.value))
        for author in dict.fromkeys(authors):
            author_key = normalized_label(author)
            if not author_key or author_key in existing_author_keys:
                continue
            actions.append(
                BackfillAction(
                    "author_reconciliation",
                    "upload_item",
                    str(item.id),
                    "既有作者字符串尚未进入实体消歧",
                    {"author": author, "normalized_name": author_key},
                )
            )
            existing_author_keys.add(author_key)

        locks = {
            lock.field_name: lock
            for lock in FieldLock.objects.filter(edition=item.edition)
        } if item.edition_id else {}
        by_field: dict[str, list[MetadataCandidate]] = defaultdict(list)
        for candidate in candidates:
            by_field[candidate.field_name].append(candidate)

        for field_name, field_candidates in by_field.items():
            accepted = [
                row for row in field_candidates
                if row.lifecycle == MetadataCandidate.Lifecycle.ACCEPTED
            ]
            lock = locks.get(field_name)
            matching_lock = [
                row for row in field_candidates
                if lock is not None and _matching_values(row.value, lock.locked_value)
            ]
            chosen_lock = max(matching_lock, key=lambda row: row.confidence) if matching_lock else None
            group_issues = []
            if len(accepted) > 1:
                group_issues.append("同一字段存在多个已接受候选")
            active_values = {
                normalized_candidate_value(row.value)
                for row in field_candidates
                if row.lifecycle in {
                    MetadataCandidate.Lifecycle.PROPOSED,
                    MetadataCandidate.Lifecycle.ACCEPTED,
                }
                and normalized_candidate_value(row.value)
            }
            if field_name not in MULTI_VALUE_REVIEW_FIELDS and len(active_values) > 1:
                group_issues.append("同一书目字段存在互相冲突的候选值")
            if lock is not None and accepted and not any(
                _matching_values(row.value, lock.locked_value) for row in accepted
            ):
                group_issues.append("已接受候选与人工字段锁不一致")
            if group_issues and not _active_task_exists(
                task_type="metadata_candidate_consistency",
                target_type="metadata_field",
                target_id=f"{item.id}:{field_name}"[:128],
            ):
                actions.append(
                    BackfillAction(
                        "candidate_review_task",
                        "metadata_field",
                        f"{item.id}:{field_name}"[:128],
                        "；".join(group_issues),
                        {
                            "upload_item_id": str(item.id),
                            "field_name": field_name,
                            "candidate_ids": [str(row.id) for row in accepted],
                        },
                    )
                )

            for candidate in field_candidates:
                fields = []
                if candidate.normalized_value in ({}, None, "") and candidate.value not in ({}, None, ""):
                    fields.append("normalized_value")
                if not candidate.conflict_group:
                    fields.append("conflict_group")
                if not candidate.score_factors:
                    fields.append("score_factors")
                if candidate.source_record_id is None:
                    existing_source_id = _source_record_id_from_evidence(candidate)
                    if existing_source_id:
                        fields.append("source_record_from_evidence")
                    elif _source_spec(candidate):
                        fields.append("source_record")
                if _candidate_needs_evidence(candidate):
                    fields.append("candidate_evidence")
                if (
                    chosen_lock
                    and candidate.id == chosen_lock.id
                    and not accepted
                    and candidate.selected
                ):
                    fields.append("accepted_from_field_lock")
                elif chosen_lock and candidate.id == chosen_lock.id and candidate in accepted:
                    if (
                        not candidate.is_locked
                        or candidate.accepted_by_id is None
                        or candidate.accepted_at is None
                        or not candidate.selected
                    ):
                        fields.append("accepted_provenance_from_field_lock")
                if fields:
                    actions.append(
                        BackfillAction(
                            "candidate_enrich",
                            "metadata_candidate",
                            str(candidate.id),
                            "补齐可由既有记录直接证明的候选来源与状态",
                            {
                                "upload_item_id": str(item.id),
                                "field_name": field_name,
                                "fields": fields,
                                "field_lock_id": str(lock.id) if lock and chosen_lock == candidate else "",
                                "source_record_id": (
                                    _source_record_id_from_evidence(candidate)
                                    if "source_record_from_evidence" in fields
                                    else ""
                                ),
                            },
                        )
                    )

                inconsistent = (
                    candidate.lifecycle == MetadataCandidate.Lifecycle.ACCEPTED
                    and (not candidate.selected or candidate.accepted_by_id is None)
                    and not (lock and chosen_lock == candidate)
                ) or (
                    candidate.lifecycle != MetadataCandidate.Lifecycle.ACCEPTED
                    and candidate.selected
                    and not (lock and chosen_lock == candidate and not accepted)
                )
                if inconsistent and not _active_task_exists(
                    task_type="legacy_candidate_provenance",
                    target_type="metadata_candidate",
                    target_id=str(candidate.id),
                ):
                    actions.append(
                        BackfillAction(
                            "candidate_review_task",
                            "metadata_candidate",
                            str(candidate.id),
                            "旧候选状态缺少足够的人工决定来源",
                            {
                                "upload_item_id": str(item.id),
                                "field_name": candidate.field_name,
                                "lifecycle": candidate.lifecycle,
                                "selected": candidate.selected,
                                "accepted_by": str(candidate.accepted_by_id or ""),
                            },
                        )
                    )
    return actions


def _ensure_review_task(action: BackfillAction) -> bool:
    task_type = {
        "person_review_task": "authority_reconciliation",
        "person_duplicate_review": "duplicate_person_authority",
    }.get(action.code)
    if action.code == "candidate_review_task":
        task_type = (
            "legacy_candidate_provenance"
            if action.target_type == "metadata_candidate"
            else "metadata_candidate_consistency"
        )
    if task_type is None:
        return False
    if _active_task_exists(
        task_type=task_type,
        target_type=action.target_type,
        target_id=action.target_id,
    ):
        return False
    upload_item_id = action.details.get("upload_item_id")
    ReviewTask.objects.create(
        upload_item_id=upload_item_id or None,
        task_type=task_type,
        target_type=action.target_type,
        target_id=action.target_id,
        title=action.reason,
        details={**action.details, "backfill_version": BACKFILL_VERSION},
    )
    return True


def _legacy_source_record(candidate: MetadataCandidate) -> SourceRecord | None:
    spec = _source_spec(candidate)
    if spec is None:
        return None
    provider, operation, query, external_id = spec
    fingerprint = sha256(
        _stable_json({"provider": provider, "operation": operation, "query": query}).encode("utf-8")
    ).hexdigest()
    existing = SourceRecord.objects.filter(
        upload_item=candidate.upload_item,
        provider=provider,
        operation=operation,
        request_fingerprint=fingerprint,
    ).order_by("created_at").first()
    if existing:
        return existing
    return SourceRecord.objects.create(
        upload_item=candidate.upload_item,
        provider=provider,
        operation=operation,
        query=query,
        request_fingerprint=fingerprint,
        external_id=external_id,
        raw_response={
            "legacy_candidate_snapshot": {
                "field_name": candidate.field_name,
                "value": candidate.value,
                "source": candidate.source,
                "evidence": candidate.evidence,
            },
            "raw_response_available": False,
            "backfill_version": BACKFILL_VERSION,
        },
        provider_version="legacy-record",
        status=SourceRecord.Status.SUCCEEDED,
    )


def _create_candidate_evidence(candidate: MetadataCandidate) -> bool:
    if not candidate.evidence or candidate.evidence_records.exists():
        return False
    evidence = candidate.evidence if isinstance(candidate.evidence, dict) else {}
    page_number = evidence.get("page")
    if page_number is None and isinstance(evidence.get("page_range"), list) and evidence["page_range"]:
        page_number = evidence["page_range"][0]
    try:
        page_number = int(page_number) if page_number is not None else None
        if page_number is not None and page_number < 1:
            page_number = None
    except (TypeError, ValueError):
        page_number = None
    bbox = evidence.get("bbox") if isinstance(evidence.get("bbox"), list) else []
    CandidateEvidence.objects.create(
        metadata_candidate=candidate,
        asset=candidate.upload_item.asset,
        source_record=candidate.source_record,
        page_number=page_number,
        bbox=bbox,
        text_quote=str(evidence.get("text_quote") or evidence.get("quote") or "")[:4000],
        source_kind=(candidate.source or "legacy")[:40],
        external_identifier=str(
            evidence.get("record_url") or evidence.get("doi") or evidence.get("isbn") or ""
        )[:400],
        extraction_method=str(evidence.get("extraction_method") or candidate.source)[:80],
        model_name=str(evidence.get("model_name") or "")[:160],
        model_revision=str(evidence.get("model_revision") or "")[:160],
    )
    return True


def _enrich_candidate(action: BackfillAction) -> bool:
    candidate = MetadataCandidate.objects.select_for_update().select_related(
        "upload_item",
    ).get(pk=action.target_id)
    fields = set(action.details.get("fields") or [])
    before = {
        "lifecycle": candidate.lifecycle,
        "selected": candidate.selected,
        "is_locked": candidate.is_locked,
        "accepted_by": str(candidate.accepted_by_id or ""),
        "accepted_at": candidate.accepted_at.isoformat() if candidate.accepted_at else "",
    }
    updates = []
    if "normalized_value" in fields and candidate.normalized_value in ({}, None, ""):
        candidate.normalized_value = normalized_value(candidate.value)
        updates.append("normalized_value")
    if "conflict_group" in fields and not candidate.conflict_group:
        candidate.conflict_group = _conflict_group(candidate.upload_item_id, candidate.field_name)
        updates.append("conflict_group")
    if "score_factors" in fields and not candidate.score_factors:
        siblings = [
            _candidate_object(row)
            for row in candidate.upload_item.metadata_candidates.filter(field_name=candidate.field_name)
        ]
        candidate.score_factors = calibrate_candidate(_candidate_object(candidate), siblings).factors
        updates.append("score_factors")
    if "source_record" in fields and candidate.source_record_id is None:
        source_record = _legacy_source_record(candidate)
        if source_record is not None:
            candidate.source_record = source_record
            updates.append("source_record")
    if "source_record_from_evidence" in fields and candidate.source_record_id is None:
        source_record = SourceRecord.objects.filter(
            pk=action.details.get("source_record_id"),
            upload_item_id=candidate.upload_item_id,
        ).first()
        if source_record is not None:
            candidate.source_record = source_record
            updates.append("source_record")
    if {"accepted_from_field_lock", "accepted_provenance_from_field_lock"} & fields:
        lock_id = action.details.get("field_lock_id")
        lock = FieldLock.objects.filter(pk=lock_id, edition=candidate.upload_item.edition).first()
        if lock and _matching_values(candidate.value, lock.locked_value):
            candidate.lifecycle = MetadataCandidate.Lifecycle.ACCEPTED
            candidate.selected = True
            candidate.is_locked = True
            candidate.accepted_by = lock.locked_by
            candidate.accepted_at = candidate.accepted_at or lock.created_at
            candidate.rejected_by = None
            candidate.rejected_at = None
            updates.extend(
                [
                    "lifecycle",
                    "selected",
                    "is_locked",
                    "accepted_by",
                    "accepted_at",
                    "rejected_by",
                    "rejected_at",
                ]
            )
            decision_action = (
                "backfill_accept_metadata_candidate"
                if "accepted_from_field_lock" in fields
                else "backfill_metadata_candidate_provenance"
            )
            DecisionLog.objects.get_or_create(
                upload_item=candidate.upload_item,
                metadata_candidate=candidate,
                actor=lock.locked_by,
                action=decision_action,
                target_type="metadata_candidate",
                target_id=str(candidate.id),
                defaults={
                    "before": before,
                    "after": {
                        "lifecycle": MetadataCandidate.Lifecycle.ACCEPTED,
                        "selected": True,
                        "is_locked": True,
                        "accepted_by": str(lock.locked_by_id),
                        "accepted_at": (candidate.accepted_at or lock.created_at).isoformat(),
                    },
                    "reason": "由既有人工字段锁补齐候选决定来源",
                    "correlation_id": f"{BACKFILL_VERSION}:{candidate.id}",
                },
            )
    if updates:
        candidate.save(update_fields=[*dict.fromkeys(updates), "updated_at"])
    evidence_created = False
    if "candidate_evidence" in fields:
        evidence_created = _create_candidate_evidence(candidate)
    return bool(updates or evidence_created)


@transaction.atomic
def apply_admin_foundation_backfill(actions: Iterable[BackfillAction]) -> dict[str, int]:
    applied: Counter[str] = Counter()
    for action in actions:
        changed = False
        if action.code == "person_mark_needs_review":
            changed = bool(
                Person.objects.filter(
                    pk=action.target_id,
                    authority_status=Person.AuthorityStatus.DRAFT,
                ).update(authority_status=Person.AuthorityStatus.NEEDS_REVIEW)
            )
        elif action.code in {
            "person_review_task",
            "person_duplicate_review",
            "candidate_review_task",
        }:
            changed = _ensure_review_task(action)
        elif action.code == "author_reconciliation":
            item = UploadItem.objects.get(pk=action.target_id)
            before = item.entity_resolution_candidates.count()
            persist_resolution_candidates(
                item,
                target_type="person",
                source_name=action.details["author"],
            )
            changed = item.entity_resolution_candidates.count() > before
        elif action.code == "candidate_enrich":
            changed = _enrich_candidate(action)
        if changed:
            applied[action.code] += 1
    return dict(sorted(applied.items()))


def action_summary(actions: Iterable[BackfillAction]) -> dict[str, int]:
    return dict(sorted(Counter(action.code for action in actions).items()))
