from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any

from django.db.models import Q

from catalog.models import (
    Asset,
    CanonicalObjectRevision,
    Edition,
    EnrichmentCandidate,
    KnowledgePublicationStatus,
    SemanticChunk,
    TheoryReviewTask,
)
from catalog.services.admin_workflow import build_edition_workflow, build_intake_workflow
from ingestion.models import EntityResolutionCandidate, FieldLock, MetadataCandidate, UploadItem


RESEARCH_CONTEXT_VERSION = "research-context-v2"
MAX_DRAFT_BYTES = 96_000
MAX_CHANGED_FIELDS = 32


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_value(row) for key, row in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(row) for row in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _bounded_draft(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    normalized = _json_value(value)
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    if len(encoded) > MAX_DRAFT_BYTES:
        raise ValueError("研究上下文中的未保存表单超过 96 KiB。")
    return normalized


def _stable_hash(value: Any) -> str:
    return sha256(
        json.dumps(
            _json_value(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _path_value(draft: dict[str, Any], persisted: dict[str, Any], path: str) -> Any:
    parts = [row for row in str(path or "").split(".") if row]
    if not parts:
        return None

    def read(source: Any) -> Any:
        current = source
        for part in parts:
            if isinstance(current, dict):
                if part not in current:
                    return None
                current = current[part]
            elif isinstance(current, list) and part.isdigit():
                index = int(part)
                if index >= len(current):
                    return None
                current = current[index]
            else:
                return None
        return current

    draft_value = read(draft)
    return draft_value if draft_value is not None else read(persisted)


def _canonical_revision(edition: Edition) -> dict[str, Any]:
    revisions = {
        row.object_type: row.current_revision
        for row in CanonicalObjectRevision.objects.filter(
            Q(object_type="work", object_id=edition.work_id)
            | Q(object_type="edition", object_id=edition.id)
        )
    }
    return {
        "work": int(revisions.get("work", 0)),
        "edition": int(revisions.get("edition", 0)),
        # Compatibility safeguard until every legacy save emits a DomainChange.
        # These timestamps keep Research identity correct during that migration.
        "work_updated_at": _json_value(edition.work.updated_at),
        "edition_updated_at": _json_value(edition.updated_at),
    }


def _candidate_state(edition: Edition, item: UploadItem | None) -> tuple[list[dict], list[dict]]:
    accepted: list[dict] = []
    rejected: list[dict] = []

    def remember(kind: str, rows, *, accepted_states: set[str], rejected_states: set[str]):
        for row in rows:
            payload = {
                "kind": kind,
                "id": str(row.id),
                "field": str(getattr(row, "field_name", "") or getattr(row, "target_type", "")),
                "status": str(getattr(row, "status", "") or getattr(row, "lifecycle", "")),
            }
            if payload["status"] in accepted_states:
                accepted.append(payload)
            elif payload["status"] in rejected_states:
                rejected.append(payload)

    if item is not None:
        remember(
            "metadata",
            MetadataCandidate.objects.filter(upload_item=item),
            accepted_states={MetadataCandidate.Lifecycle.ACCEPTED},
            rejected_states={MetadataCandidate.Lifecycle.REJECTED},
        )
        remember(
            "entity",
            EntityResolutionCandidate.objects.filter(upload_item=item),
            accepted_states={
                EntityResolutionCandidate.Status.LINKED,
                EntityResolutionCandidate.Status.CREATE_DRAFT,
                EntityResolutionCandidate.Status.UNRESOLVED,
            },
            rejected_states={EntityResolutionCandidate.Status.REJECTED, EntityResolutionCandidate.Status.IGNORED},
        )
    enrichment = EnrichmentCandidate.objects.filter(
        Q(target_type=EnrichmentCandidate.TargetType.WORK, target_id=edition.work_id)
        | Q(target_type=EnrichmentCandidate.TargetType.EDITION, target_id=edition.id)
    )
    remember(
        "enrichment",
        enrichment,
        accepted_states={EnrichmentCandidate.Status.ACCEPTED},
        rejected_states={EnrichmentCandidate.Status.REJECTED, EnrichmentCandidate.Status.SUPERSEDED},
    )
    remember(
        "theory",
        TheoryReviewTask.objects.filter(work_id=edition.work_id),
        accepted_states={TheoryReviewTask.TaskStatus.CONFIRMED},
        rejected_states={TheoryReviewTask.TaskStatus.REJECTED},
    )
    return accepted[:300], rejected[:300]


def _persisted_data(edition: Edition) -> dict[str, Any]:
    work = edition.work
    contributions = [
        {
            "id": str(row.id),
            "person_id": str(row.person_id),
            "display_name": row.person.preferred_name,
            "role": row.role,
            "order": row.order,
            "approved": row.approved,
        }
        for row in edition.contributions.select_related("person").order_by("order", "id")
    ]
    return {
        "work": {
            "id": str(work.id),
            "document_type": work.document_type,
            "title": work.title,
            "subtitle": work.subtitle,
            "original_title": work.original_title,
            "uniform_title": work.uniform_title,
            "canonical_title": work.uniform_title,
            "language": work.language,
            "original_language": work.original_language,
            "first_publication_date": work.first_publication_date,
            "abstract": work.abstract,
            "updated_at": work.updated_at,
        },
        "bibliography": {
            "id": str(edition.id),
            "version_label": edition.version_label,
            "edition_statement": edition.version_label,
            "publication_date": edition.publication_date,
            "publication_year": edition.publication_year,
            "publisher": edition.publisher,
            "publication_place": edition.publication_place,
            "isbn": edition.isbn,
            "isbn10": edition.isbn10,
            "isbn13": edition.isbn13,
            "series": edition.series,
            "extent": edition.extent,
            "responsibility_statement": edition.responsibility_statement,
            "journal_title": edition.journal_title,
            "volume": edition.volume,
            "issue": edition.issue,
            "page_range": edition.page_range,
            "doi": edition.doi,
            "degree_institution": edition.degree_institution,
            "degree_type": edition.degree_type,
            "report_institution": edition.report_institution,
            "state": edition.state,
            "updated_at": edition.updated_at,
        },
        "contributors": {"items": contributions},
        "classification": {
            "disciplines": [
                {
                    "id": str(row.discipline_id),
                    "name": row.discipline.name,
                    "is_primary": row.is_primary,
                    "review_status": row.review_status,
                }
                for row in work.discipline_relations.select_related("discipline")
            ],
            "subdisciplines": [
                {
                    "id": str(row.subdiscipline_id),
                    "name": row.subdiscipline.name,
                    "review_status": row.review_status,
                }
                for row in work.subdiscipline_relations.select_related("subdiscipline")
            ],
        },
        "knowledge": {
            "relations": [
                {
                    "id": str(row.id),
                    "target_type": "knowledge_node",
                    "target_id": str(row.node_id),
                    "review_status": row.status,
                    "role": row.role,
                }
                for row in work.node_relations.all()
            ],
        },
    }


def _confirmed_entities(edition: Edition) -> list[dict[str, Any]]:
    work = edition.work
    rows = [
        {
            "entity_type": "person",
            "entity_id": str(row.person_id),
            "label": row.person.preferred_name,
            "role": row.role,
        }
        for row in edition.contributions.select_related("person").filter(approved=True)
    ]
    rows.extend(
        {
            "entity_type": "discipline",
            "entity_id": str(row.discipline_id),
            "label": row.discipline.name,
            "role": "primary" if row.is_primary else "related",
        }
        for row in work.discipline_relations.select_related("discipline").filter(review_status="approved")
    )
    rows.extend(
        {
            "entity_type": "knowledge_node",
            "entity_id": str(row.node_id),
            "label": row.node.canonical_name_zh or row.node.canonical_name_en,
            "role": row.role,
        }
        for row in work.node_relations.select_related("node").filter(
            status=KnowledgePublicationStatus.PUBLISHED
        )
    )
    return rows[:300]


def _unresolved_entities(item: UploadItem | None, draft: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    if item is not None:
        rows.extend(
            {
                "entity_type": candidate.target_type,
                "label": candidate.source_name,
                "candidate_id": str(candidate.id),
            }
            for candidate in EntityResolutionCandidate.objects.filter(
                upload_item=item,
                status=EntityResolutionCandidate.Status.PROPOSED,
            )[:200]
        )
    for contributor in (draft.get("contributors") or {}).get("items") or []:
        if isinstance(contributor, dict) and contributor.get("display_name") and not contributor.get("person_id"):
            rows.append({
                "entity_type": "person",
                "label": str(contributor["display_name"]).strip(),
                "draft_path": "contributors.items",
            })
    return rows[:300]


def _pdf_signals(edition: Edition) -> dict[str, Any]:
    assets = edition.assets.filter(is_current=True)
    return {
        "asset_count": assets.count(),
        "ready_assets": assets.filter(status=Asset.Status.READY).count(),
        "page_count": sum(asset.pages.count() for asset in assets[:20]),
        "semantic_chunks": SemanticChunk.objects.filter(asset__edition=edition).count(),
        "semantic_chunks_ready": SemanticChunk.objects.filter(
            asset__edition=edition,
            index_status=SemanticChunk.IndexStatus.READY,
        ).count(),
        "ocr_status": edition.ocr_status,
        "page_label_status": edition.page_label_status,
        "semantic_index_status": edition.semantic_index_status,
    }


@dataclass(frozen=True)
class ResearchContext:
    work_id: str
    edition_id: str
    upload_item_id: str | None
    document_type: str
    active_step: str
    persisted_data: dict[str, Any]
    draft_data: dict[str, Any]
    confirmed_entities: list[dict[str, Any]]
    unresolved_entities: list[dict[str, Any]]
    accepted_candidates: list[dict[str, Any]]
    rejected_candidates: list[dict[str, Any]]
    field_locks: list[dict[str, Any]]
    pdf_ocr_signals: dict[str, Any]
    workflow_status: dict[str, Any]
    canonical_revision: dict[str, Any] = field(default_factory=dict)
    draft_session_id: str = ""
    draft_hash: str = ""
    trigger_input_values: dict[str, Any] = field(default_factory=dict)
    trigger_input_hash: str = ""
    workflow_gaps: list[dict[str, Any]] = field(default_factory=list)
    changed_fields: tuple[str, ...] = ()
    fingerprint: str = ""
    version: str = RESEARCH_CONTEXT_VERSION

    def payload(self) -> dict[str, Any]:
        return _json_value(asdict(self))

    def draft_value(self, step: str, field_name: str, default: Any = "") -> Any:
        step_data = self.draft_data.get(step)
        if isinstance(step_data, dict) and field_name in step_data:
            return step_data[field_name]
        persisted = self.persisted_data.get(step)
        if isinstance(persisted, dict):
            return persisted.get(field_name, default)
        return default


def build_research_context(
    edition: Edition,
    *,
    item: UploadItem | None = None,
    active_step: str,
    draft_data: dict[str, Any] | None = None,
    changed_fields: list[str] | tuple[str, ...] | None = None,
    draft_session_id: str = "",
) -> ResearchContext:
    edition = Edition.objects.select_related("work").get(pk=edition.pk)
    if item is not None:
        item = UploadItem.objects.select_related("edition__work").get(pk=item.pk)
        if item.edition_id != edition.id:
            raise ValueError("ResearchContext 的 UploadItem 与 Edition 不一致。")
    draft = _bounded_draft(draft_data or {})
    changed = tuple(dict.fromkeys(str(value).strip() for value in (changed_fields or []) if str(value).strip()))
    if len(changed) > MAX_CHANGED_FIELDS:
        raise ValueError("一次研究最多声明 32 个 changed fields。")
    persisted = _persisted_data(edition)
    canonical_revision = _canonical_revision(edition)
    normalized_session_id = str(draft_session_id or "").strip()[:96]
    draft_hash = _stable_hash(draft)
    # Import locally to keep context construction independent from registry
    # initialization order.
    from .contracts import RESEARCH_CONTRACTS

    trigger_paths = {
        path
        for contract in RESEARCH_CONTRACTS.all()
        for path in contract.effective_trigger_inputs
        if path
    }
    trigger_paths.update(changed)
    trigger_input_values = {
        path: _json_value(_path_value(draft, persisted, path))
        for path in sorted(trigger_paths)
    }
    trigger_input_hash = _stable_hash(trigger_input_values)
    accepted, rejected = _candidate_state(edition, item)
    workflow = build_intake_workflow(item) if item else build_edition_workflow(edition)
    locks = [
        {
            "field": row.field_name,
            "value": row.locked_value,
            "reason": row.reason,
            "updated_at": row.updated_at,
        }
        for row in FieldLock.objects.filter(edition=edition).order_by("field_name")
    ]
    base = {
        "version": RESEARCH_CONTEXT_VERSION,
        "work_id": str(edition.work_id),
        "edition_id": str(edition.id),
        "upload_item_id": str(item.id) if item else None,
        "document_type": edition.work.document_type,
        "active_step": str(active_step or "work").strip().casefold(),
        "persisted_data": _json_value(persisted),
        "draft_data": draft,
        "confirmed_entities": _confirmed_entities(edition),
        "unresolved_entities": _unresolved_entities(item, draft),
        "accepted_candidates": accepted,
        "rejected_candidates": rejected,
        "field_locks": _json_value(locks),
        "pdf_ocr_signals": _pdf_signals(edition),
        "workflow_status": _json_value(workflow),
        "changed_fields": list(changed),
        "canonical_revision": canonical_revision,
        "draft_session_id": normalized_session_id,
        "draft_hash": draft_hash,
        "trigger_input_values": trigger_input_values,
        "trigger_input_hash": trigger_input_hash,
    }
    fingerprint = sha256(
        json.dumps(base, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return ResearchContext(
        work_id=base["work_id"],
        edition_id=base["edition_id"],
        upload_item_id=base["upload_item_id"],
        document_type=base["document_type"],
        active_step=base["active_step"],
        persisted_data=base["persisted_data"],
        draft_data=draft,
        confirmed_entities=base["confirmed_entities"],
        unresolved_entities=base["unresolved_entities"],
        accepted_candidates=accepted,
        rejected_candidates=rejected,
        field_locks=base["field_locks"],
        pdf_ocr_signals=base["pdf_ocr_signals"],
        workflow_status=base["workflow_status"],
        canonical_revision=canonical_revision,
        draft_session_id=normalized_session_id,
        draft_hash=draft_hash,
        trigger_input_values=trigger_input_values,
        trigger_input_hash=trigger_input_hash,
        changed_fields=changed,
        fingerprint=fingerprint,
    )
