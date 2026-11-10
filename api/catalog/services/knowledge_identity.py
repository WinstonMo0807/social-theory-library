"""Reviewed identity redirects preserve statement endpoints and historical pages."""
from django.db import transaction
from django.db.models import Q, TextField
from django.db.models.functions import Cast
from catalog import models as m


def canonical_entity(entity):
    seen = set()
    while entity and entity.merged_into_id:
        if entity.pk in seen or len(seen) >= 32:
            raise ValueError("身份重定向存在循环或超过安全范围，请核对归并历史。")
        seen.add(entity.pk)
        entity = entity.merged_into
    return entity


def family_ids(identifiers):
    """Original IDs belonging to reviewed survivors; names never imply identity."""
    found = set(identifiers)
    frontier = found
    while frontier:
        frontier = set(m.Entity.objects.filter(merged_into_id__in=frontier).values_list("pk", flat=True)) - found
        found.update(frontier)
        if len(found) > 5000:
            raise ValueError("身份归并范围超过单次查询上限，请按具体身份缩小范围。")
    return found


def identity_scope(entities):
    ids = family_ids(entities.values_list("pk", flat=True))
    participants = m.AssertionParticipant.objects.filter(entity_id__in=ids)
    sources = m.AssertionSource.objects.filter(attribution_id__in=ids)
    statements = m.Assertion.objects.filter(Q(pk__in=participants.values("assertion_id")) | Q(pk__in=sources.values("assertion_id")))
    dependent_pages = m.KnowledgeBlockDependency.objects.filter(
        Q(source_type="entity", source_id__in=ids)
        | Q(source_type="assertion", source_id__in=statements.values("pk"))).values("page_id")
    pages = m.KnowledgePage.objects.filter(Q(entity_id__in=ids) | Q(pk__in=dependent_pages))
    changes = m.ChangeItem.objects.annotate(identity_text=Cast("payload", TextField()))
    condition = Q(changeset__subject_entity_id__in=ids)
    for key in ids:
        condition |= Q(identity_text__icontains=str(key))
    changes = changes.filter(condition)
    return {
        "Entity": m.Entity.objects.filter(pk__in=ids),
        "EntityAlias": m.EntityAlias.objects.filter(entity_id__in=ids),
        "EntityIdentifier": m.EntityIdentifier.objects.filter(entity_id__in=ids),
        "Assertion": statements, "AssertionParticipant": m.AssertionParticipant.objects.filter(assertion__in=statements),
        "AssertionSource": m.AssertionSource.objects.filter(assertion__in=statements),
        "AssertionEvidence": m.AssertionEvidence.objects.filter(assertion__in=statements),
        "KnowledgePage": pages,
        "KnowledgeEditorialRevision": m.EditorialRevision.objects.filter(target_type="knowledge_page", target_id__in=pages.values("pk")),
        "ChangeItem": changes,
    }


def pending_identity_edits(entities):
    scope = identity_scope(entities)
    return (scope["KnowledgeEditorialRevision"].filter(status="draft").exists()
        or scope["ChangeItem"].filter(decision__in=["pending", "deferred", "accepted"], application={}).exists())


@transaction.atomic
def merge_identity(source, target):
    """Called only inside existing permissioned, previewed merge transactions."""
    from catalog.services.knowledge_core import entity_for_legacy
    from catalog.services.knowledge_migration import migrate_relation
    left, right = entity_for_legacy(source), entity_for_legacy(target)
    list(m.Entity.objects.select_for_update().filter(pk__in=[left.pk, right.pk]).order_by("pk"))
    if left.kind != right.kind or left.pk == right.pk or canonical_entity(right).pk == left.pk:
        raise ValueError("身份类型不同或归并会产生循环。")
    if left.merged_into_id or right.merged_into_id:
        raise ValueError("身份已经归并，请重新读取当前保留身份。")
    if isinstance(source, m.KnowledgeNode):
        queries = [m.PersonNodeRelation.objects.filter(node=source), m.WorkNodeRelation.objects.filter(node=source),
            m.KnowledgeRelation.objects.filter(Q(source_node=source) | Q(target_node=source))]
    elif isinstance(source, m.Person):
        queries = [m.PersonNodeRelation.objects.filter(person=source)]
    else:
        queries = []
    for rows in queries:
        for row in rows.filter(status__in=["published", "confirmed", "approved"]).order_by("pk"):
            migrate_relation(row)
    before = {"id": str(left.pk), "merged_into_id": None, "status": left.status}
    left.merged_into = right
    left.status = "merged"
    left.save(update_fields=["merged_into", "status", "updated_at"])
    # Recompile affected page suggestions only; no OCR or inference is launched.
    m.KnowledgeBlockDependency.objects.filter(source_type="entity", source_id__in=[left.pk, right.pk]).update(stale=True)
    return before


def restore_identity(before):
    if before:
        m.Entity.objects.filter(pk=before["id"]).update(merged_into_id=before["merged_into_id"], status=before["status"])
        m.KnowledgeBlockDependency.objects.filter(source_type="entity", source_id=before["id"]).update(stale=True)
