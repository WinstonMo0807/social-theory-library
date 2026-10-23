"""Recoverable decisions over the existing field assistant and authority services."""
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.core.exceptions import ObjectDoesNotExist
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from catalog.field_assistant_views import _FieldAssistantView, FieldAssistantCreateSerializer, FieldAssistantDecisionSerializer
from catalog.models import Edition, Work
from catalog.services.field_assistant import FieldAssistantError
from catalog.services.editorial_revision import EditorialRevisionConflict
from catalog.services.workspace_edits import _digest, workspace_edit_version
from catalog.services.work_editor import _json_safe
from catalog.services.editorial_issues import EditConflict
from catalog.editorial_issue_views import EditorialErrorMixin
from common.capabilities import Capability, has_capability
from ingestion.models import AuditEvent

ACTION = "field_assistant.command"


class AssistantCommandInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    expected_version = serializers.CharField(max_length=64)
    action = serializers.ChoiceField(choices=["adopt", "reject", "create"])
    field_name = serializers.CharField(max_length=80)
    payload = serializers.DictField()

    def validate_payload(self, value):
        import json
        if len(json.dumps(value, ensure_ascii=False).encode()) > 65536:
            raise serializers.ValidationError("单次字段决定内容过长，请分开核对。")
        return value


class AssistantStopInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=["cancel_pending"])


class AssistantReceipt(serializers.Serializer):
    owner_id = serializers.CharField()
    request_id = serializers.UUIDField()
    edition_id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    action = serializers.CharField(allow_blank=True)
    field_name = serializers.CharField(allow_blank=True)
    next_url = serializers.CharField(allow_blank=True)
    result = serializers.DictField()


def output(row):
    return {"owner_id": str(row.actor_id), "request_id": row.request_id, "edition_id": row.object_id,
            "state": row.after["state"], "action": row.after.get("action", ""), "field_name": row.after.get("field_name", ""),
            "next_url": "", "result": row.after.get("result", {})}


def existing(user, request_id):
    return AuditEvent.objects.filter(actor=user, action=ACTION, request_id=str(request_id)).first()


class AssistantCommandView(EditorialErrorMixin, _FieldAssistantView):
    @extend_schema(request=AssistantCommandInput, responses=AssistantReceipt)
    @transaction.atomic
    def post(self, request, edition_id):
        self.lock_actor(request)
        data = AssistantCommandInput(data=request.data); data.is_valid(raise_exception=True); data = data.validated_data
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("登录账户已变化，请重新读取当前资料。")
        fingerprint = _digest(data)
        prior = existing(request.user, data["request_id"])
        if prior:
            if prior.object_id != str(edition_id) or prior.after["state"] != "applied" or prior.after.get("fingerprint") != fingerprint:
                raise EditConflict("原决定已停止或内容不匹配，请先查回原结果。")
            return Response(output(prior))
        # Match the assistant's run -> Edition -> Work lock order for adopted enrichment.
        if data["action"] == "adopt" and data["payload"].get("source_type") == "enrichment":
            from catalog.models import EnrichmentCandidate, ResearchRun
            source_id = serializers.UUIDField().run_validation(data["payload"].get("source_id"))
            context = EnrichmentCandidate.objects.filter(pk=source_id).values_list("request_context", flat=True).first() or {}
            if context.get("research_run_id"):
                list(ResearchRun.objects.select_for_update().filter(pk=context["research_run_id"]).order_by("pk"))
        edition = get_object_or_404(Edition.objects.select_for_update(), pk=edition_id)
        edition.work = Work.objects.select_for_update().get(pk=edition.work_id)
        if workspace_edit_version(edition) != data["expected_version"]:
            raise EditConflict("书目或人工锁已经变化，请重新读取候选后决定。")
        if data["field_name"] in {"theory", "topic"} and not has_capability(request.user, Capability.EDIT_DRAFT_AUTHORITY):
            raise PermissionDenied("当前账户不能更改关联知识的候选决定。")
        values = {**data["payload"], "edition_id": edition.pk, "field_name": data["field_name"]}
        try:
            if data["action"] == "create":
                if not has_capability(request.user, Capability.CREATE_AUTHORITY):
                    raise PermissionDenied("当前账户不能新建人物或知识草稿。")
                check = FieldAssistantCreateSerializer(data={**values, "request_id": data["request_id"]})
                check.is_valid(raise_exception=True)
                result = self.service.create_and_link(actor=request.user, **check.validated_data)
            else:
                check = FieldAssistantDecisionSerializer(data=values); check.is_valid(raise_exception=True)
                values = dict(check.validated_data)
                if data["action"] == "reject": values.pop("selected_value", None)
                result = getattr(self.service, data["action"])(actor=request.user, **values)
        except EditorialRevisionConflict as error:
            raise EditConflict(str(error)) from error
        except ObjectDoesNotExist as error:
            raise NotFound("所选来源或对象已变化，请重新读取候选。") from error
        except (FieldAssistantError, ValueError) as error:
            raise ValidationError(str(error)) from error
        row = AuditEvent.objects.create(actor=request.user, action=ACTION, object_type="catalog.Edition", object_id=str(edition.pk),
            request_id=str(data["request_id"]), after={"state": "applied", "fingerprint": fingerprint,
                "action": data["action"], "field_name": data["field_name"], "result": _json_safe(result)})
        return Response(output(row))


class AssistantReceiptView(EditorialErrorMixin, _FieldAssistantView):
    @extend_schema(responses=AssistantReceipt)
    def get(self, request, edition_id, request_id):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk): raise PermissionDenied("登录账户已变化。")
        row = existing(request.user, request_id)
        if row is None or row.object_id != str(edition_id): raise NotFound("尚未找到本人的原决定，请稍后查回或停止尚未执行的请求。")
        return Response(output(row))

    @extend_schema(request=AssistantStopInput, responses=AssistantReceipt)
    @transaction.atomic
    def post(self, request, edition_id, request_id):
        self.lock_actor(request)
        if request.headers.get("X-Editor-Owner") != str(request.user.pk): raise PermissionDenied("登录账户已变化。")
        if request.data != {"action":"cancel_pending"}: raise ValidationError("仅接受停止尚未执行的原决定。")
        row = existing(request.user, request_id)
        if row and row.object_id != str(edition_id): raise EditConflict("原请求属于另一个出版版本。")
        if not row:
            get_object_or_404(Edition, pk=edition_id)
            row = AuditEvent.objects.create(actor=request.user, action=ACTION, object_type="catalog.Edition", object_id=str(edition_id),
                                           request_id=str(request_id), after={"state":"cancelled"})
        return Response(output(row))
