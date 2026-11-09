"""Read-only legacy payloads over source-specific published Assertions.

The unmapped fallback exists for staged migration only. Mapped withdrawn or
superseded records never fall back to their old published rows.
"""
from types import SimpleNamespace
from django.db.models import Q
from catalog import models as m
from catalog.services.knowledge_public import assertion_public


def _mapped(model):
    return m.KnowledgeLegacyMapping.objects.filter(source_type=model._meta.label_lower,
        target_type="assertion", target_id__isnull=False).values("source_id")


def _statements(kind, *, person_ids=None, node_ids=None, work_ids=None):
    rows = m.Assertion.objects.filter(status="published", participants__entity__node__isnull=False)
    if kind == "person":
        rows = rows.filter(participants__entity__person__isnull=False)
    if person_ids is not None:
        rows = rows.filter(participants__entity__person_id__in=person_ids)
    if node_ids is not None:
        rows = rows.filter(participants__entity__node_id__in=node_ids)
    if kind == "work":
        rows = rows.filter(participants__work__isnull=False)
    if work_ids is not None:
        rows = rows.filter(participants__work_id__in=work_ids)
    return rows.distinct().order_by("id").prefetch_related("participants__entity__node", "participants__entity__person", "participants__work", "sources", "evidence")


def person_node_links(*, person_ids=None, node_ids=None, tradition_only=False):
    for statement in _statements("person", person_ids=person_ids, node_ids=node_ids):
        if not assertion_public(statement):
            continue
        members = list(statement.participants.all())
        persons = [v for v in members if v.role in {"subject", "object"} and v.entity_id and v.entity.person_id]
        nodes = [v for v in members if v.role in {"subject", "object"} and v.entity_id and v.entity.node_id]
        if len(persons) != 1 or len(nodes) != 1:
            continue
        person, node = persons[0].entity.person, nodes[0].entity.node
        if tradition_only and node.node_type != "theory_tradition":
            continue
        record = statement.origin.get("record", {})
        yield SimpleNamespace(pk=statement.pk, id=statement.pk, person_id=person.pk, person=person,
            node_id=node.pk, node=node, relation_label=statement.text, relation_type=statement.predicate,
            direction=statement.direction, node_is_source=nodes[0].role == "subject", status="published",
            is_representative=bool(record.get("is_representative", False)), confidence=record.get("confidence"),
            source="；".join(v.citation for v in statement.sources.all() if v.citation),
            sort_order=record.get("sort_order", 0), assertion_id=statement.pk)
    rows = m.PersonNodeRelation.objects.filter(status="published", node__status="published").exclude(pk__in=_mapped(m.PersonNodeRelation))
    if person_ids is not None:
        rows = rows.filter(person_id__in=person_ids)
    if node_ids is not None:
        rows = rows.filter(node_id__in=node_ids)
    if tradition_only:
        rows = rows.filter(node__node_type="theory_tradition")
    yield from rows.select_related("person", "node").order_by("id")


def work_node_links(*, work_ids=None, node_ids=None):
    for statement in _statements("work", work_ids=work_ids, node_ids=node_ids):
        if not assertion_public(statement):
            continue
        members = list(statement.participants.all())
        works = [v for v in members if v.role in {"subject", "object"} and v.work_id]
        nodes = [v for v in members if v.role in {"subject", "object"} and v.entity_id and v.entity.node_id]
        if len(works) != 1 or len(nodes) != 1:
            continue
        work, node = works[0].work, nodes[0].entity.node
        record = statement.origin.get("record", {})
        yield SimpleNamespace(pk=statement.pk, id=statement.pk, work=work, work_id=work.pk, node=node, node_id=node.pk,
            role=statement.predicate, is_primary=bool(record.get("is_primary", False)), strength=record.get("strength", "medium"),
            status="published", assertion_id=statement.pk, description=statement.text)
    rows = m.WorkNodeRelation.objects.filter(status="published", node__status="published").exclude(pk__in=_mapped(m.WorkNodeRelation))
    if work_ids is not None:
        rows = rows.filter(work_id__in=work_ids)
    if node_ids is not None:
        rows = rows.filter(node_id__in=node_ids)
    yield from rows.select_related("work", "node").order_by("id")
