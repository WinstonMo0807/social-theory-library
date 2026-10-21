"""Owner-locked graph commands with encrypted controls and durable nonce receipts."""
import json

from django.db import transaction
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from . import privacy, research
from .graph_models import GraphViewReceipt, SavedGraphView
from .graph_serializers import GraphViewCreateInput, GraphViewDeleteInput, GraphViewUpdateInput


def validated(raw, schema):
    if not hasattr(raw, "items") or len(json.dumps(dict(raw), ensure_ascii=False, default=str)) > 20_000:
        raise ValidationError("保存图谱需要对象，且内容不能超过20000字符。")
    serializer = schema(data=raw)
    serializer.is_valid(raise_exception=True)
    return json.loads(json.dumps(serializer.validated_data, default=str))


def validate_identities(data, previous=None):
    from catalog.services.theory_graph import entity_querysets, graph_options, public_graph_edge
    view, old = data["view"], (previous or {}).get("view", {})
    entities = entity_querysets(graph_options({}))
    same_center = (view["center_kind"], view["center"]) == (old.get("center_kind"), old.get("center"))
    if not same_center and not entities[view["center_kind"]].filter(pk=view["center"]).exists():
        raise ValidationError({"center": "图谱中心当前不可公开读取，请重新选择。"})
    if view["selected_node"] and view["selected_node"] != old.get("selected_node"):
        kind, identifier = view["selected_node"].split(":", 1)
        if not entities[kind].filter(pk=identifier).exists():
            raise ValidationError({"selected_node": "选中节点当前不可公开读取。"})
    if view["selected_edge"] and view["selected_edge"] != old.get("selected_edge"):
        if public_graph_edge(view["selected_edge"]) is None:
            raise ValidationError({"selected_edge": "只能保存当前已公开的关系，不能保存审核候选。"})
    return data


def record_output(record, user):
    if record.user_id != user.pk:
        raise PermissionDenied("只能读取本人的图谱视图。")
    # A stored identity is navigation state, never a grant to read its source.
    # The graph endpoint rechecks all current publication rules on restoration.
    return {"id": str(record.pk), "revision": record.revision,
        "created_at": record.created_at.isoformat(), "updated_at": record.updated_at.isoformat(),
        "data": research.unpack(record)}


def command_output(user, *, record=None, receipt=None):
    if receipt is not None:
        if receipt.user_id != user.pk:
            raise PermissionDenied("只能读取本人的保存回执。")
        record = receipt.record
    return {"owner_id": str(user.pk), "record": record_output(record, user) if record else None,
        "receipt": {"request_id": str(receipt.request_id), "applied_revision": receipt.applied_revision,
                    "deleted": record is None} if receipt else None}


def existing_receipt(user, request_id, digest):
    receipt = GraphViewReceipt.objects.select_related("record").filter(user=user, request_id=request_id).first()
    if receipt and receipt.fingerprint != digest:
        raise research.ResearchConflict("原请求已用于不同内容，请先核对保存回执。")
    return receipt


def by_request(user, request_id):
    receipt = GraphViewReceipt.objects.select_related("record").filter(
        user=user, request_id=research.identifier(request_id, "request_id")).first()
    if receipt is None:
        raise NotFound("未找到本人的该次图谱保存回执，可使用原请求标识重试。")
    return command_output(user, receipt=receipt)


@transaction.atomic
def create_view(user, raw):
    command = validated(raw, GraphViewCreateInput)
    privacy.lock_owner(user)
    fingerprint = research.request_fingerprint({"action": "create", **command}, ("action", "request_id", "data"))
    receipt = existing_receipt(user, command["request_id"], fingerprint)
    if receipt:
        return command_output(user, receipt=receipt)
    privacy.require_retention(user, "saved_knowledge")
    data = validate_identities(command["data"])
    record = SavedGraphView.objects.create(user=user, request_id=command["request_id"], data_ciphertext=research.pack(data))
    receipt = GraphViewReceipt.objects.create(user=user, record=record, request_id=command["request_id"],
        fingerprint=fingerprint, applied_revision=record.revision)
    return command_output(user, receipt=receipt)


@transaction.atomic
def update_view(user, pk, raw):
    command = validated(raw, GraphViewUpdateInput)
    pk = research.identifier(pk)
    privacy.lock_owner(user)
    payload = {"action": "update", "record_id": pk, **command}
    fingerprint = research.request_fingerprint(payload, payload.keys())
    receipt = existing_receipt(user, command["request_id"], fingerprint)
    if receipt:
        return command_output(user, receipt=receipt)
    record = research.owned(SavedGraphView, user, pk, lock=True)
    privacy.require_retention(user, "saved_knowledge")
    research.expect(record, command["expected_revision"])
    data = validate_identities(command["data"], previous=research.unpack(record))
    research.save_data(record, data)
    receipt = GraphViewReceipt.objects.create(user=user, record=record, request_id=command["request_id"],
        fingerprint=fingerprint, applied_revision=record.revision)
    return command_output(user, receipt=receipt)


@transaction.atomic
def delete_view(user, pk, raw):
    command = validated(raw, GraphViewDeleteInput)
    pk = research.identifier(pk)
    privacy.lock_owner(user)
    payload = {"action": "delete", "record_id": pk, **command}
    fingerprint = research.request_fingerprint(payload, payload.keys())
    receipt = existing_receipt(user, command["request_id"], fingerprint)
    if receipt:
        return command_output(user, receipt=receipt)
    record = research.owned(SavedGraphView, user, pk, lock=True)
    research.expect(record, command["expected_revision"])
    revision = record.revision + 1
    record.delete()
    receipt = GraphViewReceipt.objects.create(user=user, request_id=command["request_id"],
        fingerprint=fingerprint, applied_revision=revision)
    return command_output(user, receipt=receipt)
