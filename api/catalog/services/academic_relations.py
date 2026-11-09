"""Academic relation commands share the Knowledge ChangeSet and publication path.

Legacy rows are immutable compatibility records. A source-specific Assertion is
the editable identity; classification and bibliographic membership stay separate.
"""
from uuid import uuid5
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from catalog import models as m
from catalog.services.knowledge_core import entity_for_legacy, require_editor, page_content
from catalog.services.knowledge_workspace import source_hash


LEGACY = {"person": m.PersonNodeRelation, "node": m.KnowledgeRelation, "work": m.WorkNodeRelation}


def propose_work_relations(work, rows, actor):
    """Catalog selection becomes a draft; existing human relations are retained."""
    from catalog.services.knowledge_sources import digest
    outcomes = []
    for row in rows:
        node, role = row["node"], row.get("role", "general_mention")
        # An unchanged historical selector is not a new scholarly proposal.
        if not row.get("evidence_text") and m.WorkNodeRelation.objects.filter(work=work, node=node, role=role, status="published").exists():
            continue
        label = dict(m.WorkNodeRelation.Role.choices).get(role, role)
        citation = f"《{work.title}》"
        if row.get("evidence_page"):
            citation += f"，所选文件PDF第{row['evidence_page']}页（精确原文尚待核验）"
        values = {"work": work, "node": node, "role": role,
            "text": row.get("evidence_text") or f"《{work.title}》与{node.canonical_name_zh}：{label}",
            "source_citation": citation}
        key = uuid5(work.pk, digest([str(actor.pk), str(node.pk), role, values["text"], citation]))
        outcomes.append(legacy_relation_draft("work", values, actor, request_id=key))
    return outcomes


def scoped_assertions(*, entity=None, work=None):
    rows = m.Assertion.objects.all()
    if entity:
        from catalog.services.knowledge_identity import canonical_entity, family_ids
        rows = rows.filter(participants__entity_id__in=family_ids([canonical_entity(entity).pk]))
    if work:
        rows = rows.filter(Q(participants__work=work) | Q(sources__work=work))
    return rows.distinct().order_by("-updated_at", "id")


def relation_directory(actor, *, entity_id=None, work_id=None, query="", state="", offset=0, limit=30):
    require_editor(actor)
    entity = get_object_or_404(m.Entity, pk=entity_id) if entity_id else None
    work = get_object_or_404(m.Work, pk=work_id) if work_id else None
    rows = scoped_assertions(entity=entity, work=work)
    if query:
        rows = rows.filter(Q(text__icontains=query) | Q(sources__citation__icontains=query)).distinct()
    if state:
        rows = rows.filter(status=state)
    else:
        rows = rows.exclude(status__in=["superseded", "withdrawn"])
    from catalog.services.knowledge_public import assertion_data
    output = []
    for row in rows[offset:offset + limit]:
        value = assertion_data(row, actor, draft=True)
        value["base_hash"] = source_hash("assertion", row.pk)
        page = assertion_page(row, create=False)
        value["page_id"] = str(page.pk) if page else None
        output.append(value)
    pending = m.ChangeSet.objects.exclude(status="applied")
    if entity:
        pending = pending.filter(subject_entity=entity)
    if work:
        pending = pending.filter(Q(subject_work=work) | Q(document_revision__asset__edition__work=work))
    return {"count": rows.count(), "assertions": output,
        "pending_changesets": [{"id": str(v.pk), "origin": v.origin} for v in pending.order_by("-updated_at")[:30]],
        "entity_id": str(entity.pk) if entity else None,
        "title": entity.label if entity else work.title if work else "学术陈述与关系"}


@transaction.atomic
def assertion_page(statement, *, create=True):
    """Resolve an existing page; legacy backfill handles the initial body."""
    bound = m.KnowledgePage.objects.filter(dependencies__source_type="assertion", dependencies__source_id=statement.pk).order_by("id").first()
    if bound:
        return bound
    work = statement.participants.filter(role="subject", work__isnull=False).select_related("work").first()
    entities = statement.participants.filter(entity__isnull=False).order_by("id").select_related("entity")
    entity = entities.filter(role="subject").first() or entities.first()
    if work:
        field, obj, title = "work", work.work, work.work.title
    elif entity:
        field, obj, title = "entity", entity.entity, entity.entity.label
    else:
        source = statement.sources.filter(work__isnull=False).select_related("work").first()
        if not source:
            raise ValidationError("此陈述尚缺作品或实体归属，请核对迁移记录。")
        field, obj, title = "work", source.work, source.work.title
    if not create:
        return m.KnowledgePage.objects.filter(**{field: obj}).first()
    return m.KnowledgePage.objects.get_or_create(**{field: obj}, defaults={"slug": f"{field}-{obj.pk}", "title": title})[0]


@transaction.atomic
def submit_withdrawal(statement, actor, *, request_id, base_hash, reason):
    from catalog.services.intelligence_changes import submit_draft, uuid_value
    require_editor(actor)
    if not str(reason).strip():
        raise ValidationError("请说明撤回原因，原记录和历史证据会保留。")
    if base_hash != source_hash("assertion", statement.pk):
        raise ValidationError({"conflict": "陈述已变化，请重新读取后再提交撤回。"})
    page = assertion_page(statement)
    blocks, _ = page_content(page)
    key = uuid_value(request_id)
    item_id = str(uuid5(key, "withdrawal"))
    proposals = [{"id": item_id, "kind": "assertion", "dependencies": [], "payload": {
        "operation": "withdraw", "assertion_id": str(statement.pk), "base_hash": base_hash,
        "page_id": str(page.pk), "text": statement.text, "reason": str(reason).strip()}}]
    from catalog.services.knowledge_sources import digest
    for block in blocks:
        if any(r.get("type") == "assertion" and r.get("id") == str(statement.pk) for r in block.get("references", [])):
            proposals.append({"id": str(uuid5(key, block["id"])), "kind": "wiki_patch", "dependencies": [item_id],
                "payload": {"page_id": str(page.pk), "operation": "delete", "block_id": block["id"],
                    "base_hash": digest(block), "human_edited": True, "reason": str(reason)}})
    if len(proposals) == 1:
        raise ValidationError("该陈述尚未映射到知识页区块，请先完成历史知识页回填。")
    return submit_draft(None, proposals, actor, request_id=key, origin="human", subject_work=page.work, subject_entity=page.entity)


def stage_withdrawal(payload, actor):
    require_editor(actor)
    statement = get_object_or_404(m.Assertion.objects.select_for_update(), pk=payload["assertion_id"])
    if payload.get("base_hash") != source_hash("assertion", statement.pk):
        raise ValidationError({"conflict": "陈述已变化，请重新核对撤回范围。"})
    if statement.status not in {"published", "draft", "confirmed"}:
        raise ValidationError("陈述当前状态不能再次撤回。")
    if str(assertion_page(statement).pk) != payload.get("page_id"):
        raise ValidationError("撤回的知识页归属已变化。")
    return {"type": "assertion_withdrawal", "id": str(statement.pk), "page_id": payload["page_id"],
        "base_hash": payload["base_hash"], "status": "draft"}


def pending_withdrawals(page, blocks):
    referenced = {r.get("id") for b in blocks for r in b.get("references", []) if r.get("type") == "assertion"}
    return [item for item in m.ChangeItem.objects.filter(kind="assertion", decision="accepted",
        application__type="assertion_withdrawal", application__page_id=str(page.pk), application__status="draft")
        if item.application["id"] not in referenced]


def publish_withdrawals(page, blocks, actor):
    from django.utils import timezone
    from ingestion.models import AuditEvent
    from catalog.services.knowledge_workspace import invalidate_source
    for item in pending_withdrawals(page, blocks):
        statement = m.Assertion.objects.select_for_update().get(pk=item.application["id"])
        if source_hash("assertion", statement.pk) != item.application["base_hash"]:
            raise ValidationError({"conflict": "待撤回的陈述已变化，请重新审核。"})
        statement.status = "withdrawn"
        statement.save(update_fields=["status", "updated_at"])
        item.application = {**item.application, "status": "published", "published_at": timezone.now().isoformat()}
        item.save(update_fields=["application", "updated_at"])
        invalidate_source("assertion", statement.pk)
        AuditEvent.objects.create(actor=actor, action="knowledge.assertion_withdrawn", object_type="assertion",
            object_id=str(statement.pk), after={"changeset_id": str(item.changeset_id), "reason": item.payload["reason"]})


@transaction.atomic
def legacy_relation_draft(kind, values, actor, *, request_id, legacy_id=None):
    """Old HTTP/editor routes translate once; they never save legacy relations."""
    require_editor(actor)
    model = LEGACY[kind]
    old = get_object_or_404(model.objects.select_for_update(), pk=legacy_id) if legacy_id else None
    if old and values.get("operation") == "withdraw":
        from catalog.services.knowledge_migration import migrate_relation, migrate_assertion_page
        if old.status not in {"published", "confirmed", "approved"}:
            raise ValidationError("未确认的历史候选保留在旧记录中，不需要撤回公开陈述。")
        mapping = migrate_relation(old)
        statement = m.Assertion.objects.get(pk=mapping.target_id)
        migrate_assertion_page(statement)
        return submit_withdrawal(statement, actor, request_id=request_id, base_hash=values.get("base_hash"), reason=values.get("reason", ""))
    def value(name, default=None):
        return values.get(name, getattr(old, name, default) if old else default)
    def identity(model, name):
        raw = value(name)
        row = raw if isinstance(raw, model) else get_object_or_404(model, pk=raw)
        return entity_for_legacy(row)
    if kind == "person":
        person, node = identity(m.Person, "person"), identity(m.KnowledgeNode, "node")
        left, right = (node, person) if value("node_is_source", False) else (person, node)
        participants = [{"role": "subject", "entity_id": str(left.pk)}, {"role": "object", "entity_id": str(right.pk)}]
        subject, work = left, None
    elif kind == "node":
        left, right = identity(m.KnowledgeNode, "source_node"), identity(m.KnowledgeNode, "target_node")
        participants = [{"role": "subject", "entity_id": str(left.pk)}, {"role": "object", "entity_id": str(right.pk)}]
        subject, work = left, None
    else:
        raw = value("work")
        work = raw if isinstance(raw, m.Work) else get_object_or_404(m.Work, pk=raw)
        right = identity(m.KnowledgeNode, "node")
        participants = [{"role": "subject", "work_id": str(work.pk)}, {"role": "object", "entity_id": str(right.pk)}]
        subject = None
    field, obj, title = ("work", work, work.title) if work else ("entity", subject, subject.label)
    page = m.KnowledgePage.objects.get_or_create(**{field: obj}, defaults={"slug": f"{field}-{obj.pk}", "title": title})[0]
    predicate = value("relation_type", value("role", "mentions"))
    text = value("text") or value("description") or value("relation_label")
    if not text:
        raise ValidationError("请填写关系的具体陈述，不能仅以对象共现代替学术关系。")
    payload = {"text": text, "predicate": predicate, "direction": value("direction", "directed"),
        "category": "relation", "expression": "editorial_judgment", "participants": participants,
        "conditions": values.get("conditions", {}), "source_citation": value("source_citation") or value("evidence_source") or value("source", ""),
        "evidence": values.get("evidence", [])}
    if values.get("source_anchor"):
        from catalog.relation_source_anchor import choose_anchor
        from catalog.services.knowledge_sources import migrate_span
        span, revision = choose_anchor(values["source_anchor"])
        mapping = migrate_span(span)
        if not mapping.target_id:
            raise ValidationError("原证据无法核验，请在原文工作区重新选取；历史记录仍保留。")
        payload["evidence"] = [{"anchor_id": str(mapping.target_id), "stance": "context"}]
    if old:
        from catalog.services.knowledge_migration import migrate_relation, migrate_assertion_page
        if old.status in {"published", "confirmed", "approved"}:
            mapping = migrate_relation(old)
            statement = m.Assertion.objects.get(pk=mapping.target_id)
            if values.get("base_hash") != source_hash("assertion", statement.pk):
                raise ValidationError({"conflict": "旧关系已迁入知识页，请读取其陈述版本后再修改。",
                    "assertion_id": str(statement.pk), "workspace_url": f"/admin/knowledge?page={page.pk}&assertion={statement.pk}"})
            migrate_assertion_page(statement)
            payload.update(supersedes_id=str(statement.pk), base_hash=source_hash("assertion", statement.pk))
            if not payload["evidence"]:
                payload["evidence"] = [{"anchor_id": str(v.anchor_id), "stance": v.stance} for v in statement.evidence.all()]
            if values.get("operation") == "withdraw":
                return submit_withdrawal(statement, actor, request_id=request_id, base_hash=payload["base_hash"], reason=values.get("reason", "人工撤回旧关系"))
    from catalog.services.knowledge_workspace import submit_page_assertion
    return submit_page_assertion(page, payload, actor, request_id=request_id)
