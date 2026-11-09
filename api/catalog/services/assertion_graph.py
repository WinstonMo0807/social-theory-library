"""Source-specific academic graph projection over canonical Assertions."""
from django.db.models import Q
from catalog import models as m
from catalog.services.knowledge_public import assertion_public, assertion_data

from catalog.services.academic_vocabulary import PREDICATES, legacy_citation


def entity_endpoint(entity, entities):
    if entity is None:
        return None
    for field, kind in (("node_id","knowledge_node"), ("person_id","scholar"), ("topic_id","topic"), ("subdiscipline_id","subdiscipline")):
        key = getattr(entity, field)
        if key:
            row = entities[kind].filter(**{"person_id" if kind == "scholar" else "pk":key}).first()
            return (kind, row) if row else None
    return None


def project_statement(statement, entities, actor=None):
    if not assertion_public(statement):
        return None
    participants = list(statement.participants.select_related("entity"))
    subjects = [v for v in participants if v.role == "subject"]
    objects = [v for v in participants if v.role == "object"]
    # A complex argument remains a full statement; do not invent binary edges.
    if len(subjects) != 1 or len(objects) != 1:
        return None
    left, right = entity_endpoint(subjects[0].entity, entities), entity_endpoint(objects[0].entity, entities)
    if not left or not right:
        return None
    value = assertion_data(statement, actor)
    legacy_record = statement.origin.get("record", {})
    citation = "；".join(v["citation"] for v in value["sources"] if v["citation"]) or legacy_citation(legacy_record.get("source") or legacy_record.get("evidence_source"))
    evidence = []
    for link in value["evidence"]:
        location = link.get("locator")
        if location:
            evidence.append({"id":link["anchor_id"], "stance":link["stance"], "quote":location["exact"],
                "reader_href":location["reader_url"], "locator":location,
                "work_id":location["work_id"], "edition_id":location["edition_id"],
                "asset_id":location["asset_id"], "document_revision_id":location["document_revision_id"],
                "title": next((v["work__title"] for v in value["sources"] if str(v["work_id"]) == location["work_id"]), ""),
                "edition_label": "", "pdf_page":location["segments"][0]["page_number"],
                "printed_page_label":location["segments"][0].get("printed_label", "")})
    return ({"id":f"Assertion:{statement.pk}", "entity_id":str(statement.pk), "model":"Assertion",
        "source":f"{left[0]}:{left[1].pk}", "target":f"{right[0]}:{right[1].pk}",
        "relation_type":statement.predicate, "relation_label":PREDICATES.get(statement.predicate, statement.predicate),
        "direction":statement.direction, "description":statement.text, "status":"published",
        "evidence_source":citation,
        "source_status":"available" if evidence else "login_required" if value["evidence"] else "citation_only" if citation else "missing",
        "evidence":evidence[:6], "evidence_truncated":len(evidence)>6,
        "sources":value["sources"], "conditions":statement.conditions, "source_quality":statement.source_quality,
        "assertion_url":f"/api/knowledge/assertions/{statement.pk}/"}, left, right)


def near_statements(frontier, entities, options):
    near = Q(pk__in=[])
    for kind, key in frontier:
        if kind == "scholar":
            near |= Q(person_id__in=entities[kind].filter(pk=key).values("person_id"))
        else:
            field = {"knowledge_node":"node_id", "topic":"topic_id", "subdiscipline":"subdiscipline_id"}[kind]
            near |= Q(**{field:key})
    ids = m.Entity.objects.filter(near).values("pk")
    rows = m.Assertion.objects.filter(status="published", participants__entity_id__in=ids,
        participants__role__in=["subject","object"]).distinct().order_by("pk")
    if options.get("relation_type"):
        rows = rows.filter(predicate__in=options["relation_type"])
    if options.get("source_work"):
        rows = rows.filter(sources__work_id=options["source_work"])
    if options.get("source_revision"):
        rows = rows.filter(sources__document_revision_id=options["source_revision"])
    if options.get("assertion_direction"):
        rows = rows.filter(direction=options["assertion_direction"])
    if options.get("context"):
        # Bounded literal context filtering, never relation expansion by similarity.
        rows = rows.filter(Q(text__icontains=options["context"]) | Q(conditions__icontains=options["context"]))
    return rows.distinct()
