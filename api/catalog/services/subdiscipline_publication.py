"""Public projections of the existing, independent Subdiscipline identity."""
from types import SimpleNamespace

from django.db.models import Q
from rest_framework.exceptions import NotFound, ValidationError

from catalog.models import (
    KnowledgeNode, KnowledgeNodeDiscipline, LegacyKnowledgeMapping, ReadingPath,
    ReadingPathItem, TheoryDisciplineRelation, WorkSubdisciplineRelation,
)
from catalog.services.canonical_identity import legacy_mapping_safety
from catalog.services.knowledge_media import image_media
from catalog.services.legacy_theory_evidence import legacy_evidence_fields
from catalog.services.publication_eligibility import active_catalog_snapshot, public_editions
from catalog.services.scoped_search import public_scholar_queryset


def works_page_number(value=1):
    raw = str(value)
    try:
        page = int(raw) if raw.isascii() and raw.isdigit() else 0
    except ValueError:
        page = 0
    if page < 1:
        raise ValidationError({"works_page": "文献页码须为正整数。"})
    return page


def entity_link(row):
    return {"id": str(row.pk), "name": row.name, "slug": row.slug,
            "href": f"/subdisciplines/{row.slug}"}


def cover_url(row):
    if getattr(row, "cover_rendition_id", None) or getattr(row, "hero_rendition_id", None):
        media = image_media(row)
        return next(item["url"] for item in media["renditions"]
                    if item["id"] == media["primary_rendition_id"])
    field = getattr(row, "cover_asset", None) or getattr(row, "hero_image", None)
    return field.url if field else ""


def safe_legacy_mappings(identifiers):
    result = {}
    for mapping in LegacyKnowledgeMapping.objects.filter(
        legacy_model="TheorySchool", legacy_id__in=identifiers, migration_status="mapped",
    ).select_related("node"):
        if legacy_mapping_safety(mapping)[0]:
            result[mapping.legacy_id] = mapping.node
    return result


def discipline_theory_count(discipline):
    linked = KnowledgeNodeDiscipline.objects.filter(
        discipline=discipline, status="published", node__status="published",
        node__node_type="theory_tradition",
    ).values("node_id")
    nodes = set(KnowledgeNode.objects.filter(
        Q(primary_discipline=discipline) | Q(pk__in=linked),
        status="published", node_type="theory_tradition",
    ).values_list("pk", flat=True))
    legacy = list(TheoryDisciplineRelation.objects.filter(
        discipline=discipline, review_status="approved", theory_school__editorial_status="published",
    ).values_list("theory_school_id", flat=True))
    mapped = safe_legacy_mappings(legacy)
    nodes.update(row.pk for row in mapped.values())
    return len(nodes) + len(set(legacy) - mapped.keys())


def node_target(node):
    return {"id": str(node.pk), "slug": node.slug, "href": f"/theories/nodes/{node.slug}"}


def node_card(relation):
    node = relation.node
    return {
        "id": str(node.pk), "name": node.canonical_name_zh, "slug": node.slug,
        "role": relation.relation_role, "kind": "knowledge_node", "node_type": node.node_type,
        "href": f"/theories/nodes/{node.slug}", "summary": node.summary or node.definition,
        "cover_url": cover_url(node), "cover_media": image_media(node), "source": relation.source,
        "canonical_target": node_target(node), "legacy_identities": [],
    }


def relation_evidence(relation, context):
    if not relation.evidence_asset_id or relation.evidence_asset.edition.work_id != relation.work_id:
        return None
    fields = legacy_evidence_fields(relation, context)
    if not fields["evidence_text"] or fields["evidence_page"] is None:
        return None
    asset = relation.evidence_asset
    revision = asset.edition.active_catalog_revision
    snapshot = active_catalog_snapshot(asset.edition)
    return {
        "id": str(relation.pk), "source_kind": "work_relation",
        "work_id": str(asset.edition.work_id), "edition_id": str(asset.edition_id),
        "asset_id": str(asset.pk), "document_revision_id": str(revision.document_revision_id),
        "title": str((snapshot.get("work") or {}).get("title") or ""),
        "edition_label": str((snapshot.get("edition") or {}).get("version_label") or ""),
        "quote": fields["evidence_text"], "pdf_page": fields["evidence_page"],
        "printed_page_label": fields["evidence_printed_label"],
        "reader_href": f"/reader/{asset.pk}?page={fields['evidence_page']}&revision={revision.document_revision_id}",
    }


def public_subdiscipline_data(obj, context):
    works_page = works_page_number(context.get("works_page", 1))
    cache = context.setdefault("_public_subdisciplines", {})
    cache_key = (obj.pk, works_page)
    if cache_key in cache:
        return cache[cache_key]
    # Imports are local because the shared serializers also consume this service.
    from catalog.serializers import PersonCompactSerializer
    from catalog.theory_serializers import compact_work
    from catalog.services import content_placements, shared_curation
    source_context = context.setdefault("_subdiscipline_source_context", {"request": context.get("request")})

    links = list(obj.knowledge_node_links.filter(
        status="published", node__status="published",
        node__node_type__in=("theory_tradition", "concept", "debate", "research_problem"),
    ).select_related("node").order_by("sort_order", "node__canonical_name_zh", "pk"))
    theories = [node_card(row) for row in links if row.node.node_type != "research_problem"]
    canonical = {row["id"]: row for row in theories}
    legacy = list(obj.theory_relations.filter(
        review_status="approved", theory_school__editorial_status="published",
    ).select_related("theory_school").order_by("theory_school__name", "pk"))
    mappings = safe_legacy_mappings([row.theory_school_id for row in legacy])
    for relation in legacy:
        old = relation.theory_school
        identity = {"id": str(old.pk), "name": old.name, "slug": old.slug,
                    "role": relation.role, "source": relation.source}
        mapped = mappings.get(old.pk)
        if mapped and str(mapped.pk) in canonical:
            canonical[str(mapped.pk)]["legacy_identities"].append(identity)
            continue
        theories.append({
            **identity, "kind": "legacy_theory", "node_type": None,
            "href": f"/theory-schools/{old.slug}", "summary": old.description,
            "cover_url": cover_url(old),
            "canonical_target": node_target(mapped) if mapped else None,
            "legacy_identities": [identity],
        })

    problems = [row for row in links if row.node.node_type == "research_problem"]
    by_title = {row.node.canonical_name_zh.strip(): row for row in problems}
    questions, used = [], set()
    for text in obj.core_questions if isinstance(obj.core_questions, list) else []:
        if not isinstance(text, str) or not text.strip():
            continue
        match = by_title.get(text.strip())
        questions.append({
            "id": str(match.node_id) if match else None, "title": text.strip(),
            "description": (match.node.summary or match.node.definition) if match else "",
            "href": f"/theories/nodes/{match.node.slug}" if match else None,
            "source": match.source if match else "",
        })
        if match:
            used.add(match.node_id)
    questions.extend({
        "id": str(row.node_id), "title": row.node.canonical_name_zh,
        "description": row.node.summary or row.node.definition,
        "href": f"/theories/nodes/{row.node.slug}", "source": row.source,
    } for row in problems if row.node_id not in used)

    topics = [{
        "id": str(row.topic_id), "name": row.topic.name, "slug": row.topic.slug,
        "relation_label": row.relation_label, "description": row.topic.description,
        "hero_image": cover_url(row.topic), "cover_media": image_media(row.topic),
        "href": f"/topics/{row.topic.slug}", "source": "",
    } for row in obj.topic_relations.filter(
        review_status="approved", topic__editorial_status="published",
    ).select_related("topic").order_by("topic__name", "pk")]
    scholars = []
    for row in obj.person_relations.filter(
        review_status="approved",
        person_id__in=public_scholar_queryset().values("person_id"),
    ).select_related("person__scholar_profile").order_by("person__preferred_name", "pk"):
        profile = row.person.scholar_profile
        scholars.append({
            "id": str(profile.pk), "person_id": str(row.person_id),
            "name": row.person.preferred_name, "slug": profile.slug,
            "source_label": row.source, "reason": row.relation_label,
            "confidence": row.confidence, "approved": True,
            "portrait_url": PersonCompactSerializer(context=context).get_portrait(row.person),
            "portrait_media": PersonCompactSerializer(context=context).get_portrait_media(row.person),
            "summary": profile.short_description or row.person.biography,
            "href": f"/scholars/{profile.slug}", "relation_label": row.relation_label,
            # This model has an editorial source note but no exact source FK.
            "source_href": None,
        })

    work_queryset = WorkSubdisciplineRelation.objects.filter(
        subdiscipline=obj, review_status="approved",
        work_id__in=public_editions().values("work_id"),
    ).select_related(
        "work", "evidence_asset__edition__active_catalog_revision__document_revision",
    ).order_by("-is_primary", "created_at", "pk")
    work_count = work_queryset.count()
    total_pages = max(1, (work_count + 47) // 48)
    if works_page > total_pages:
        raise NotFound({"works_page": "此文献页不存在，请返回第一页重新查看。"})
    offset = (works_page - 1) * 48
    work_relations = list(work_queryset[offset:offset + 48])
    core_works, sources = [], []
    for row in work_relations:
        card = compact_work(row.work, context.get("request"))
        if card is None:
            continue
        evidence = relation_evidence(row, source_context)
        core_works.append({**card, "relation_label": "主要关联文献" if row.is_primary else "相关文献",
                           "source": row.source, "evidence": evidence})
        if evidence:
            sources.append(evidence)

    if obj.editorial_status == "published":
        placements = content_placements.read("subdiscipline", obj.pk, public=True)
        for item in placements["items"]:
            source = item["source"]
            if source.get("type") != "span" or not isinstance(source.get("text"), str) or not source["text"]:
                continue
            # Resolve once more through the same strict asset/page gate used by
            # relation excerpts; saved placements never relax current access.
            span = shared_curation.sources("span", public=True).filter(pk=source["id"]).first()
            if span is None or str(span.document_revision_id) != source["document_revision_id"]:
                continue
            checked = legacy_evidence_fields(SimpleNamespace(
                evidence_asset_id=span.page.asset_id, evidence_page=source["page_start"],
                evidence_text=source["text"], evidence_printed_label=source["printed_label"],
            ), source_context)
            if not checked["evidence_text"]:
                continue
            sources.append({
                "id": str(item["id"]), "source_kind": "placement_span",
                "work_id": source["work_id"], "edition_id": source["edition_id"],
                "asset_id": source["asset_id"], "document_revision_id": source["document_revision_id"],
                "title": source["work_title"], "quote": source["text"],
                "edition_label": source.get("edition_label") or "",
                "pdf_page": source["page_start"], "printed_page_label": source["printed_label"],
                "reader_href": f"/reader/{source['asset_id']}?page={source['page_start']}&revision={source['document_revision_id']}",
            })

    valid_items = ReadingPathItem.objects.filter(
        node_id__in=[row.node_id for row in links], node__status="published",
    ).filter(Q(work__isnull=True) | Q(work_id__in=public_editions().values("work_id")))
    paths = ReadingPath.objects.filter(
        status="published", items__in=valid_items,
    ).distinct().order_by("sort_order", "title", "pk")
    output = {
        "theories": theories, "topics": topics, "scholars": scholars,
        "key_questions": questions, "core_works": core_works, "sources": sources,
        "work_objects": [row.work for row in work_relations],
        "works_pagination": {"count": work_count, "page": works_page, "total_pages": total_pages},
        "reading_paths": [{
            "id": str(path.pk), "title": path.title, "slug": path.slug,
            "href": f"/theories/reading-paths/{path.slug}", "introduction": path.introduction,
            "relation_label": "包含本子学科已确认的知识节点",
        } for path in paths],
    }
    cache[cache_key] = output
    return output
