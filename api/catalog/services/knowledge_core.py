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
    return {"id": str(entity.pk), "kind": entity.kind, "label": entity.label,
        "definition": entity.definition, "context": entity.context, "status": entity.status,
        "aliases": list(entity.aliases.values("text", "language", "script", "review_status", "source")),
        "identifiers": list(entity.identifiers.values("namespace", "value", "review_status", "source")),
        "person": {"birth_year": entity.person.birth_year, "death_year": entity.person.death_year,
            "biography": entity.person.biography, "authority_status": entity.person.authority_status} if entity.person_id else None}


def match_entities(label, kind, *, limit=12):
    # Names only retrieve candidates. Even one exact name does not merge identity.
    rows = m.Entity.objects.filter(kind=kind, merged_into__isnull=True).filter(
        Q(label__iexact=label) | Q(aliases__text__iexact=label, aliases__review_status="confirmed")
    ).distinct().order_by("id")[:min(limit, 30)]
    return [{**entity_data(row), "reason": "名称或已确认异名匹配，身份仍须审核", "automatic_same_identity": False} for row in rows]


@transaction.atomic
def entity_for_legacy(row):
    types = {"Person": ("person", "person", "preferred_name"), "KnowledgeNode": ("node", row.node_type if isinstance(row, m.KnowledgeNode) else "concept", "canonical_name_zh"),
        "Topic": ("topic", "topic", "name"), "Discipline": ("discipline", "discipline", "name"),
        "Subdiscipline": ("subdiscipline", "discipline", "name"), "TheorySchool": ("theory_school", "school", "name")}
    field, kind, label = types[type(row).__name__]
    if kind not in m.Entity.Kind.values:
        kind = "school" if kind in {"theory_school", "theory"} else "tradition"
    entity, created = m.Entity.objects.get_or_create(**{field: row}, defaults={"kind": kind,
        "label": getattr(row, label), "definition": getattr(row, "definition", getattr(row, "description", "")),
        "status": getattr(row, "status", getattr(row, "editorial_status", "draft"))})
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
    if kind not in m.Entity.Kind.values or not label or len(label) > 600:
        raise ValidationError("请填写合法的实体类型和名称。")
    identity = {}
    if kind == "person":
        identity["person"] = m.Person.objects.create(preferred_name=label, authority_status="draft")
    elif kind in {"concept", "school", "tradition", "debate", "question"}:
        node_kind = {"school": "school", "tradition": "tradition", "debate": "debate", "question": "concept", "concept": "concept"}[kind]
        identity["node"] = m.KnowledgeNode.objects.create(node_type=node_kind, canonical_name_zh=label,
            slug=f"knowledge-{uuid4().hex}", definition=payload.get("definition", ""), status="draft", created_by=actor)
    return m.Entity.objects.create(kind=kind, label=label, definition=payload.get("definition", ""),
        context=payload.get("context", ""), **identity)


@transaction.atomic
def create_assertion(payload, revision, actor):
    require_editor(actor)
    require_revision_access(revision, actor, editorial=True)
    text = payload.get("text")
    evidence = payload.get("evidence", [])
    if not isinstance(text, str) or not text.strip() or len(text) > 20000 or not evidence:
        raise ValidationError("学术陈述须包含正文和经原文核对的证据。")
    expression = payload.get("expression", "author_claim")
    if expression not in {"author_claim", "direct_quote", "paraphrase", "criticized_claim", "editorial_judgment"}:
        raise ValidationError("论述身份无效。")
    statement = m.Assertion.objects.create(text=text, predicate=payload.get("predicate", ""),
        category=payload.get("category", "proposition"), direction=payload.get("direction", "directed"),
        expression=expression, conditions=payload.get("conditions", {}), source_quality="verified_text", created_by=actor)
    for participant in payload.get("participants", []):
        role = participant.get("role")
        values = {key: participant[key] for key in ("entity_id", "work_id", "edition_id") if participant.get(key)}
        if role not in {"subject", "object", "claimant", "quoted", "criticized", "context"} or len(values) != 1:
            raise ValidationError("陈述参与者须有明确角色和唯一身份。")
        if "entity_id" in values and not m.Entity.objects.filter(pk=values["entity_id"], merged_into__isnull=True).exists():
            raise ValidationError("陈述包含未解析的实体。")
        m.AssertionParticipant.objects.create(assertion=statement, role=role, **values)
    attribution = payload.get("attribution_id")
    if attribution and not m.Entity.objects.filter(pk=attribution, kind__in=["person", "organization"]).exists():
        raise ValidationError("论述归属须为已解析的人物或组织。")
    m.AssertionSource.objects.create(assertion=statement, work=revision.asset.edition.work,
        edition=revision.asset.edition, document_revision=revision, attribution_id=attribution,
        expression=expression, provenance={"attribution_status": "explicit" if attribution else "unresolved"})
    for row in evidence:
        if row.get("stance") not in {"supports", "opposes", "qualifies", "context"}:
            raise ValidationError("请标明证据的支持、反对、限定或语境作用。")
        anchor = create_anchor(revision, row.get("segments"))
        m.AssertionEvidence.objects.create(assertion=statement, anchor=anchor, stance=row["stance"])
    return statement


def page_content(page):
    latest = m.EditorialRevision.objects.filter(target_type="knowledge_page", target_id=page.pk,
        status="draft").order_by("-revision").first()
    return (deepcopy(latest.materialized_preview.get("body_blocks", [])), latest) if latest else (deepcopy(page.body_blocks), None)


def normalize_page_blocks(blocks, *, retained=None):
    from catalog.services.editorial_blocks import normalize_typed_block
    if not isinstance(blocks, list) or len(blocks) > 500:
        raise ValidationError("知识页最多保存500个区块。")
    old = {b["id"]: b for b in (retained or [])}
    result, seen = [], set()
    for raw in blocks:
        block = normalize_typed_block(raw, retained=old.get(raw.get("id")))
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
def apply_page_patch(payload, actor, *, request_key):
    require_editor(actor)
    page = m.KnowledgePage.objects.select_for_update().get(pk=payload["page_id"])
    blocks, _ = page_content(page)
    by_id = {b["id"]: b for b in blocks}
    operation, key = payload.get("operation"), payload.get("block_id")
    current = by_id.get(key)
    if operation not in {"add", "replace", "delete"} or not key:
        raise ValidationError("知识页补丁须指定稳定区块和操作。")
    if (operation == "add" and current is not None) or (operation != "add" and (current is None or digest(current) != payload.get("base_hash"))):
        raise ValidationError({"conflict": "该区块已修改，请对照当前正文重新审核。", "block_id": key})
    if operation != "delete":
        proposed = {**payload.get("block", {}), "id": key, "origin": "intelligence", "human_edited": False}
        value = normalize_page_blocks([proposed], retained=[current] if current else [])[0]
    if operation == "add":
        blocks.append(value)
    elif operation == "replace":
        blocks = [value if b["id"] == key else b for b in blocks]
    else:
        blocks = [b for b in blocks if b["id"] != key]
    from catalog.services.editorial_revision import create_editorial_revision
    return create_editorial_revision(target_type="knowledge_page", target_id=page.pk,
        patch={"body_blocks": blocks}, actor=actor, idempotency_key=request_key,
        change_note=payload.get("reason", "审核知识页局部修改"))


def export_page(page, actor, *, draft=False):
    if draft:
        require_editor(actor)
        blocks, revision = page_content(page)
    else:
        if page.status != "published":
            raise Http404
        blocks = page.body_blocks
        revision = m.EditorialRevision.objects.filter(target_type="knowledge_page", target_id=page.pk, status="published").order_by("-revision").first()
    lines = [f"# {page.title}", "", f"<!-- STL knowledge_page={page.pk} editorial_revision={revision.pk if revision else 'legacy'}; database is authoritative -->", ""]
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
    return json.dumps(ref, ensure_ascii=False)
