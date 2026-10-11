"""Saved home selections reuse editorial revisions; policy/snapshots stay unchanged."""
from django.db import transaction
from rest_framework.exceptions import APIException, ValidationError

from catalog.models import EditorialRevision
from ingestion.models import AuditEvent


class SelectionConflict(APIException):
    status_code = 409
    default_detail = "草稿或当前推荐已变化。当前输入已保留，请重新读取并核对后再保存。"


def latest_selection_revision(policy):
    return EditorialRevision.objects.filter(target_type="recommendation_policy", target_id=policy.pk).order_by("-revision").first()


def selection_version(revision):
    return str(revision.pk) if revision else "none"


def selection_state(policy):
    from catalog.knowledge_views import _resolve_manual_target
    from catalog.serializers import PersonCompactSerializer, TopicSerializer, WorkCardSerializer

    latest = latest_selection_revision(policy)
    draft = latest if latest and latest.status == "draft" else None
    current = policy.snapshots.filter(is_current=True).first()
    items = []
    for row in (draft.materialized_preview.get("items", []) if draft else []):
        target = _resolve_manual_target(row["target_type"], row["id"])
        if target is None:
            items.append({**row, "name": "内容已不可公开，请更换", "image_url": "", "available": False})
            continue
        if row["target_type"] == "scholar":
            name = target.person.preferred_name
            image = PersonCompactSerializer(target.person).data.get("portrait", "")
        elif row["target_type"] == "topic":
            name = target.name
            image = TopicSerializer(target).data.get("hero_image", "")
        else:
            name = target.title
            image = WorkCardSerializer(target).data.get("cover", "")
        items.append({**row, "name": name, "image_url": image or "", "available": True})
    return {"policy_id": str(policy.pk), "exists": bool(draft), "edit_version": selection_version(latest),
            "expected_updated_at": policy.updated_at, "expected_snapshot_id": str(current.pk) if current else None,
            "items": items, "public_unchanged": True}


@transaction.atomic
def save_selection(policy, data, actor):
    from catalog.knowledge_views import PLACEMENT_TARGETS, _resolve_manual_target

    clean = {"items": [{"id": str(row["id"]), "target_type": row["target_type"]} for row in data["items"]],
             "edit_version": data["edit_version"], "expected_updated_at": data["expected_updated_at"].isoformat(),
             "expected_snapshot_id": str(data["expected_snapshot_id"]) if data["expected_snapshot_id"] else None}
    key = f"home-selection:{actor.pk}:{data['request_key']}"
    receipt = EditorialRevision.objects.filter(idempotency_key=key).first()
    if receipt:
        if receipt.target_type != "recommendation_policy" or receipt.target_id != policy.pk or receipt.created_by_id != actor.pk or receipt.patch != clean:
            raise SelectionConflict("此请求编号已经用于其他选择，请重新读取并核对。")
        return selection_state(policy)
    latest = latest_selection_revision(policy)
    current = policy.snapshots.filter(is_current=True).first()
    if clean["edit_version"] != selection_version(latest) or data["expected_updated_at"] != policy.updated_at or clean["expected_snapshot_id"] != (str(current.pk) if current else None):
        raise SelectionConflict()
    if len(clean["items"]) > policy.item_count:
        raise ValidationError({"items": f"当前位置最多保存{policy.item_count}项。"})
    seen = set()
    for row in clean["items"]:
        if row["target_type"] != PLACEMENT_TARGETS.get(policy.placement) or row["id"] in seen or _resolve_manual_target(row["target_type"], row["id"]) is None:
            raise ValidationError({"items": "请选择当前位置的公开内容，不可重复或使用已撤回的对象。"})
        seen.add(row["id"])
    revision = EditorialRevision.objects.create(target_type="recommendation_policy", target_id=policy.pk,
        base_revision=latest.revision if latest else 0, revision=(latest.revision if latest else 0)+1,
        patch=clean, materialized_preview={"items": clean["items"]}, changed_fields=["home_selection"],
        idempotency_key=key, created_by=actor, change_note="保存首页选择与顺序，等待预览确认发布")
    EditorialRevision.objects.filter(target_type="recommendation_policy", target_id=policy.pk, status="draft").exclude(pk=revision.pk).update(status="superseded")
    AuditEvent.objects.create(actor=actor, action="recommendation_policy.save_draft", object_type="recommendation_policy",
                              object_id=str(policy.pk), after={"revision": revision.revision})
    return selection_state(policy)
