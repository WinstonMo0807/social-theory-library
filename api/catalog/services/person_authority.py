"""Explicit authority edits on the original Person, with original audit/outbox."""
import copy
import json
from uuid import uuid4

from django.core.exceptions import ValidationError as ModelValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.crypto import salted_hmac
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from accounts.models import User
from common.capabilities import Capability, has_capability
from ingestion.models import AuditEvent
from catalog.models import Person, PersonNameVariant, ScholarProfile, Contribution, EditorialRevision, Edition
from catalog.contracts.identifiers import describe_external_identifiers, validate_external_identifiers
from catalog.services.person_resolution import _record, person_business_impact
from catalog.services.query_lexicon.mutations import acquire_entity_lock, acquire_generation_lock
from catalog.services.query_lexicon.normalization import normalize_term


class AuthorityConflict(APIException):
    status_code = 409
    default_detail = "人物资料或引用已变化，请重新读取并核对。"


FIELDS = ("preferred_name", "original_name", "birth_year", "death_year", "biography", "preferred_language",
          "original_language", "country_region", "authority_note", "external_ids", "identifier_sources", "authority_status")
VARIANT_FIELDS = ("name", "language", "variant_type", "source_note", "is_verified", "displayable")
ACTION = "person_authority_command"


def digest(value):
    return salted_hmac("stl4-person-authority", json.dumps(value, cls=DjangoJSONEncoder, ensure_ascii=False, sort_keys=True), algorithm="sha256").hexdigest()


def state(person):
    if person is None:
        return {"person": None, "variants": [], "contributions": [], "profiles": [], "drafts": []}
    profiles = list(ScholarProfile.objects.filter(person=person).values("id", "updated_at", "editorial_status"))
    return {"person": _record(person), "variants": list(person.name_variants.order_by("pk").values()),
        "contributions": list(person.contributions.order_by("pk").values("id", "edition_id", "role", "approved", "updated_at")),
        "profiles": profiles, "drafts": list(EditorialRevision.objects.filter(target_type="scholar_profile",
            target_id__in=[row["id"] for row in profiles], status="draft").order_by("pk").values("id", "updated_at"))}


def authority_rows(search="", status=""):
    rows = Person.objects.all()
    if search:
        rows = rows.filter(Q(preferred_name__icontains=search) | Q(original_name__icontains=search)
            | Q(name_variants__name__icontains=search)).distinct()
    if status:
        rows = rows.filter(authority_status=status)
    return rows.order_by("preferred_name", "pk")


def audit_rows(person_id):
    return AuditEvent.objects.filter(action=ACTION, object_type="catalog.Person", object_id=str(person_id)).order_by("-created_at", "-pk")


def detail(person, actor):
    snapshot = state(person)
    profile = ScholarProfile.objects.filter(person=person).first()
    edition_ids = list(person.contributions.order_by("edition_id").values_list("edition_id", flat=True).distinct()[:501])
    variants = [{"id": str(row["id"]), **{key: row[key] for key in VARIANT_FIELDS}, "source_kind": row["source_kind"]} for row in snapshot["variants"]]
    portrait_url, portrait_notice = "", ""
    if profile:
        from catalog.scholar_media_views import scholar_portrait_state
        try:
            portrait_state = scholar_portrait_state(profile)
            portrait_url = portrait_state["preview_url"]
            if portrait_state["canonical_write_deferred"]:
                portrait_notice = "此肖像来自学者编辑草稿，尚不代表公开页已更新。"
        except (ValueError, ModelValidationError):
            portrait_notice = "肖像的来源或编辑版本需要核对，请打开原学者编辑页处理。"
    elif person.portrait:
        portrait_url = person.portrait.url
    # A bibliography editor does not gain access to any reader's private records.
    return {"actor_id": str(actor.pk), "id": str(person.pk), "version": digest(snapshot),
        "updated_at": person.updated_at, "values": {key: getattr(person, key) for key in FIELDS}, "variants": variants,
        "identifiers": describe_external_identifiers(person.external_ids),
        "can_edit": has_capability(actor, Capability.EDIT_DRAFT_AUTHORITY) and person.authority_status not in {"merged", "archived", "rejected"},
        "can_verify": has_capability(actor, Capability.PUBLISH_AUTHORITY),
        "scholar_id": str(profile.pk) if profile else None,
        "portrait_url": portrait_url, "portrait_notice": portrait_notice,
        "public_url": f"/scholars/{profile.slug}" if profile and profile.editorial_status == "published" and person.authority_status == "verified" else "",
        "pending_draft": bool(snapshot["drafts"]), "impact": person_business_impact(edition_ids[:500], [person.pk]),
        "impact_complete": len(edition_ids) <= 500,
        "history": [{"id": str(row.pk), "created_at": row.created_at, "operation": row.after.get("operation", "update"),
            "reason": row.after.get("reason", ""), "fields": row.after.get("fields", []),
            "decision": row.after.get("decision", ""), "target_id": row.after.get("target_id"),
            "event_ids": row.after.get("event_ids", [])} for row in audit_rows(person.pk)[:20]]}


def prepare(actor, data, *, person=None, target=None):
    operation = data["operation"]
    if not has_capability(actor, Capability.EDIT_DRAFT_AUTHORITY):
        raise PermissionDenied("当前账户不能维护人物规范。")
    if operation == "create":
        if not has_capability(actor, Capability.CREATE_AUTHORITY):
            raise PermissionDenied("当前账户不能创建人物规范。")
        person = None
    elif person is None:
        person = get_object_or_404(Person, pk=data["person_id"])
    before = state(person)
    if person and digest(before) != data["expected_version"]:
        raise AuthorityConflict()
    if person and person.authority_status in {"merged", "archived", "rejected"}:
        raise AuthorityConflict("此人物已合并或退役，请先在原记录中处理。")
    if operation == "decision":
        target = target or get_object_or_404(Person, pk=data["target_id"])
        if target.pk == person.pk or target.authority_status in {"merged", "archived", "rejected"}:
            raise ValidationError("请选择另一个有效人物进行人工核对。")
        if digest(state(target)) != data["target_version"]:
            raise AuthorityConflict("比较人物已变化，请重新读取双方资料。")
        proposed, variants = None, []
        changes = ["人工身份核对"]
    else:
        if before["drafts"]:
            raise AuthorityConflict("关联学者有未完成的编辑草稿，请先在学者编辑页处理，避免覆盖不同版本的人物资料。")
        proposed = copy.copy(person) if person else Person()
        proposed._state = copy.copy(proposed._state)
        for key, value in data["values"].items():
            setattr(proposed, key, value)
        if proposed.authority_status == "verified" and not has_capability(actor, Capability.PUBLISH_AUTHORITY):
            raise PermissionDenied("核验或更改正式人物资料需要规范发布权限。")
        if person and person.authority_status == "verified" and proposed.authority_status != "verified":
            raise ValidationError("正式人物不能通过普通保存退回草稿，请使用原退役与恢复流程。")
        try:
            proposed.external_ids = validate_external_identifiers(proposed.external_ids, previous=person.external_ids if person else {})
            proposed.full_clean(validate_unique=False, validate_constraints=False)
            proposed.prepare_query_lexicon_bulk_object()
        except (ValueError, ModelValidationError) as error:
            raise ValidationError(str(error)) from error
        if set(proposed.identifier_sources) - set(proposed.external_ids):
            raise ValidationError("来源记录必须对应当前外部标识。")
        old_ids = person.external_ids if person else {}
        for key, value in proposed.external_ids.items():
            if key not in old_ids or value != old_ids[key]:
                if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).strip() or len(str(value)) > 500:
                    raise ValidationError("新增或修改的外部标识须是500字以内的有效文本或数字。")
                if not str(proposed.identifier_sources.get(key, "")).strip():
                    raise ValidationError("新增或修改外部标识时请记录来源依据。")
        previous = {str(row["id"]): row for row in before["variants"]}
        variants, names, identifiers = [], set(), set()
        for item in data["variants"]:
            row = dict(item)
            existing = previous.get(str(row.get("id", "")))
            if row.get("id") and existing is None:
                raise ValidationError("异名不属于当前人物或已不存在。")
            if row.get("id"):
                if str(row["id"]) in identifiers:
                    raise ValidationError("同一条异名记录不能重复提交。")
                identifiers.add(str(row["id"]))
            normalized = normalize_term(row["name"])
            if not normalized or normalized in names:
                raise ValidationError("异名不能为空或重复。")
            names.add(normalized)
            if any(old["normalized_name"] == normalized and str(old["id"]) != str(row.get("id", "")) for old in previous.values()):
                raise ValidationError("此异名已由另一条原记录保存，请编辑原异名，不能覆盖或交换原始身份。")
            if row["displayable"] and not row["is_verified"]:
                raise ValidationError("公开显示的异名必须经过人工核验。")
            changed = existing is None or any(existing[key] != row[key] for key in VARIANT_FIELDS)
            if changed and row["is_verified"] and not row["source_note"].strip():
                raise ValidationError("核验异名时请填写来源与判断依据。")
            if changed and row["is_verified"] and not has_capability(actor, Capability.PUBLISH_AUTHORITY):
                raise PermissionDenied("确认异名需要规范发布权限。")
            row.update(normalized_name=normalized, changed=changed)
            variants.append(row)
        # Missing rows cannot silently erase previous authority evidence.
        if set(previous) != {str(row["id"]) for row in variants if row.get("id")}:
            raise ValidationError("原异名不可省略删除。停用时取消核验和公开，并说明理由。")
        changes = [key for key in FIELDS if person is None or getattr(person, key) != getattr(proposed, key)]
        if any(row["changed"] for row in variants):
            changes.append("name_variants")
        if not changes:
            raise ValidationError("没有需要保存的变更。")
    editions = sorted({str(row["edition_id"]) for row in before["contributions"]})
    if len(editions) > 500:
        raise AuthorityConflict("关联版本超过500，请先通过书目维护流程缩小本次影响。")
    projection = {"actor_id": str(actor.pk), "person_id": str(person.pk) if person else None,
        "fields": changes, "edition_count": len(editions), "profile_count": len(before["profiles"]),
        "public_update": operation != "decision" and proposed.authority_status == "verified" and bool(set(changes) - {"authority_note", "identifier_sources"}),
        "reason": data["reason"], "decision": data.get("decision", ""),
        "before": {key: getattr(person, key) for key in FIELDS} if person else None,
        "after": {key: getattr(proposed, key) for key in FIELDS} if proposed else None,
        "variant_changes": [{
            "before": {key: previous[str(row["id"])][key] for key in VARIANT_FIELDS} if row.get("id") else None,
            "after": {key: row[key] for key in VARIANT_FIELDS},
        } for row in variants if row["changed"]] if operation != "decision" else []}
    request = {key: value for key, value in data.items() if key not in {"request_id", "confirmed", "preview_hash"}}
    projection["preview_hash"] = digest({"actor": actor.pk, "request": request, "before": before,
        "target": state(target) if target else None, "projection": projection})
    return projection, person, proposed, variants, editions


def receipt(actor, request_id):
    row = get_object_or_404(AuditEvent, pk=request_id, actor=actor, action=ACTION)
    return {"actor_id": str(actor.pk), "request_id": str(row.pk), "person_id": row.object_id,
        "created_at": row.created_at, "operation": row.after["operation"], "event_ids": row.after.get("event_ids", [])}


@transaction.atomic
def command(actor, data):
    original_token = actor.token_version
    actor = get_object_or_404(User.objects.select_for_update(), pk=actor.pk, is_active=True)
    if actor.token_version != original_token:
        raise PermissionDenied("账户会话已变化，请重新登录。")
    if not has_capability(actor, Capability.EDIT_DRAFT_AUTHORITY):
        raise PermissionDenied("账户权限已变化，请重新登录。")
    acquire_generation_lock(shared=True)
    acquire_entity_lock("person_authority_request", data["request_id"])
    fingerprint = digest(data)
    prior = AuditEvent.objects.filter(pk=data["request_id"]).first()
    if prior:
        if prior.action != ACTION or prior.actor_id != actor.pk or prior.after.get("fingerprint") != fingerprint:
            raise AuthorityConflict("本次请求编号已用于不同操作。")
        return receipt(actor, prior.pk)
    if data["confirmed"] is not True:
        raise ValidationError("请先核对变化与影响并明确确认。")
    ids = [data[key] for key in ("person_id", "target_id") if data.get(key)]
    locked = {str(row.pk): row for row in Person.objects.select_for_update().filter(pk__in=ids).order_by("pk")}
    if len(locked) != len(set(ids)):
        raise AuthorityConflict("人物已不存在。")
    current = locked.get(str(data.get("person_id")))
    if current:
        list(current.name_variants.select_for_update().order_by("pk"))
        list(current.contributions.select_for_update().order_by("pk"))
        list(ScholarProfile.objects.select_for_update().filter(person=current).order_by("pk"))
    preview, current, proposed, variants, editions = prepare(actor, data, person=current, target=locked.get(str(data.get("target_id"))))
    if preview["preview_hash"] != data["preview_hash"]:
        raise AuthorityConflict("预览内容已变化，请重新确认。")
    before_variants = list(current.name_variants.order_by("pk").values()) if current else []
    events = []
    if proposed:
        proposed.save()
        for item in variants:
            if item["changed"]:
                variant = PersonNameVariant.objects.get(pk=item["id"], person=proposed) if item.get("id") else PersonNameVariant(person=proposed, pk=uuid4())
                for key in VARIANT_FIELDS:
                    setattr(variant, key, item[key])
                variant.created_by = actor
                variant.source_kind = "editorial"
                variant.save()
        if preview["public_update"]:
            from catalog.services.knowledge_publication import create_entity_publication_event, create_catalog_publication_event
            event = create_entity_publication_event(object_type="person", object_id=proposed.pk, event_type="entity_updated",
                changed_fields=preview["fields"], actor=actor, idempotency_key=f"person-authority:{data['request_id']}",
                provenance={"source": "person_authority", "request_id": str(data["request_id"])})
            events.append(str(event.pk))
            for edition in Edition.objects.filter(pk__in=editions, state="published").order_by("pk"):
                event = create_catalog_publication_event(edition, event_type="catalog_updated", changed_fields=["contributors"],
                    actor=actor, idempotency_key=f"person-authority:{data['request_id']}:{edition.pk}",
                    provenance={"source": "person_authority", "request_id": str(data["request_id"])})
                events.append(str(event.pk))
        current = proposed
    AuditEvent.objects.create(pk=data["request_id"], actor=actor, action=ACTION, object_type="catalog.Person", object_id=str(current.pk),
        before={"values": preview["before"], "variants": json.loads(json.dumps(before_variants, cls=DjangoJSONEncoder))}, after={"fingerprint": fingerprint, "operation": data["operation"],
            "fields": preview["fields"], "values": preview["after"], "variants": json.loads(json.dumps(variants, cls=DjangoJSONEncoder)),
            "expected_version": data.get("expected_version"), "target_version": data.get("target_version"),
            "reason": data["reason"], "decision": data.get("decision", ""), "target_id": str(data["target_id"]) if data.get("target_id") else None,
            "event_ids": events})
    return receipt(actor, data["request_id"])
