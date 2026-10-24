"""One owner-bound receipt for a knowledge/claim candidate decision; no new store."""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.editorial_issue_views import EditorialErrorMixin
from catalog.field_assistant_commands import AssistantStopInput
from catalog.models import DerivedClaim, EnrichmentCandidate, ResearchRun, ScholarProfile
from catalog.services.claims.curation import decide_claim_curation_candidate, _candidate_kind
from catalog.services.curation_decisions import decision_version
from catalog.services.editorial_issues import EditConflict
from catalog.services.field_enrichment.mutations import accept_enrichment_candidate, reject_enrichment_candidate
from catalog.services.field_enrichment.targets import TARGET_MODELS, get_target
from catalog.services.workspace_edits import _digest
from common.capabilities import Capability, has_capability
from common.permissions import CanReviewCandidate
from ingestion.models import AuditEvent

ACTION = "curation_assistant.command"


class CurationDecisionInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    expected_version = serializers.CharField(max_length=64)
    field_name = serializers.CharField(max_length=80)
    source_type = serializers.ChoiceField(choices=["enrichment", "claim"])
    source_id = serializers.UUIDField()
    action = serializers.ChoiceField(choices=["accept", "accept_with_edit", "reject"])
    proposition = serializers.CharField(required=False, allow_blank=True, max_length=30000, default="")
    reason = serializers.CharField(required=False, allow_blank=True, max_length=4000, default="")

    def validate(self, attrs):
        if attrs["source_type"] != "claim" and (attrs["action"] == "accept_with_edit" or attrs["proposition"]):
            raise serializers.ValidationError("只有原文观点支持修改后采用，其他建议请在表单核对。")
        if attrs["action"] == "accept_with_edit" and not attrs["proposition"]:
            raise serializers.ValidationError("请填写修改后的观点。")
        if attrs["action"] == "reject" and not attrs["reason"]:
            raise serializers.ValidationError("请说明本次不采用的原因。")
        return attrs


class CurationDecisionReceipt(serializers.Serializer):
    owner_id = serializers.CharField()
    request_id = serializers.UUIDField()
    target_type = serializers.CharField()
    target_id = serializers.UUIDField()
    field_name = serializers.CharField(allow_blank=True)
    source_id = serializers.CharField(allow_blank=True)
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    action = serializers.CharField(allow_blank=True)
    next_url = serializers.CharField(allow_blank=True)
    result = serializers.DictField()


def output(row):
    return {"owner_id": str(row.actor_id), "request_id": row.request_id,
        "target_type": row.after["target_type"], "target_id": row.object_id,
        "field_name": row.after.get("field_name", ""), "source_id": row.after.get("source_id", ""),
        "state": row.after["state"], "action": row.after.get("action", ""),
        "next_url": "", "result": row.after.get("result", {})}


def existing(actor, request_id):
    return AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(request_id)).first()


class CurationDecisionBase(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanReviewCandidate]

    def actor(self, request, target_type, *, lock=False):
        if target_type not in TARGET_MODELS:
            raise NotFound("不支持的编辑对象。")
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("账户已变化，请重新读取当前资料。")
        actor = request.user
        if lock:
            actor = get_user_model().objects.select_for_update().filter(pk=actor.pk, is_active=True).first()
        capability = Capability.EDIT_METADATA if target_type in {"work", "edition"} else Capability.EDIT_DRAFT_AUTHORITY
        if not actor or not actor.is_active or actor.token_version != request.user.token_version or not all(
                has_capability(actor, item) for item in (capability, Capability.REVIEW_CANDIDATE)):
            raise PermissionDenied("当前账户不能处理此类候选，请核对登录状态与编辑权限。")
        request.user = actor
        return actor


class CurationDecisionView(CurationDecisionBase):
    @extend_schema(request=CurationDecisionInput, responses=CurationDecisionReceipt)
    @transaction.atomic
    def post(self, request, target_type, target_id):
        actor = self.actor(request, target_type, lock=True)
        check = CurationDecisionInput(data=request.data); check.is_valid(raise_exception=True)
        data = check.validated_data
        fingerprint = _digest({**data, "target_type": target_type, "target_id": target_id})
        prior = existing(actor, data["request_id"])
        if prior:
            if prior.object_id != str(target_id) or prior.after["target_type"] != target_type or prior.after["state"] != "applied" or prior.after.get("fingerprint") != fingerprint:
                raise EditConflict("原请求已停止或内容不同，请先查回原决定。")
            return Response(output(prior))
        try:
            if data["source_type"] == "enrichment":
                candidate = get_object_or_404(EnrichmentCandidate, pk=data["source_id"], target_type=target_type,
                                               target_id=target_id, field_name=data["field_name"])
                # Preserve ResearchRun -> candidate -> target order of the original service.
                run_id = (candidate.request_context or {}).get("research_run_id")
                if run_id:
                    list(ResearchRun.objects.select_for_update(of=("self",)).filter(pk=run_id))
                candidate = EnrichmentCandidate.objects.select_for_update().get(pk=candidate.pk)
                if (candidate.request_context or {}).get("research_run_id") != run_id:
                    raise EditConflict("建议来源已变化，请重新读取。")
                if candidate.target_type != target_type or candidate.target_id != target_id or candidate.field_name != data["field_name"]:
                    raise EditConflict("建议所属对象已变化，请重新读取。")
            elif target_type != "work" or data["field_name"] not in {"core_viewpoint", "major_criticism", "major_response"}:
                raise ValidationError("原文观点须属于当前作品的对应字段。")
            target = get_target(target_type, target_id, for_update=True)
            if target_type == "person":
                list(ScholarProfile.objects.select_for_update().filter(person=target))
            if decision_version(target_type, target, data["field_name"]) != data["expected_version"]:
                raise EditConflict("已保存内容或草稿已经变化，请重新读取后再决定。")
            if data["source_type"] == "claim":
                claim = get_object_or_404(DerivedClaim.objects.select_for_update(), pk=data["source_id"], work=target)
                if _candidate_kind(claim) != data["field_name"]:
                    raise ValidationError("观点候选不属于当前字段，请重新核对。")
                curated = decide_claim_curation_candidate(work=target, claim=claim, decision=data["action"], actor=actor,
                    proposition=data["proposition"], editorial_note=data["reason"], kind=data["field_name"])
                result = {"curated_claim_id": str(curated.pk) if curated else ""}
            else:
                if data["action"] == "reject":
                    reject_enrichment_candidate(candidate, actor=actor, reason=data["reason"])
                    result = {}
                else:
                    mutation = accept_enrichment_candidate(candidate, actor=actor, reason=data["reason"])
                    result = {"authority_model": mutation.authority_model, "authority_id": str(mutation.authority_id)}
        except ObjectDoesNotExist as error:
            raise NotFound("所选来源或对象已变化，请重新读取候选。") from error
        except ValueError as error:
            raise EditConflict(str(error)) from error
        row = AuditEvent.objects.create(actor=actor, action=ACTION, object_type=target._meta.label, object_id=str(target.pk),
            request_id=str(data["request_id"]), after={"target_type": target_type, "state": "applied", "fingerprint": fingerprint,
                "action": data["action"], "field_name": data["field_name"], "source_id": str(data["source_id"]), "result": result})
        return Response(output(row))


class CurationDecisionReceiptView(CurationDecisionBase):
    @extend_schema(responses=CurationDecisionReceipt)
    def get(self, request, target_type, target_id, request_id):
        actor = self.actor(request, target_type)
        row = existing(actor, request_id)
        if row is None or row.object_id != str(target_id) or row.after["target_type"] != target_type:
            raise NotFound("尚未找到本人的原决定，请稍后查回或停止尚未执行的请求。")
        return Response(output(row))

    @extend_schema(request=AssistantStopInput, responses=CurationDecisionReceipt)
    @transaction.atomic
    def post(self, request, target_type, target_id, request_id):
        actor = self.actor(request, target_type, lock=True)
        if request.data != {"action": "cancel_pending"}:
            raise ValidationError("仅接受停止尚未执行的原决定。")
        row = existing(actor, request_id)
        if row and (row.object_id != str(target_id) or row.after["target_type"] != target_type):
            raise EditConflict("原请求属于另一个对象。")
        if not row:
            # A removed target can still have a delayed request. The tombstone is owner-scoped.
            row = AuditEvent.objects.create(actor=actor, action=ACTION, object_type=TARGET_MODELS[target_type]._meta.label,
                object_id=str(target_id), request_id=str(request_id), after={"target_type": target_type, "state": "cancelled"})
        return Response(output(row))
