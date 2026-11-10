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
    "concept": ("concept", m.Concept, ["name", "description", "editorial_status"]),
    "organization_profile": ("organization", m.OrganizationAuthority, ["preferred_name", "original_name", "description", "organization_type", "country", "authority_status"]),
    "timeline_event": ("timeline_event", m.TheoryTimelineEvent, ["title", "description", "event_type", "start_year", "end_year", "start_date", "end_date", "date_precision", "date_label", "source", "review_status"]),
    "research_object_profile": ("research_object", m.ResearchObjectProfile, ["object_kind", "geographic_scope", "temporal_scope", "population", "unit_of_analysis"]),
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
            from .knowledge_entity_queries import profile_aliases
            row["aliases"] = sorted(({key: value[key] for key in ("text", "language", "script")}
                for value in profile_aliases(entity) if value["review_status"] == "confirmed"),
                key=lambda value: (value["text"], value["language"], value["script"]))
    elif kind in ENTITY_PROFILES:
        _, model, fields = ENTITY_PROFILES[kind]
        row = model.objects.filter(pk=key).values(*fields).first()
    elif kind == "assertion":
        row = m.Assertion.objects.filter(pk=key).values("text", "predicate", "expression", "conditions", "status").first()
        if row is not None:
            row["participants"] = list(m.AssertionParticipant.objects.filter(assertion_id=key).order_by("id")
                .values("role", "entity_id", "work_id", "edition_id"))
            row["sources"] = list(m.AssertionSource.objects.filter(assertion_id=key).order_by("id")
                .values("work_id", "edition_id", "document_revision_id", "node_id", "attribution_id", "expression", "citation"))
            row["evidence"] = list(m.AssertionEvidence.objects.filter(assertion_id=key).order_by("id")
                .values("anchor_id", "stance", "note"))
    elif kind == "knowledge_page":
        page = m.KnowledgePage.objects.filter(pk=key).first()
        from catalog.services.knowledge_core import page_metadata
        row = {**page_metadata(page, draft=True), "blocks": page_content(page)[0], "status": page.status} if page else None
    elif kind == "work":
        row = m.Work.objects.filter(pk=key).values("title", "abstract").first()
        if row is not None:
            row["revisions"] = list(m.DocumentRevision.objects.filter(asset__edition__work_id=key, is_active=True)
                .order_by("id").values("id", "text_checksum"))
    elif kind == "document_revision":
        # Citations pin immutable ranges. Restructuring the same text does not
        # change their evidence; Intelligence separately fingerprints its ranges.
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


def revision_evidence_hashes(key):
    """Read old fingerprints only when their text and active state still match."""
    value = source_value("document_revision", key)
    if value is None:
        return {digest(None)}
    structures = m.DocumentStructure.objects.filter(document_revision_id=key).values_list("input_hash", flat=True)
    return {digest(value), *[digest({**value, "structure_hash": h}) for h in [None, *structures]]}


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
            if source.work_id:
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
              "discipline": "discipline_id", "subdiscipline": "subdiscipline_id", "theory_school": "theory_school_id", "concept": "concept_id",
              "organization_profile": "organization_id", "timeline_event": "timeline_event_id", "research_object_profile": "research_object_id"}
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
        if source_type == "document_revision":
            # Normalize the old structure-sensitive projection, never accepting
            # a changed text checksum or a withdrawn/inactive revision.
            m.KnowledgeBlockDependency.objects.filter(source_type=source_type, source_id=source_id,
                source_hash__in=revision_evidence_hashes(source_id)).update(source_hash=current, stale=False)
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
        row["stale"] = (row["source_hash"] not in revision_evidence_hashes(row["source_id"]) if row["source_type"] == "document_revision"
            else row["stale"] or row["source_hash"] != source_hash(row["source_type"], row["source_id"]))
    links = m.KnowledgeBlockDependency.objects.filter(source_type="knowledge_page", source_id=page.pk).select_related("page")
    revisions = m.EditorialRevision.objects.filter(target_type="knowledge_page", target_id=page.pk).order_by("-revision")[:20]
    data.update({"kind": page.entity.kind if page.entity_id else "work" if page.work_id else "special",
        "work_id": str(page.work_id) if page.work_id else None, "entity_id": str(page.entity_id) if page.entity_id else None,
        "dependencies": dependencies, "backlinks": [{"page_id": str(r.page_id), "title": r.page.title, "block_id": str(r.block_id)} for r in links],
        "block_hashes": {b["id"]: digest(b) for b in blocks}, "metadata_hash": digest({k: data[k] for k in ("title", "scope")}),
        "revisions": [{"id": str(r.pk), "revision": r.revision, "status": r.status, "created_at": r.created_at} for r in revisions],
        "pending_changesets": list(m.ChangeSet.objects.filter(items__payload__page_id=str(page.pk),
            items__decision__in=["pending", "accepted", "deferred"], items__application={}).distinct().values("id", "origin", "status", "created_at"))})
    from catalog.services.editorial_blocks import block_references, resolve_target
    from catalog.services.knowledge_sources import locator
    from django.http import Http404
    references = {}
    for block in blocks:
        for ref in block_references(block):
            identity = f"{ref['type']}:{ref['id']}"
            if identity in references:
                continue
            try:
                _, card = resolve_target(ref)
                if ref["type"] == "anchor":
                    card["locator"] = locator(m.EvidenceAnchor.objects.get(pk=ref["id"]), actor, editorial=True)
                references[identity] = {**ref, **card}
            except (Http404, ValidationError, m.EvidenceAnchor.DoesNotExist):
                references[identity] = {**ref, "title": "来源当前不可用", "unavailable": True}
    data["references"] = list(references.values())
    data["assertion_hashes"] = {v["id"]: source_hash("assertion", v["id"]) for v in data.get("assertions", [])}
    data["public_url"] = public_page_url(page)
    return data


def public_page_url(page):
    if page.work_id:
        from catalog.services.publication_eligibility import public_editions
        edition = public_editions().filter(work_id=page.work_id).order_by("-is_primary").first()
        return f"/works/{edition.public_slug}" if edition and edition.public_slug else None
    from catalog.services.knowledge_identity import canonical_entity
    entity = canonical_entity(page.entity)
    if entity and entity.node_id:
        return f"/theories/nodes/{entity.node.slug}"
    if entity and entity.topic_id:
        return f"/topics/{entity.topic.slug}"
    if entity and entity.discipline_id:
        return f"/theories/disciplines/{entity.discipline.slug}"
    if entity and entity.person_id:
        profile = m.ScholarProfile.objects.filter(person_id=entity.person_id).first()
        return f"/scholars/{profile.slug}" if profile else None
    return f"/knowledge/{page.slug}"


@transaction.atomic
def open_page(actor, *, work_id=None, entity_id=None, title="", scope="", request_id=None):
    """A human opens a draft identity; body edits still go through ChangeSet."""
    require_editor(actor)
    from django.shortcuts import get_object_or_404
    if not work_id and not entity_id:
        from catalog.services.intelligence_changes import uuid_value
        if not isinstance(title, str) or not isinstance(scope, str):
            raise ValidationError("标题和编纂范围必须为文本。")
        title, scope = title.strip(), scope.strip()
        if not title or len(title) > 600 or not scope or len(scope) > 6000:
            raise ValidationError("专题须填写标题与明确编纂范围；标题最多600字，范围最多6000字。")
        key = uuid5(uuid_value(request_id), f"knowledge-special:{actor.pk}")
        page, created = m.KnowledgePage.objects.get_or_create(pk=key,
            defaults={"slug": f"special-{key}", "title": title, "scope": scope})
        if not created and (page.title != title or page.scope != scope or page.work_id or page.entity_id):
            raise ValidationError("请求编号已用于另一知识页，请重新打开创建表单。")
        return page_workspace(page, actor)
    if bool(work_id) == bool(entity_id):
        raise ValidationError("请选择一个作品或知识实体。")
    rows = (m.Work if work_id else m.Entity).objects.select_for_update()
    if entity_id:
        rows = rows.filter(merged_into__isnull=True)
    obj = get_object_or_404(rows, pk=work_id or entity_id)
    field, title = ("work", obj.title) if work_id else ("entity", obj.label)
    page, _ = m.KnowledgePage.objects.get_or_create(**{field: obj}, defaults={"slug": f"{field}-{obj.pk}", "title": title})
    return page_workspace(page, actor)


def submit_page_changes(page, revision, patches, actor, *, request_id):
    require_editor(actor)
    from catalog.services.intelligence_changes import submit_draft, uuid_value
    request_id = uuid_value(request_id)
    if not isinstance(patches, list) or not 1 <= len(patches) <= 200:
        raise ValidationError("请提交1至200个区块修改。")
    proposals = []
    for i, patch in enumerate(patches):
        if not isinstance(patch, dict) or patch.get("operation") not in {"add", "replace", "delete", "metadata"}:
            raise ValidationError("区块修改操作无效。")
        block_id = str(uuid_value(patch.get("block_id")))
        payload = {k: patch[k] for k in ("operation", "base_hash", "block", "reason", "title", "scope") if k in patch}
        payload.update(page_id=str(page.pk), block_id=block_id, human_edited=True)
        proposals.append({"id": str(uuid5(request_id, str(i))), "kind": "wiki_patch", "payload": payload, "dependencies": []})
    return submit_draft(revision, proposals, actor, request_id=request_id, origin="human",
        subject_work=page.work, subject_entity=page.entity, subject_page=page)


def submit_page_assertion(page, payload, actor, *, request_id, revision=None, origin="human"):
    """Human citation edits stay drafts and use the identical ChangeSet path.

    A citation is explicitly distinct from a verified passage. Automated and
    external producers cannot use this manual-only entry to waive evidence.
    """
    from catalog.services.intelligence_changes import submit_draft, uuid_value
    from catalog.services.knowledge_sources import create_anchor, require_revision_access
    require_editor(actor)
    key = uuid_value(request_id)
    if not isinstance(payload, dict) or not str(payload.get("text", "")).strip():
        raise ValidationError("请填写陈述内容。")
    if revision:
        require_revision_access(revision, actor, editorial=True)
    evidence = payload.get("evidence", [])
    if not isinstance(evidence, list) or len(evidence) > 50:
        raise ValidationError("每条陈述最多引用50处原文。")
    if evidence and not revision and any(not v.get("anchor_id") for v in evidence):
        raise ValidationError("引用原文须指定正文修订。")
    for value in evidence:
        if not isinstance(value, dict) or value.get("stance") not in {"supports", "opposes", "qualifies", "context"}:
            raise ValidationError("请标明证据作用。")
        if value.get("anchor_id"):
            anchor = m.EvidenceAnchor.objects.get(pk=uuid_value(value["anchor_id"]))
            require_revision_access(anchor.document_revision, actor, editorial=True)
        else:
            create_anchor(revision, value.get("segments"))
    if not evidence and not str(payload.get("source_citation", "")).strip():
        raise ValidationError("请填写可供审核的文献出处，或选择并校验馆藏原文。")
    statement_id, patch_id, block_id = [str(uuid5(key, name)) for name in ("assertion", "wiki-patch", "block")]
    blocks, _ = page_content(page)
    supersedes = payload.get("supersedes_id")
    previous_block = next((b for b in blocks if any(r.get("type") == "assertion" and r.get("id") == supersedes
        for r in b.get("references", []))), None) if supersedes else None
    if supersedes and previous_block is None:
        raise ValidationError("原陈述不属于此知识页，请从对应知识页修改。")
    block_id = previous_block["id"] if previous_block else block_id
    block = {**(previous_block or {"type": "analysis"}), "id": block_id, "text": payload["text"],
        "references": [*([r for r in previous_block.get("references", []) if r.get("id") != supersedes] if previous_block else []),
            {"type": "assertion", "id": {"change_item": statement_id}}]}
    items = [{"id": statement_id, "kind": "assertion", "payload": payload, "dependencies": []},
        {"id": patch_id, "kind": "wiki_patch", "dependencies": [statement_id], "payload": {
            "page_id": str(page.pk), "operation": "replace" if previous_block else "add", "block_id": block_id,
            "base_hash": digest(previous_block) if previous_block else None, "human_edited": True,
            "reason": "人工编辑有来源的学术陈述", "block": block}}]
    return submit_draft(revision, items, actor, request_id=key, origin=origin, subject_work=page.work, subject_entity=page.entity, subject_page=page)


def submit_assertion_draft(revision, payload, actor, *, request_id, origin="human"):
    """Manual and legacy editors propose through the same review/application path."""
    from catalog.services.intelligence_changes import submit_draft, uuid_value
    from catalog.services.knowledge_sources import require_revision_access, create_anchor
    require_editor(actor)
    require_revision_access(revision,actor,editorial=True)
    key=uuid_value(request_id)
    if not isinstance(payload,dict) or not isinstance(payload.get("text"),str) or not payload["text"].strip():
        raise ValidationError("请填写陈述内容。")
    evidence=payload.get("evidence")
    if not isinstance(evidence,list) or not 1<=len(evidence)<=50:
        raise ValidationError("请选择并校验1至50条原文依据。")
    for value in evidence:
        if not isinstance(value,dict) or value.get("stance") not in {"supports","opposes","qualifies","context"}:
            raise ValidationError("请说明每条原文的证据作用。")
        create_anchor(revision,value.get("segments"))
    statement_id,patch_id,block_id=[str(uuid5(key,name)) for name in ["assertion","wiki-patch","block"]]
    items=[{"id":statement_id,"kind":"assertion","payload":payload,"dependencies":[]},
        {"id":patch_id,"kind":"wiki_patch","dependencies":[statement_id],"payload":{
            "work_id":str(revision.asset.edition.work_id),"operation":"add","block_id":block_id,
            "human_edited":origin=="human","reason":"将审核后的陈述加入此作品知识页",
            "block":{"id":block_id,"type":"analysis","text":payload["text"],
                "references":[{"type":"assertion","id":{"change_item":statement_id}}]}}}]
    return submit_draft(revision,items,actor,request_id=key,origin=origin)
