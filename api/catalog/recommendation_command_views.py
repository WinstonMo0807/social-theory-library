"""Look up or stop the original homepage publication; never republish on lookup."""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import RecommendationPolicy
from catalog.serializers import RecommendationPolicySerializer, RecommendationSnapshotSerializer
from common.capabilities import Capability, has_capability
from common.permissions import CanPublishAuthority
from ingestion.models import AuditEvent

ACTION = "catalog.recommendations_published"


def publication_actor(request):
    owner = request.headers.get("X-Editor-Owner")
    if owner is not None and owner != str(request.user.pk):
        raise PermissionDenied("登录账户已变化，请重新读取当前账户的工作。")
    actor = get_object_or_404(get_user_model().objects.select_for_update(), pk=request.user.pk, is_active=True)
    if actor.token_version != request.user.token_version or not has_capability(actor, Capability.PUBLISH_AUTHORITY):
        raise PermissionDenied("当前会话不能发布首页推荐。")
    return actor


def command_record(policy, request_id):
    # Keep receipts written by the previous refresh endpoint readable.
    return AuditEvent.objects.filter(action=ACTION, object_type="catalog.RecommendationPolicy",
        object_id=str(policy.pk)).filter(Q(request_id=str(request_id)) | Q(after__request_key=str(request_id)))


def publication_result(request, policy, row, *, replayed=True):
    current = policy.snapshots.filter(is_current=True).first()
    policy.resolved_snapshot = current
    data = dict(RecommendationPolicySerializer(policy, context={"request": request}).data)
    cancelled = bool(row.after.get("cancelled"))
    data.update(owner_id=str(row.actor_id), request_id=row.request_id or row.after["request_key"],
        state="cancelled" if cancelled else "applied", next_url="", command_accepted=not cancelled,
        replayed=replayed, accepted_snapshot_id=row.after.get("snapshot_id"), audit_id=str(row.pk),
        publication_effective=bool(not cancelled and policy.enabled and current
            and str(current.pk) == row.after.get("snapshot_id")
            and current.starts_at <= timezone.now() < current.expires_at))
    return data


class RecommendationRefreshCommandSerializer(serializers.Serializer):
    request_id = serializers.UUIDField(required=False)
    request_key = serializers.UUIDField(required=False)
    confirm = serializers.BooleanField()
    expected_snapshot_id = serializers.UUIDField(allow_null=True)
    expected_updated_at = serializers.DateTimeField()
    preview_token = serializers.CharField(required=False)
    items = serializers.ListField(child=serializers.DictField(), required=False)


class RecommendationPublishedItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    position = serializers.IntegerField()
    reason = serializers.CharField()
    image_override = serializers.CharField(allow_blank=True)
    target_type = serializers.CharField()
    target = serializers.JSONField()


class RecommendationPublishedSnapshotSerializer(RecommendationSnapshotSerializer):
    @extend_schema_field(RecommendationPublishedItemSerializer(many=True))
    def get_items(self, obj):
        return super().get_items(obj)


class RecommendationRefreshReceiptSerializer(RecommendationPolicySerializer):
    owner_id = serializers.CharField()
    request_id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    next_url = serializers.CharField(allow_blank=True)
    command_accepted = serializers.BooleanField()
    replayed = serializers.BooleanField()
    accepted_snapshot_id = serializers.UUIDField(allow_null=True)
    audit_id = serializers.UUIDField()
    publication_effective = serializers.BooleanField()

    @extend_schema_field(RecommendationPublishedSnapshotSerializer(allow_null=True))
    def get_current(self, obj):
        return super().get_current(obj)

    class Meta(RecommendationPolicySerializer.Meta):
        fields = (*RecommendationPolicySerializer.Meta.fields, "owner_id", "request_id", "state", "next_url",
            "command_accepted", "replayed", "accepted_snapshot_id", "audit_id", "publication_effective")


class RecommendationRefreshStopSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["cancel_pending"])


class RecommendationRefreshReceiptView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanPublishAuthority]

    def owner(self, request):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("请从当前账户的首页编排查回原请求。")

    @extend_schema(responses=RecommendationRefreshReceiptSerializer)
    def get(self, request, placement, request_id):
        self.owner(request)
        policy = get_object_or_404(RecommendationPolicy, placement=placement)
        row = get_object_or_404(command_record(policy, request_id), actor=request.user)
        return Response(publication_result(request, policy, row))

    @extend_schema(request=RecommendationRefreshStopSerializer, responses=RecommendationRefreshReceiptSerializer)
    @transaction.atomic
    def post(self, request, placement, request_id):
        self.owner(request)
        actor = publication_actor(request)
        if request.data != {"action": "cancel_pending"}:
            raise ValidationError("仅接受停止尚未执行的原发布请求。")
        policy = get_object_or_404(RecommendationPolicy.objects.select_for_update(), placement=placement)
        row = command_record(policy, request_id).first()
        if row and row.actor_id != actor.pk:
            raise PermissionDenied("此请求不属于当前账户。")
        if not row:
            row = AuditEvent.objects.create(actor=actor, action=ACTION, object_type="catalog.RecommendationPolicy",
                object_id=str(policy.pk), request_id=str(request_id),
                after={"request_key": str(request_id), "placement": placement, "cancelled": True})
        return Response(publication_result(request, policy, row))
