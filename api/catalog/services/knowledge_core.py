"""Canonical knowledge writes shared by transports and the review workspace."""
from copy import deepcopy
from uuid import UUID, uuid4

from django.db import transaction
from django.db.models import Q
from django.http import Http404
from rest_framework.exceptions import PermissionDenied, ValidationError

from catalog import models as m
from catalog.services.knowledge_sources import digest, create_anchor, require_revision_access
from common.capabilities import Capability, has_capability


def require_editor(actor):
    if not actor or not actor.is_active or not has_capability(actor, Capability.EDIT_METADATA):
        raise PermissionDenied("当前账户不能编辑知识草稿。")


def entity_data(entity):
    from catalog.services.knowledge_identity import canonical_entity
    return {"id": str(entity.pk), "kind": entity.kind, "label": entity.label,
        "canonical_id": str(canonical_entity(entity).pk),
        "definition": entity.definition, "context": entity.context, "status": entity.status,
        "aliases": list(entity.aliases.values("text", "language", "script", "review_status", "source")),
        "identifiers": list(entity.identifiers.values("namespace", "value", "review_status", "source")),
        "person": {"birth_year": entity.person.birth_year, "death_year": entity.person.death_year,
            "biography": entity.person.biography, "authority_status": entity.person.authority_status} if entity.person_id else None}


def match_entities(label, kind, *, limit=12):
    # Names only retrieve candidates. Even one exact name does not merge identity.
    rows = m.Entity.objects.filter(kind=kind).filter(
        Q(label__iexact=label) | Q(aliases__text__iexact=label, aliases__review_status="confirmed")
    ).distinct().order_by("id")[:min(limit, 30)]
    from catalog.services.knowledge_identity import canonical_entity
    candidates = {value.pk: value for row in rows if (value := canonical_entity(row))}
    return [{**entity_data(row), "reason": "名称或已确认异名匹配，身份仍须审核", "automatic_same_identity": False} for row in candidates.values()]


@transaction.atomic
def entity_for_legacy(row):
    mapping = m.KnowledgeLegacyMapping.objects.filter(source_type=row._meta.label_lower, source_id=row.pk, target_type="entity").first()
    if mapping and mapping.target_id:
        return m.Entity.objects.get(pk=mapping.target_id)
    if isinstance(row, (m.Concept, m.TheorySchool)):
        # Only an existing reviewed identity mapping can connect the old profile
        # to a node. Equal labels alone are never a migration merge rule.
        from catalog.services.canonical_identity import mapped_node_for_legacy, CanonicalIdentityError
        try:
            node = mapped_node_for_legacy(type(row).__name__, row.pk)
        except CanonicalIdentityError:
            node = None
        if node:
            entity = entity_for_legacy(node)
            m.KnowledgeLegacyMapping.objects.create(source_type=row._meta.label_lower, source_id=row.pk,
                target_type="entity", target_id=entity.pk, quality="reviewed_identity_mapping",
                provenance={"node_id":str(node.pk), "legacy_profile_retained":True})
            return entity
    types = {"Person": ("person", "person", "preferred_name"), "KnowledgeNode": ("node", row.node_type if isinstance(row, m.KnowledgeNode) else "concept", "canonical_name_zh"),
        "Topic": ("topic", "topic", "name"), "Discipline": ("discipline", "discipline", "name"),
        "Subdiscipline": ("subdiscipline", "discipline", "name"), "TheorySchool": ("theory_school", "school", "name"),
        "Concept": ("concept", "concept", "name")}
    field, kind, label = types[type(row).__name__]
    kind = {"theory_tradition": "tradition", "research_problem": "question", "subdiscipline": "discipline"}.get(kind,kind)
    if kind not in m.Entity.Kind.values:
        kind = "school" if kind in {"theory_school", "theory"} else "tradition"
    entity, created = m.Entity.objects.get_or_create(**{field: row}, defaults={"kind": kind,
        "label": getattr(row, label), "definition": getattr(row, "definition", getattr(row, "description", "")),
        "status": getattr(row, "status", getattr(row, "editorial_status", "draft"))})
    if isinstance(row, m.Person):
        for variant in m.PersonNameVariant.objects.filter(person=row):
            m.EntityAlias.objects.get_or_create(entity=entity, text=variant.name, language=variant.language,
                defaults={"review_status": "confirmed" if variant.is_verified else "legacy",
                          "source": {"legacy_type": "catalog.personnamevariant", "legacy_id": str(variant.pk),
                                     "kind": variant.source_kind, "note": variant.source_note}})
    elif isinstance(row, m.KnowledgeNode):
        for alias in m.KnowledgeNodeAlias.objects.filter(node=row):
            m.EntityAlias.objects.get_or_create(entity=entity, text=alias.alias, language=alias.language,
                defaults={"review_status": "confirmed" if alias.is_verified else "legacy",
                          "source": {"legacy_type": "catalog.knowledgenodealias", "legacy_id": str(alias.pk), "kind": alias.source_kind}})
    for alias in getattr(row, "search_aliases", []):
        if isinstance(alias, str) and alias and alias != entity.label:
            m.EntityAlias.objects.get_or_create(entity=entity, text=alias,
                defaults={"review_status":"legacy", "source":{"legacy_type":row._meta.label_lower,"legacy_id":str(row.pk)}})
    m.KnowledgeLegacyMapping.objects.get_or_create(source_type=row._meta.label_lower, source_id=row.pk, target_type="entity",
        defaults={"target_id": entity.pk, "quality": "identity_preserved", "provenance": {"legacy_id": str(row.pk)}})
    if created and isinstance(row, m.Person):
        for alias in row.aliases:
            if isinstance(alias, str) and alias:
                m.EntityAlias.objects.create(entity=entity, text=alias, source={"person_id": str(row.pk)}, review_status="legacy")
        for namespace, value in row.external_ids.items():
            if isinstance(value, str) and value:
                m.EntityIdentifier.objects.create(entity=entity, namespace=namespace, value=value,
                    source={"person_id": str(row.pk), "legacy_source": row.identifier_sources.get(namespace)}, review_status="legacy")
    return entity


@transaction.atomic
def create_entity(payload, actor):
    require_editor(actor)
    if payload.get("existing_id"):
        entity = m.Entity.objects.filter(pk=payload["existing_id"], merged_into__isnull=True).first()
        if not entity or entity.kind != payload.get("kind"):
            raise ValidationError("所选实体类型或身份已变化。")
        return entity
    kind, label = payload.get("kind"), str(payload.get("label", "")).strip()
    if kind not in m.Entity.Kind.values or not label or len(label) > 240:
        raise ValidationError("请填写合法的实体类型和名称。")
    identity = {}
    if kind == "person":
        identity["person"] = m.Person.objects.create(preferred_name=label, authority_status="draft", biography=payload.get("definition", ""))
        m.ScholarProfile.objects.create(person=identity["person"], slug=f"scholar-{identity['person'].pk}")
    elif kind in {"concept", "school", "tradition", "debate", "question"}:
        node_kind = {"school": "theory_tradition", "tradition": "theory_tradition", "debate": "debate", "question": "research_problem", "concept": "concept"}[kind]
        identity["node"] = m.KnowledgeNode.objects.create(node_type=node_kind, canonical_name_zh=label,
            slug=f"knowledge-{uuid4().hex}", definition=payload.get("definition", ""), status="draft", created_by=actor)
    elif kind == "topic":
        identity["topic"] = m.Topic.objects.create(name=label,slug=f"topic-{uuid4().hex}",editorial_status="draft")
    elif kind == "discipline":
        slug = f"discipline-{uuid4().hex}"
        identity["discipline"] = m.Discipline.objects.create(name=label,slug=slug,code=slug,editorial_status="draft")
    return m.Entity.objects.create(kind=kind, label=label, definition=payload.get("definition", ""),
        context=payload.get("context", ""), **identity)


@transaction.atomic
def create_assertion(payload, revision, actor, *, allow_citation=False, subject_work=None):
    require_editor(actor)
    if revision:
        require_revision_access(revision, actor, editorial=True)
    text = payload.get("text")
    if payload.get("unresolved_names") or payload.get("unresolved_participants"):
        raise ValidationError("请先在审核中解决主张者或参与者身份。")
    evidence = payload.get("evidence", [])
    citation = str(payload.get("source_citation", "")).strip()
    if not isinstance(text, str) or not text.strip() or len(text) > 20000:
        raise ValidationError("学术陈述须包含正文。")
    if not evidence and not (allow_citation and citation and len(citation) <= 20000):
        raise ValidationError("学术陈述须包含正文和经原文核对的证据。")
    if evidence and not revision and any(not row.get("anchor_id") for row in evidence):
        raise ValidationError("原文证据须固定到实际正文修订。")
    previous = None
    if payload.get("supersedes_id"):
        previous = m.Assertion.objects.select_for_update().get(pk=payload["supersedes_id"])
        from catalog.services.knowledge_workspace import source_hash
        if payload.get("base_hash") != source_hash("assertion", previous.pk):
            raise ValidationError({"conflict": "该陈述已变化，请对照当前记录重新审核。"})
    expression = payload.get("expression", "author_claim")
    if expression not in {"author_claim", "direct_quote", "paraphrase", "criticized_claim", "editorial_judgment"}:
        raise ValidationError("论述身份无效。")
    conditions=payload.get("conditions",{})
    if not isinstance(conditions,dict) or any(not isinstance(v,str) or len(v)>4000 for v in conditions.values()):
        raise ValidationError("适用条件须按时间、地区、人群或概念用法填写文字。")
    if payload.get("direction","directed") not in {"directed","bidirectional","undirected"}:
        raise ValidationError("陈述方向无效。")
    statement = m.Assertion.objects.create(text=text, predicate=payload.get("predicate", ""),
        category=payload.get("category", "proposition"), direction=payload.get("direction", "directed"),
        expression=expression, conditions=payload.get("conditions", {}),
        source_quality="verified_text" if evidence else "human_citation", created_by=actor,
        supersedes=previous)
    for participant in payload.get("participants", []):
        role = participant.get("role")
        values = {key: participant[key] for key in ("entity_id", "work_id", "edition_id") if participant.get(key)}
        if role not in {"subject", "object", "claimant", "quoted", "criticized", "context"} or len(values) != 1:
            raise ValidationError("陈述参与者须有明确角色和唯一身份。")
        if "entity_id" in values:
            from catalog.services.knowledge_identity import canonical_entity
            identity = m.Entity.objects.filter(pk=values["entity_id"]).first()
            if identity is None:
                raise ValidationError("陈述包含未解析的实体。")
            values["entity_id"] = canonical_entity(identity).pk
        m.AssertionParticipant.objects.create(assertion=statement, role=role, **values)
    attribution = payload.get("attribution_id")
    if attribution and not m.Entity.objects.filter(pk=attribution, kind__in=["person", "organization"]).exists():
        raise ValidationError("论述归属须为已解析的人物或组织。")
    source_defaults = {"attribution_id": attribution, "expression": expression, "citation": citation,
        "provenance": {"attribution_status": "explicit" if attribution else "unresolved", "exact_location_verified": bool(evidence)}}
    if revision or not evidence:
        m.AssertionSource.objects.create(assertion=statement, work=revision.asset.edition.work if revision else subject_work,
            edition=revision.asset.edition if revision else None, document_revision=revision, **source_defaults)
    for row in evidence:
        if row.get("stance") not in {"supports", "opposes", "qualifies", "context"}:
            raise ValidationError("请标明证据的支持、反对、限定或语境作用。")
        if row.get("anchor_id"):
            anchor = m.EvidenceAnchor.objects.select_related("document_revision__asset__edition__work").get(pk=row["anchor_id"])
            require_revision_access(anchor.document_revision, actor, editorial=True)
        else:
            anchor = create_anchor(revision, row.get("segments"))
        anchor_revision = anchor.document_revision
        m.AssertionSource.objects.get_or_create(assertion=statement, document_revision=anchor_revision,
            defaults={"work": anchor_revision.asset.edition.work, "edition": anchor_revision.asset.edition, **source_defaults})
        m.AssertionEvidence.objects.create(assertion=statement, anchor=anchor, stance=row["stance"])
    return statement


def page_content(page):
    latest = m.EditorialRevision.objects.filter(target_type="knowledge_page", target_id=page.pk,
        status="draft").order_by("-revision").first()
    if latest:
        return deepcopy(latest.materialized_preview.get("body_blocks", [])), latest
    published = m.EditorialRevision.objects.filter(target_type="knowledge_page", target_id=page.pk,
        status="published").order_by("-revision").first()
    return deepcopy(page.body_blocks), published


def normalize_page_blocks(blocks, *, retained=None):
    from catalog.services.editorial_blocks import normalize_typed_block, normalize_text_format
    if not isinstance(blocks, list) or len(blocks) > 500:
        raise ValidationError("知识页最多保存500个区块。")
    old = {b["id"]: b for b in (retained or [])}
    result, seen = [], set()
    for raw in blocks:
        block = normalize_text_format(raw, normalize_typed_block(raw, retained=old.get(raw.get("id"))))
        if block["id"] in seen:
            raise ValidationError("知识区块ID重复。")
        seen.add(block["id"])
        block["origin"] = raw.get("origin", "human")
        block["human_edited"] = bool(raw.get("human_edited", block["origin"] == "human"))
        block["base_revision"] = raw.get("base_revision", 0)
        block["content_hash"] = digest({k: v for k, v in block.items() if k not in {"content_hash", "base_revision"}})
        result.append(block)
    return result


@transaction.atomic
def apply_page_patch(payload, actor, *, request_key, origin="intelligence"):
    require_editor(actor)
    if payload.get("page_id"):
        page = m.KnowledgePage.objects.select_for_update().get(pk=payload["page_id"])
        if payload.get("entity_id") and str(page.entity_id) != str(payload["entity_id"]):
            raise ValidationError({"conflict":"此修改对应的旧页面与审核选定身份不同，请保留原页面并重新编纂。"})
    elif payload.get("entity_id"):
        entity = m.Entity.objects.select_for_update().get(pk=payload["entity_id"], merged_into__isnull=True)
        page, _ = m.KnowledgePage.objects.get_or_create(entity=entity, defaults={"slug": f"entity-{entity.pk}", "title": entity.label})
    elif payload.get("work_id"):
        work = m.Work.objects.select_for_update().get(pk=payload["work_id"])
        page, _ = m.KnowledgePage.objects.get_or_create(work=work, defaults={"slug":f"work-{work.pk}","title":work.title})
    else:
        raise ValidationError("知识页修改须指定已有页面、作品或实体。")
    blocks, _ = page_content(page)
    if payload.get("operation") == "metadata":
        if origin != "human":
            raise ValidationError("标题与范围须由管理员在知识页中编辑。")
        if digest(page_metadata(page, draft=True)) != payload.get("base_hash"):
            raise ValidationError({"conflict": "标题或范围已修改，请核对当前页面信息。"})
        title, scope = payload.get("title"), payload.get("scope")
        if not isinstance(title, str) or not title.strip() or len(title) > 600 or not isinstance(scope, str) or len(scope) > 6000:
            raise ValidationError("请填写有效标题和编纂范围。")
        if not page.work_id and not page.entity_id and not scope.strip():
            raise ValidationError("专题必须保留明确编纂范围。")
        from catalog.services.editorial_revision import create_editorial_revision
        revision = create_editorial_revision(target_type="knowledge_page", target_id=page.pk,
            patch={"title": title.strip(), "scope": scope.strip(), "body_blocks": blocks}, actor=actor, idempotency_key=request_key,
            change_note=payload.get("reason", "审核知识页标题与范围"))
        from catalog.services.knowledge_workspace import invalidate_source
        invalidate_source("knowledge_page", page.pk)
        return revision
    by_id = {b["id"]: b for b in blocks}
    operation, key = payload.get("operation"), payload.get("block_id")
    current = by_id.get(key)
    if operation not in {"add", "replace", "delete"} or not key:
        raise ValidationError("知识页补丁须指定稳定区块和操作。")
    if (operation == "add" and current is not None) or (operation != "add" and (current is None or digest(current) != payload.get("base_hash"))):
        raise ValidationError({"conflict": "该区块已修改，请对照当前正文重新审核。", "block_id": key})
    if operation != "add" and origin == "intelligence" and current and (
            current.get("human_edited") or current.get("origin") in {"human","manual","migration"}) and not payload.get("human_edited"):
        raise ValidationError({"conflict":"此区块包含人工正文，请在可视化编辑器中审阅并明确修改后再保存。","block_id":key})
    if operation != "delete":
        proposed = {**payload.get("block", {}), "id": key, "origin": origin,
                    "human_edited": bool(payload.get("human_edited"))}
        value = normalize_page_blocks([proposed], retained=[current] if current else [])[0]
    if operation == "add":
        blocks.append(value)
    elif operation == "replace":
        blocks = [value if b["id"] == key else b for b in blocks]
    else:
        blocks = [b for b in blocks if b["id"] != key]
    from catalog.services.editorial_revision import create_editorial_revision
    revision = create_editorial_revision(target_type="knowledge_page", target_id=page.pk,
        patch={**page_metadata(page, draft=True), "body_blocks": blocks}, actor=actor, idempotency_key=request_key,
        change_note=payload.get("reason", "审核知识页局部修改"))
    from catalog.services.knowledge_workspace import sync_dependencies, invalidate_source
    sync_dependencies(page, blocks, changed_blocks={str(key)})
    invalidate_source("knowledge_page", page.pk)
    return revision


def page_metadata(page, *, draft=False):
    revision = page_content(page)[1] if draft else None
    snapshot = revision.materialized_preview if revision else {}
    return {"title": snapshot.get("title", page.title), "scope": snapshot.get("scope", page.scope)}


def export_page(page, actor, *, draft=False):
    if draft:
        require_editor(actor)
        blocks, revision = page_content(page)
    else:
        from catalog.services.knowledge_public import page_data
        blocks = page_data(page, actor)["blocks"]
        revision = m.EditorialRevision.objects.filter(target_type="knowledge_page", target_id=page.pk, status="published").order_by("-revision").first()
    metadata = page_metadata(page, draft=draft)
    lines = [f"# {metadata['title']}", "", metadata['scope'], "", f"<!-- STL knowledge_page={page.pk} editorial_revision={revision.pk if revision else 'legacy'}; database is authoritative -->", ""]
    for block in blocks:
        lines.extend([f"<!-- block={block['id']} hash={block.get('content_hash', '')} -->", block.get("text", ""), ""])
        for ref in block.get("references", []):
            lines.extend(["```json", json_reference(ref, actor, draft), "```", ""])
    return "\n".join(lines)


def json_reference(ref, actor, draft):
    import json
    from catalog.services.knowledge_sources import locator
    if ref.get("type") == "anchor":
        anchor = m.EvidenceAnchor.objects.get(pk=ref["id"])
        return json.dumps(locator(anchor, actor, editorial=draft), ensure_ascii=False)
    if ref.get("type") == "assertion":
        from catalog.services.knowledge_public import assertion_data
        return json.dumps(assertion_data(m.Assertion.objects.get(pk=ref["id"]), actor, draft=draft), ensure_ascii=False, default=str)
    return json.dumps(ref, ensure_ascii=False)
