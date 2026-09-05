from __future__ import annotations

from collections.abc import Iterable

from django.db import transaction

from catalog.services.dependency_engine import record_canonical_change


ENTITY_PUBLICATION_TYPES = {
    "person", "scholar_profile", "knowledge_node", "discipline",
    "subdiscipline", "topic", "reading_path", "theory_school", "knowledge_relation",
}


def _is_published(target, object_type: str) -> bool:
    if object_type == "person":
        return target.authority_status == "verified"
    if object_type == "scholar_profile":
        return target.editorial_status == "published" and target.person.authority_status == "verified"
    if object_type == "knowledge_relation":
        return target.status == "published" and target.source_node.status == "published" and target.target_node.status == "published"
    return getattr(target, "editorial_status", getattr(target, "status", "")) == "published"


@transaction.atomic
def record_admin_canonical_change(
    *,
    object_type: str,
    target,
    change_kind: str,
    changed_fields: Iterable[str] | None,
    actor,
    request_idempotency_key: str = "",
):
    """Record one explicit admin mutation in the shared dependency runtime.

    Callers invoke this inside the same database transaction as the canonical
    save. The generated key is stable for that saved object revision while an
    optional request key makes client retries deterministic.
    """

    request_key = str(request_idempotency_key or "").strip()
    if request_key:
        suffix = request_key[:120]
    else:
        marker = getattr(target, "updated_at", None)
        suffix = marker.isoformat() if marker is not None else str(target.pk)
    key = (
        f"admin-mutation:{object_type}:{target.pk}:{change_kind}:{suffix}"
    )[:200]
    # Candidate adoption is a draft action even when its target is currently
    # published. Missing revision adapters must roll back the entire adoption,
    # not accidentally turn acceptance into a knowledge publication.
    if request_key.startswith("field-enrichment:"):
        if object_type in ENTITY_PUBLICATION_TYPES and _is_published(target, object_type):
            raise ValueError("该建议未能写入编辑草稿，未保存成功。")
        if object_type == "edition" and target.state == "published":
            raise ValueError("已发布版本必须先写入编辑草稿，未保存成功。")
        if object_type == "work" and target.editions.filter(state="published").exists():
            raise ValueError("已发布作品必须先写入编辑草稿，未保存成功。")
        return None
    if object_type in ENTITY_PUBLICATION_TYPES:
        if change_kind != "withdraw" and not _is_published(target, object_type):
            return None
        from catalog.models import KnowledgePublicationEvent
        from catalog.services.knowledge_publication import create_entity_publication_event

        event_type = {
            "publish": KnowledgePublicationEvent.EventType.ENTITY_PUBLISHED,
            "merge": KnowledgePublicationEvent.EventType.ENTITY_MERGED,
        }.get(change_kind, KnowledgePublicationEvent.EventType.ENTITY_UPDATED)
        event = create_entity_publication_event(
            object_type=object_type, object_id=target.pk, event_type=event_type,
            changed_fields=changed_fields, actor=actor, idempotency_key=key,
            provenance={"source": "admin_publication", "withdrawal": change_kind == "withdraw"},
        )
        return event.domain_event
    return record_canonical_change(
        object_type=object_type,
        object_id=target.pk,
        change_kind=change_kind,
        changed_fields=changed_fields,
        actor=actor,
        idempotency_key=key,
    )
