"""Knowledge page queries and dependency projection shared by UI and MCP.

Page bodies remain in EditorialRevision and its published materialization.
Human edits enter the same ChangeSet review service as generated suggestions.
"""
from uuid import UUID, uuid5
from django.db import transaction
from django.db.models import Q, Max
from rest_framework.exceptions import ValidationError
from catalog import models as m
from catalog.services.knowledge_core import require_editor, page_content
from catalog.services.knowledge_sources import digest

ENTITY_PROFILES = {
    "person": ("person", m.Person, ["preferred_name", "original_name", "biography", "birth_year", "death_year", "country_region", "authority_status"]),
    "knowledge_node": ("node", m.KnowledgeNode, ["canonical_name_zh", "canonical_name_en", "definition", "summary", "core_questions", "basic_propositions", "theoretical_boundary", "status"]),
    "topic": ("topic", m.Topic, ["name", "description", "editorial_status", "problem_statement", "core_questions", "research_dimensions", "methods", "formation_context", "key_concepts"]),
    "discipline": ("discipline", m.Discipline, ["name", "description", "editorial_status", "introduction"]),
    "subdiscipline": ("subdiscipline", m.Subdiscipline, ["name", "description", "editorial_status", "research_object", "core_questions", "research_directions", "methods", "representative_issues"]),
    "theory_school": ("theory_school", m.TheorySchool, ["name", "description", "editorial_status", "entity_level", "formation_period", "core_questions", "key_themes"]),
}


def source_value(kind, key):
    """Only meaning-bearing data enters freshness, never portraits or layout."""
    if kind == "entity":
        entity = m.Entity.objects.filter(pk=key).select_related("person", "node", "topic", "discipline", "subdiscipline", "theory_school").first()
        row = {"label": entity.label, "definition": entity.definition, "context": entity.context,
            "status": entity.status, "merged_into": entity.merged_into_id} if entity else None
        if entity:
            for relation, _, fields in ENTITY_PROFILES.values():
                if getattr(entity, f"{relation}_id"):
                    typed = getattr(entity, relation)
                    row[relation] = {k: getattr(typed, k) for k in fields}
            row["aliases"] = list(entity.aliases.filter(review_status="confirmed").order_by("id").values("text", "language", "script"))
    elif kind in ENTITY_PROFILES:
        _, model, fields = ENTITY_PROFILES[kind]
        row = model.objects.filter(pk=key).values(*fields).first()
    elif kind == "assertion":
        row = m.Assertion.objects.filter(pk=key).values("text", "predicate", "expression", "conditions", "status").first()
        if row is not None:
            row["participants"] = list(m.AssertionParticipant.objects.filter(assertion_id=key).order_by("id")
                .values("role", "entity_id", "work_id", "edition_id"))
            row["sources"] = list(m.AssertionSource.objects.filter(assertion_id=key).order_by("id")
                .values("work_id", "edition_id", "document_revision_id", "node_id", "attribution_id", "expression"))
            row["evidence"] = list(m.AssertionEvidence.objects.filter(assertion_id=key).order_by("id")
                .values("anchor_id", "stance", "note"))
    elif kind == "knowledge_page":
        page = m.KnowledgePage.objects.filter(pk=key).first()
        row = {"title": page.title, "blocks": page_content(page)[0], "status": page.status} if page else None
    elif kind == "work":
        row = m.Work.objects.filter(pk=key).values("title", "abstract").first()
        if row is not None:
            row["revisions"] = list(m.DocumentRevision.objects.filter(asset__edition__work_id=key, is_active=True)
                .order_by("id").values("id", "text_checksum"))
    elif kind == "document_revision":
        row = m.DocumentRevision.objects.filter(pk=key).values("text_checksum", "is_active").first()
    elif kind == "anchor":
        row = m.EvidenceAnchor.objects.filter(pk=key).values("content_hash", "validation").first()
    else:
        return {"type": kind, "id": str(key)}
    return row


def source_hash(kind, key):
    # UUIDs inside ORM values need a stable, non-secret JSON representation.
    import json
    return digest(json.loads(json.dumps(source_value(kind, key), default=str, ensure_ascii=False)))


def reference_sources(ref):
    kind, key = ref.get("type"), ref.get("id")
    if kind == "node":
        kind = "knowledge_node"
    if kind in ENTITY_PROFILES:
        return [(kind, UUID(str(key)))]
    if kind == "span":
        mapped = m.KnowledgeLegacyMapping.objects.filter(source_type="evidence_span", source_id=key, target_type="anchor").first()
        return reference_sources({"type": "anchor", "id": mapped.target_id}) if mapped and mapped.target_id else []
    if kind not in {"entity", "assertion", "knowledge_page", "work", "anchor"}:
        return []
    key = UUID(str(key))
    result = [(kind, key)]
    if kind == "assertion":
        statement = m.Assertion.objects.filter(pk=key).first()
        if statement is None:
            return result
        result += [("entity", value) for value in statement.participants.exclude(entity=None).values_list("entity_id", flat=True)]
        for source in statement.sources.all():
            result.append(("work", source.work_id))
            if source.document_revision_id:
                result.append(("document_revision", source.document_revision_id))
        for anchor in m.EvidenceAnchor.objects.filter(assertion_links__assertion=statement):
            result += [("anchor", anchor.pk), ("document_revision", anchor.document_revision_id)]
    elif kind == "anchor":
        anchor = m.EvidenceAnchor.objects.filter(pk=key).first()
        if anchor:
            result.append(("document_revision", anchor.document_revision_id))
    return result


@transaction.atomic
def sync_dependencies(page, blocks=None, *, changed_blocks=None):
    """Rebuild this page only; removed references are disposable projection rows."""
    blocks = page_content(page)[0] if blocks is None else blocks
    from catalog.services.editorial_blocks import block_references
    rows, seen, hashes = [], set(), {}
    retained = {(str(r.block_id), r.source_type, r.source_id): r for r in page.dependencies.all()}
    for block in blocks:
        refs = block_references(block)
        if page.work_id:
            refs = [*refs, {"type": "work", "id": str(page.work_id)}]
        if page.entity_id:
            refs = [*refs, {"type": "entity", "id": str(page.entity_id)}]
        for ref in refs:
            for kind, key in reference_sources(ref):
                identity = (str(block["id"]), kind, key)
                if identity in seen:
                    continue
                seen.add(identity)
                old = retained.get(identity) if changed_blocks is not None and str(block["id"]) not in changed_blocks else None
                if not old and (kind, key) not in hashes:
                    hashes[kind, key] = source_hash(kind, key)
                rows.append(m.KnowledgeBlockDependency(page=page, block_id=block["id"], source_type=kind,
                    source_id=key, source_hash=old.source_hash if old else hashes[kind, key], stale=old.stale if old else False))
    page.dependencies.all().delete()
    m.KnowledgeBlockDependency.objects.bulk_create(rows)


def invalidate_source(kind, key):
    """Called by the existing canonical change coordinator, without model work."""
    targets = [(kind, key)]
    legacy = {"person": "person_id", "knowledge_node": "node_id", "topic": "topic_id",
              "discipline": "discipline_id", "subdiscipline": "subdiscipline_id", "theory_school": "theory_school_id"}
    if kind in legacy:
        targets += [("entity", value) for value in m.Entity.objects.filter(**{legacy[kind]: key}).values_list("pk", flat=True)]
    if kind in {"edition", "asset", "document_revision"}:
        # Use explicit joins below; asset revision related names differ in old schemas.
        if kind == "edition":
            work = m.Edition.objects.filter(pk=key).values_list("work_id", flat=True).first()
        elif kind == "asset":
            work = m.Asset.objects.filter(pk=key).values_list("edition__work_id", flat=True).first()
        else:
            work = m.DocumentRevision.objects.filter(pk=key).values_list("asset__edition__work_id", flat=True).first()
        if work:
            targets.append(("work", work))
    for source_type, source_id in targets:
        if not m.KnowledgeBlockDependency.objects.filter(source_type=source_type, source_id=source_id).exists():
            continue
        current = source_hash(source_type, source_id)
        m.KnowledgeBlockDependency.objects.filter(source_type=source_type, source_id=source_id).exclude(source_hash=current).update(stale=True)


def page_directory(actor, *, query="", kind="", state="", offset=0, limit=30):
    require_editor(actor)
    rows = m.KnowledgePage.objects.select_related("entity", "work").order_by("title", "id")
    if query:
        rows = rows.filter(Q(title__icontains=query) | Q(scope__icontains=query))
    if kind == "work":
        rows = rows.filter(work__isnull=False)
    elif kind == "special":
        rows = rows.filter(work__isnull=True, entity__isnull=True)
    elif kind:
        rows = rows.filter(entity__kind=kind)
    if state == "stale":
        rows = rows.filter(dependencies__stale=True).distinct()
    elif state:
        rows = rows.filter(status=state)
    count = rows.count()
    pages = list(rows[offset:offset + limit])
    drafts = set(str(v) for v in m.EditorialRevision.objects.filter(target_type="knowledge_page",
        target_id__in=[p.pk for p in pages], status="draft").values_list("target_id", flat=True))
    edited = {r["target_id"]: r["latest"] for r in m.EditorialRevision.objects.filter(target_type="knowledge_page",
        target_id__in=[p.pk for p in pages]).values("target_id").annotate(latest=Max("created_at"))}
    return {"count": count, "offset": offset, "limit": limit, "pages": [{
        "id": str(p.pk), "title": p.title, "scope": p.scope, "kind": p.entity.kind if p.entity_id else "work" if p.work_id else "special",
        "status": p.status, "has_draft": str(p.pk) in drafts, "work_id": str(p.work_id) if p.work_id else None,
        "entity_id": str(p.entity_id) if p.entity_id else None, "changed_blocks": p.dependencies.filter(stale=True).values("block_id").distinct().count(),
        "updated_at": max(p.updated_at, edited.get(p.pk, p.updated_at))} for p in pages]}


def page_workspace(page, actor):
    require_editor(actor)
    from catalog.services.knowledge_public import page_data
    data = page_data(page, actor, draft=True)
    blocks, revision = page_content(page)
    dependencies = list(page.dependencies.values("block_id", "source_type", "source_id", "source_hash", "stale"))
    # This also catches an older producer that has not emitted a canonical event yet.
    for row in dependencies:
        row["stale"] = row["stale"] or row["source_hash"] != source_hash(row["source_type"], row["source_id"])
    links = m.KnowledgeBlockDependency.objects.filter(source_type="knowledge_page", source_id=page.pk).select_related("page")
    revisions = m.EditorialRevision.objects.filter(target_type="knowledge_page", target_id=page.pk).order_by("-revision")[:20]
    data.update({"kind": page.entity.kind if page.entity_id else "work" if page.work_id else "special",
        "work_id": str(page.work_id) if page.work_id else None, "entity_id": str(page.entity_id) if page.entity_id else None,
        "dependencies": dependencies, "backlinks": [{"page_id": str(r.page_id), "title": r.page.title, "block_id": str(r.block_id)} for r in links],
        "block_hashes": {b["id"]: digest(b) for b in blocks},
        "revisions": [{"id": str(r.pk), "revision": r.revision, "status": r.status, "created_at": r.created_at} for r in revisions],
        "pending_changesets": list(m.ChangeSet.objects.filter(items__payload__page_id=str(page.pk),
            items__decision__in=["pending", "accepted", "deferred"], items__application={}).distinct().values("id", "origin", "status", "created_at"))})
    return data


def submit_page_changes(page, revision, patches, actor, *, request_id):
    require_editor(actor)
    from catalog.services.intelligence_changes import submit_draft, uuid_value
    request_id = uuid_value(request_id)
    if not isinstance(patches, list) or not 1 <= len(patches) <= 200:
        raise ValidationError("请提交1至200个区块修改。")
    proposals = []
    for i, patch in enumerate(patches):
        if not isinstance(patch, dict) or patch.get("operation") not in {"add", "replace", "delete"}:
            raise ValidationError("区块修改操作无效。")
        block_id = str(uuid_value(patch.get("block_id")))
        payload = {k: patch[k] for k in ("operation", "base_hash", "block", "reason") if k in patch}
        payload.update(page_id=str(page.pk), block_id=block_id, human_edited=True)
        proposals.append({"id": str(uuid5(request_id, str(i))), "kind": "wiki_patch", "payload": payload, "dependencies": []})
    return submit_draft(revision, proposals, actor, request_id=request_id, origin="human")
