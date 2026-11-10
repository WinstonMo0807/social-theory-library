"""Read-only legacy payloads over source-specific published Assertions.

The unmapped fallback exists for staged migration only. Mapped withdrawn or
superseded records never fall back to their old published rows.
"""
from types import SimpleNamespace
from django.db.models import Q
from catalog import models as m
from catalog.services.knowledge_public import assertion_public
from catalog.services.academic_vocabulary import PREDICATES
from catalog.services.knowledge_identity import canonical_entity, family_ids


def _mapped(model):
    return m.KnowledgeLegacyMapping.objects.filter(source_type=model._meta.label_lower,
        target_type="assertion", target_id__isnull=False).values("source_id")


def scholar_links(*, scholar_id=None):
    rows = m.Assertion.objects.filter(status="published", participants__entity__person__isnull=False)
    if scholar_id:
        roots = m.Entity.objects.filter(person__scholar_profile__pk=scholar_id).values_list("pk", flat=True)
        rows = rows.filter(participants__entity_id__in=family_ids(roots))
    rows = rows.distinct().order_by("-updated_at", "pk").prefetch_related("participants__entity__person__scholar_profile", "sources")
    for statement in rows:
        members = list(statement.participants.all())
        left = [v for v in members if v.role == "subject"]
        right = [v for v in members if v.role == "object"]
        if len(left) != 1 or len(right) != 1 or not all(v.entity_id and v.entity.person_id for v in left + right):
            continue
        if not assertion_public(statement):
            continue
        source, target = [canonical_entity(v.entity).person.scholar_profile for v in left + right]
        if source.pk == target.pk:
            continue
        yield SimpleNamespace(pk=statement.pk, id=statement.pk, statement=statement,
            source_scholar=source, target_scholar=target, source_scholar_id=source.pk, target_scholar_id=target.pk,
            relation_type=statement.predicate, direction=statement.direction, updated_at=statement.updated_at)
    from catalog.services.public_scholars import legacy_public_scholar_relations
    old = legacy_public_scholar_relations().exclude(pk__in=_mapped(m.ScholarRelation))
    if scholar_id:
        old = old.filter(Q(source_scholar_id=scholar_id) | Q(target_scholar_id=scholar_id))
    yield from old.select_related("source_scholar__person", "target_scholar__person")


def scholar_payload(row, actor=None):
    if not hasattr(row, "statement"):
        from catalog.services.shared_curation import relation_payload as legacy_payload
        return legacy_payload(row, public=True)
    from catalog.services.knowledge_public import assertion_data
    from catalog.services.public_scholars import _base, _formal_profile
    people = {p.pk: _formal_profile(p, p.public_snapshot or {}) for p in _base().filter(pk__in=[row.source_scholar_id, row.target_scholar_id])}
    if len(people) != 2:
        return None
    source, target = people[row.source_scholar_id], people[row.target_scholar_id]
    value = assertion_data(row.statement, actor)
    return {"id": str(row.pk), "assertion_id": str(row.pk), "source_scholar": str(source.pk),
        "target_scholar": str(target.pk), "source_name": source.person.preferred_name,
        "target_name": target.person.preferred_name, "source_slug": source.slug, "target_slug": target.slug,
        "relation_type": row.relation_type, "relation_label": PREDICATES.get(row.relation_type, row.relation_type),
        "direction": row.direction, "summary": value["text"], "status": value["status"],
        "source": "；".join(v["citation"] or v["work__title"] or "" for v in value["sources"]),
        "assertion": value, "source_material": None, "edit_version": ""}


def _statements(kind, *, person_ids=None, node_ids=None, work_ids=None):
    rows = m.Assertion.objects.filter(status="published", participants__entity__node__isnull=False)
    if kind == "person":
        rows = rows.filter(participants__entity__person__isnull=False)
    if person_ids is not None:
        rows = rows.filter(participants__entity_id__in=family_ids(m.Entity.objects.filter(person_id__in=person_ids).values_list("pk", flat=True)))
    if node_ids is not None:
        rows = rows.filter(participants__entity_id__in=family_ids(m.Entity.objects.filter(node_id__in=node_ids).values_list("pk", flat=True)))
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
        person, node = canonical_entity(persons[0].entity).person, canonical_entity(nodes[0].entity).node
        if tradition_only and node.node_type != "theory_tradition":
            continue
        record = statement.origin.get("record", {})
        yield SimpleNamespace(pk=statement.pk, id=statement.pk, person_id=person.pk, person=person,
            node_id=node.pk, node=node, relation_label=statement.text, relation_type=statement.predicate,
            direction=statement.direction, node_is_source=nodes[0].role == "subject", status="published",
            is_representative=bool(record.get("is_representative", False)), confidence=record.get("confidence"),
            source="；".join(v.citation for v in statement.sources.all() if v.citation),
            sort_order=record.get("sort_order", 0), assertion_id=statement.pk, statement=statement)
    rows = m.PersonNodeRelation.objects.filter(status="published", node__status="published",
        person__authority_status="verified", person__scholar_profile__editorial_status="published").exclude(pk__in=_mapped(m.PersonNodeRelation))
    if person_ids is not None:
        rows = rows.filter(person_id__in=person_ids)
    if node_ids is not None:
        rows = rows.filter(node_id__in=node_ids)
    if tradition_only:
        rows = rows.filter(node__node_type="theory_tradition")
    yield from rows.select_related("person", "node").order_by("id")


def work_node_links(*, work_ids=None, node_ids=None, preparing_catalog=False):
    for statement in _statements("work", work_ids=work_ids, node_ids=node_ids):
        if not assertion_public(statement):
            continue
        members = list(statement.participants.all())
        works = [v for v in members if v.role in {"subject", "object"} and v.work_id]
        nodes = [v for v in members if v.role in {"subject", "object"} and v.entity_id and v.entity.node_id]
        if len(works) != 1 or len(nodes) != 1:
            continue
        work, node = works[0].work, canonical_entity(nodes[0].entity).node
        record = statement.origin.get("record", {})
        yield SimpleNamespace(pk=statement.pk, id=statement.pk, work=work, work_id=work.pk, node=node, node_id=node.pk,
            role=statement.predicate, is_primary=bool(record.get("is_primary", False)), strength=record.get("strength", "medium"),
            status="published", assertion_id=statement.pk, description=statement.text, statement=statement,
            updated_at=statement.updated_at, get_role_display=lambda p=statement.predicate: PREDICATES.get(p, p))
    from catalog.services.publication_eligibility import public_editions
    rows = m.WorkNodeRelation.objects.filter(status="published", node__status="published").exclude(pk__in=_mapped(m.WorkNodeRelation))
    if not preparing_catalog:
        rows = rows.filter(work_id__in=public_editions().values("work_id"))
    if work_ids is not None:
        rows = rows.filter(work_id__in=work_ids)
    if node_ids is not None:
        rows = rows.filter(node_id__in=node_ids)
    yield from rows.select_related("work", "node").order_by("id")


def node_node_links(*, node_ids=None):
    for statement in _statements("node", node_ids=node_ids):
        if not assertion_public(statement):
            continue
        members = list(statement.participants.all())
        subjects = [v for v in members if v.role == "subject"]
        objects = [v for v in members if v.role == "object"]
        if len(subjects) != 1 or len(objects) != 1:
            continue
        if not all(v.entity_id and v.entity.node_id for v in [subjects[0], objects[0]]):
            continue
        source, target = canonical_entity(subjects[0].entity).node, canonical_entity(objects[0].entity).node
        yield SimpleNamespace(id=statement.pk, pk=statement.pk, source_node=source, target_node=target,
            source_node_id=source.pk, target_node_id=target.pk, relation_type=statement.predicate,
            direction=statement.direction, description=statement.text, status="published",
            get_relation_type_display=lambda p=statement.predicate: PREDICATES.get(p, p), statement=statement,
            assertion_id=statement.pk)
    rows = m.KnowledgeRelation.objects.filter(status="published", source_node__status="published",
        target_node__status="published").exclude(pk__in=_mapped(m.KnowledgeRelation))
    if node_ids is not None:
        rows = rows.filter(Q(source_node_id__in=node_ids) | Q(target_node_id__in=node_ids))
    yield from rows.select_related("source_node", "target_node").order_by("id")


def relation_payload(link, actor):
    """Legacy public component fields with exact versioned, multi-segment locators."""
    from catalog.services.knowledge_public import assertion_data
    statement = link.statement
    value = assertion_data(statement, actor)
    evidence = []
    for item in value["evidence"]:
        location = item.get("locator")
        if not location:
            continue  # The existing login boundary applies to verbatim text.
        evidence.append({"id": item["anchor_id"], "anchor_id": item["anchor_id"], "stance": item["stance"],
            "work": location["work_id"], "file": location["asset_id"],
            "work_title": next((s["work__title"] for s in value["sources"] if str(s["work_id"]) == location["work_id"]), ""),
            "quote": location["exact"], "reader_href": location["reader_url"], "locator": location,
            "document_revision_id": location["document_revision_id"], "page_number": location["segments"][0]["page_number"],
            "page_end": location["segments"][-1]["page_number"],
            "printed_page_label": "、".join(s["printed_label"] for s in location["segments"] if s.get("printed_label")),
            "bounding_box": {}, "extraction_method": "verified_anchor", "review_status": "approved"})
    return {"id": str(statement.pk), "assertion_id": str(statement.pk), "status": statement.status,
        "description": statement.text, "source": "；".join(s["citation"] for s in value["sources"] if s["citation"]),
        "sources": value["sources"], "conditions": value["conditions"], "evidence": evidence,
        "source_quality": value["source_quality"], "confidence": None, "reviewed_at": None,
        "created_at": statement.created_at, "updated_at": statement.updated_at}


def published_knowledge_nodes(work_id, frozen_rows):
    """Overlay independently published knowledge, never unpublished bibliography.

    Unmigrated rows retain the activated catalog's boundary. Mapped rows use
    current Assertions so withdrawing knowledge cannot resurrect a frozen edge.
    """
    replaced = set(map(str, m.WorkNodeRelation.objects.filter(work_id=work_id,
        pk__in=_mapped(m.WorkNodeRelation)).values_list("node_id", flat=True)))
    rows = [v for v in frozen_rows if isinstance(v, dict) and str(v.get("id")) not in replaced and not v.get("assertion_id")]
    for link in work_node_links(work_ids=[work_id]):
        if not getattr(link, "assertion_id", None):
            continue
        rows.append({"id": str(link.node_id), "name": link.node.canonical_name_zh, "slug": link.node.slug,
            "type": link.node.node_type, "role": link.role, "is_primary": link.is_primary,
            "assertion_id": str(link.assertion_id)})
    return rows
