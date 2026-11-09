"""One draft/review/apply service for the UI, Intelligence and external MCP."""
from copy import deepcopy
from uuid import UUID, uuid4
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from catalog import models as m
from catalog.services.knowledge_core import require_editor, create_entity, create_assertion, apply_page_patch
from catalog.services.knowledge_sources import digest, require_revision_access
from ingestion.models import AuditEvent

KINDS = {"entity", "alias", "assertion", "wiki_patch"}


def proposal_fingerprint(revision_id, kind, payload, proposals, trail=()):
    """Stable across runs, while preserving source, context and opposing evidence."""
    def normalize(value, path=()):
        if isinstance(value, dict):
            if set(value) == {"change_item"}:
                key = str(value["change_item"])
                if key in trail or key not in proposals:
                    raise ValidationError("建议引用缺少依赖项或形成循环。")
                item = proposals[key]
                return {"candidate_fingerprint": proposal_fingerprint(revision_id, item["kind"], item["payload"], proposals, (*trail, key))}
            return {k:normalize(v, (*path, k)) for k,v in value.items() if not (not path and k in {"candidates", "comparisons", "reason", "base_revision"})
                and not (kind == "wiki_patch" and ((not path and k == "block_id") or (path == ("block",) and k == "id")))}
        if isinstance(value, list):
            return [normalize(v, path) for v in value]
        return value
    return digest([str(revision_id), kind, normalize(payload)])


def uuid_value(raw):
    try:
        return UUID(str(raw))
    except (ValueError, TypeError):
        raise ValidationError("缺少合法的请求或对象ID。")


@transaction.atomic
def submit_draft(revision, proposals, actor, *, request_id, origin="external", run=None):
    require_editor(actor)
    require_revision_access(revision, actor, editorial=True)
    request_id = uuid_value(request_id)
    if not isinstance(proposals, list) or len(proposals) > 2000:
        raise ValidationError("每份变更集最多2000项建议。")
    fingerprint = digest([str(revision.pk), proposals, origin])
    previous = m.ChangeSet.objects.filter(request_id=request_id).first()
    if previous:
        if previous.input_hash != fingerprint or previous.created_by_id != actor.pk:
            raise ValidationError("请求ID已用于其他草稿。")
        return previous
    changeset = m.ChangeSet.objects.create(document_revision=revision, created_by=actor,
        request_id=request_id, input_hash=fingerprint, origin=origin, run=run)
    keys = [str(uuid_value(item.get("id"))) for item in proposals]
    if len(keys) != len(set(keys)) or m.ChangeItem.objects.filter(pk__in=keys).exists():
        raise ValidationError("建议ID重复。")
    proposal_map = dict(zip(keys, proposals))
    seen = set()
    for key, item in zip(keys, proposals):
        kind = item.get("kind")
        dependencies = [str(uuid_value(v)) for v in item.get("dependencies", [])]
        if kind not in KINDS or not isinstance(item.get("payload"), dict) or set(dependencies) - set(keys) or key in dependencies:
            raise ValidationError("建议类型、内容或依赖无效。")
        payload = item["payload"]
        item_hash = proposal_fingerprint(revision.pk, kind, payload, proposal_map)
        if item_hash in seen:
            raise ValidationError("变更集中存在内容和来源完全相同的建议，请保留一项并调整依赖。")
        seen.add(item_hash)
        rejected = m.ChangeItem.objects.filter(fingerprint=item_hash, decision="rejected").order_by("-reviewed_at").first()
        artifact = None
        if item.get("source_artifact_id"):
            artifact = m.CurationArtifact.objects.filter(pk=uuid_value(item["source_artifact_id"]),run=run).first() if run else None
            if not artifact:
                raise ValidationError("建议来源产物不属于此策展任务。")
        m.ChangeItem.objects.create(id=key, changeset=changeset, kind=kind, payload=payload,
            dependencies=dependencies, fingerprint=item_hash, source_artifact=artifact, decision="rejected" if rejected else "pending",
            decision_note=rejected.decision_note if rejected else "", reviewed_by=rejected.reviewed_by if rejected else None,
            reviewed_at=rejected.reviewed_at if rejected else None)
    _ordered(list(changeset.items.all()))
    AuditEvent.objects.create(actor=actor, action="intelligence.draft_submitted", object_type="changeset",
        object_id=str(changeset.pk), after={"count": len(proposals), "origin": origin})
    return changeset


def _ordered(items):
    remaining = {str(item.pk): item for item in items}
    output, done = [], set()
    while remaining:
        ready = [item for item in remaining.values() if not (set(item.dependencies) & set(remaining))]
        if not ready:
            raise ValidationError("变更依赖形成循环。")
        for item in ready:
            output.append(item)
            done.add(str(item.pk))
            del remaining[str(item.pk)]
    return output


def refresh_fingerprints(changeset):
    """Also updates dependent meanings after an editor changes an identity."""
    items = list(changeset.items.select_for_update().all())
    proposals = {str(v.pk):{"kind":v.kind,"payload":v.payload} for v in items}
    values = {v.pk:proposal_fingerprint(changeset.document_revision_id,v.kind,v.payload,proposals) for v in items}
    if len(set(values.values())) != len(values):
        raise ValidationError("修改后出现内容和来源完全重复的建议，请保留其中一项。")
    # Temporary, transaction-local keys permit exchanging two valid meanings.
    for item in items:
        m.ChangeItem.objects.filter(pk=item.pk).update(fingerprint=digest(["rehash",str(uuid4()),str(item.pk)]))
    for item in items:
        m.ChangeItem.objects.filter(pk=item.pk).update(fingerprint=values[item.pk])


@transaction.atomic
def review(changeset_id, decisions, actor, *, expected_version):
    require_editor(actor)
    changeset = m.ChangeSet.objects.select_for_update().get(pk=changeset_id)
    require_revision_access(changeset.document_revision, actor, editorial=True)
    if changeset.version != expected_version:
        raise ValidationError({"conflict": "审核工作区已变化，请刷新；已保存决定仍保留。"})
    if not isinstance(decisions, list) or not 1 <= len(decisions) <= 2000:
        raise ValidationError("请选择要审核的建议。")
    for decision in decisions:
        item = get_object_or_404(changeset.items.select_for_update(), pk=uuid_value(decision.get("id")))
        if item.application:
            raise ValidationError("已应用的建议请通过正式修订修改。")
        if decision.get("decision") not in {"accepted", "rejected", "deferred", "pending"}:
            raise ValidationError("审核决定无效。")
        if "payload" in decision:
            if not isinstance(decision["payload"], dict):
                raise ValidationError("修改内容必须是结构化对象。")
            edited = decision["payload"] != item.payload
            item.payload = decision["payload"]
            if edited and item.kind == "wiki_patch":
                item.payload = {**item.payload, "human_edited": True}
        item.decision, item.decision_note = decision["decision"], str(decision.get("note", ""))[:1000]
        item.reviewed_by, item.reviewed_at, item.conflict = actor, timezone.now(), {}
        item.save()
    refresh_fingerprints(changeset)
    changeset.version += 1
    changeset.status = "reviewing"
    changeset.save(update_fields=["version", "status", "updated_at"])
    AuditEvent.objects.create(actor=actor, action="intelligence.reviewed", object_type="changeset",
        object_id=str(changeset.pk), after={"items": [str(d["id"]) for d in decisions], "version": changeset.version})
    return changeset


def _resolved(value, applications):
    if isinstance(value, dict):
        if set(value) == {"change_item"}:
            result = applications.get(str(value["change_item"]))
            if not result or not result.get("id"):
                raise ValidationError("依赖项尚未保存。")
            return result["id"]
        return {k: _resolved(v, applications) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolved(v, applications) for v in value]
    return value


def _groups(items):
    remaining = {str(i.pk): i for i in items}
    while remaining:
        group = {next(iter(remaining))}
        while True:
            expanded = group | {key for key, item in remaining.items() if key in group or set(item.dependencies) & group}
            expanded |= {dep for key in group for dep in remaining[key].dependencies if dep in remaining}
            if expanded == group:
                break
            group = expanded
        yield [remaining.pop(key) for key in sorted(group)]


@transaction.atomic
def apply(changeset_id, selected_ids, actor, *, request_id, expected_version):
    require_editor(actor)
    changeset = m.ChangeSet.objects.select_for_update().get(pk=changeset_id)
    require_revision_access(changeset.document_revision, actor, editorial=True)
    selected = sorted(set(str(uuid_value(v)) for v in selected_ids))
    request_id = uuid_value(request_id)
    fingerprint = digest([str(changeset.pk), selected, expected_version])
    receipt = m.ChangeReceipt.objects.filter(request_id=request_id).first()
    if receipt:
        if receipt.input_hash != fingerprint or receipt.actor_id != actor.pk:
            raise ValidationError("请求ID已用于其他保存操作。")
        return receipt.result
    if changeset.version != expected_version:
        raise ValidationError({"conflict": "工作区版本已变化，请重新读取审核决定。"})
    all_items = {str(i.pk): i for i in changeset.items.select_for_update().all()}
    if not selected or set(selected) - all_items.keys():
        raise ValidationError("请选择当前变更集中的建议。")
    applications = {key: item.application for key, item in all_items.items() if item.application}
    eligible, blocked = [], {}
    for key in selected:
        item = all_items[key]
        if item.application:
            continue
        missing = [dep for dep in item.dependencies if not all_items[dep].application and (
            dep not in selected or all_items[dep].decision != "accepted")]
        if item.decision != "accepted" or missing:
            blocked[key] = {"reason": "尚未确认" if item.decision != "accepted" else "依赖尚未确认或未选择", "dependencies": missing}
        else:
            eligible.append(item)
    for group in _groups(eligible):
        local = dict(applications)
        try:
            with transaction.atomic():
                for item in _ordered(group):
                    payload = _resolved(deepcopy(item.payload), local)
                    if item.kind == "entity":
                        obj = create_entity(payload, actor)
                        result = {"type": "entity", "id": str(obj.pk), "status": obj.status}
                    elif item.kind == "assertion":
                        obj = create_assertion(payload, changeset.document_revision, actor)
                        result = {"type": "assertion", "id": str(obj.pk), "status": obj.status}
                    elif item.kind == "alias":
                        entity = m.Entity.objects.get(pk=payload["entity_id"])
                        text = str(payload.get("text", "")).strip()
                        if not text or len(text) > 600:
                            raise ValidationError("异名不可为空或超过600字符。")
                        obj, _ = m.EntityAlias.objects.get_or_create(entity=entity, text=text, language=payload.get("language", ""),
                            defaults={"review_status": "confirmed", "source": {"changeset": str(changeset.pk)}})
                        result = {"type": "alias", "id": str(obj.pk)}
                    else:
                        obj = apply_page_patch(payload, actor, request_key=f"change:{item.pk}", origin=changeset.origin)
                        result = {"type": "editorial_revision", "id": str(obj.pk), "page_id": str(obj.target_id), "status": "draft"}
                    item.application, item.conflict = result, {}
                    item.save(update_fields=["application", "conflict", "updated_at"])
                    local[str(item.pk)] = result
            applications = local
        except (ValidationError, IntegrityError, KeyError, ValueError, ObjectDoesNotExist) as exc:
            reason = str(exc.detail) if isinstance(exc, ValidationError) else "该事务组无法保存，请核对身份、来源和依赖。"
            for item in group:
                blocked[str(item.pk)] = {"reason": reason}
                m.ChangeItem.objects.filter(pk=item.pk).update(conflict={"reason": reason})
    changeset.version += 1
    changeset.status = "applied" if all(i.application or i.decision == "rejected" for i in changeset.items.all()) else "partial"
    changeset.save(update_fields=["version", "status", "updated_at"])
    result = {"changeset_id": str(changeset.pk), "version": changeset.version,
        "saved": {key: applications[key] for key in selected if key in applications}, "blocked": blocked,
        "publication": "drafts_only"}
    m.ChangeReceipt.objects.create(changeset=changeset, request_id=request_id, input_hash=fingerprint, result=result, actor=actor)
    AuditEvent.objects.create(actor=actor, action="intelligence.applied", object_type="changeset",
        object_id=str(changeset.pk), after={"saved": list(result["saved"]), "blocked": list(blocked)})
    return result
