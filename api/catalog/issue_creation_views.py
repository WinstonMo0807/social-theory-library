"""Recoverable creation of an ungrouped article using the existing issue service."""
from hashlib import sha256
import json

from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_issue_views import EditorialErrorMixin
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.services.curation_projects import visible_issues
from catalog.services.editorial_issues import EditConflict, create_issue
from catalog.workspace_receipt_views import actor_for
from common.permissions import CanEditMetadata
from ingestion.models import AuditEvent

ACTION = "recommendation_issue.create_command"


class IssueCreateCommandSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    title = serializers.CharField(max_length=600)
    kind = serializers.ChoiceField(choices=["article", "research", "exhibition"])

    def validate(self, value):
        if set(self.initial_data) != set(self.fields):
            raise serializers.ValidationError("新建文章只接受标题、类型和原请求编号。")
        return value


class IssueCreateReceiptSerializer(serializers.Serializer):
    owner_id = serializers.CharField()
    request_id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    next_url = serializers.CharField(allow_blank=True)
    issue_id = serializers.UUIDField(allow_null=True)
    available = serializers.BooleanField()


class IssueCreateStopSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["cancel_pending"])


def receipt(row, actor):
    issue_id = row.after.get("issue_id")
    # An accepted creation can later be recycled or moved to another team.
    # Report completion without exposing its current identity or blocking new work.
    available = bool(issue_id and visible_issues(actor).filter(pk=issue_id).exists())
    if not available:
        issue_id = None
    return {"owner_id": str(row.actor_id), "request_id": row.request_id,
        "state": "cancelled" if row.after.get("cancelled") else "applied", "issue_id": issue_id,
        "next_url": f"/admin/recommendations/issues/{issue_id}" if issue_id else "", "available": available}


class IssueCreateView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    @extend_schema(request=IssueCreateCommandSerializer, responses=IssueCreateReceiptSerializer)
    @transaction.atomic
    def post(self, request):
        actor = actor_for(request, True)
        check = IssueCreateCommandSerializer(data=request.data)
        check.is_valid(raise_exception=True)
        data = check.validated_data
        signature = sha256(json.dumps(data, default=str, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        row = AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(data["request_id"])).first()
        if row:
            if not row.after.get("cancelled") and row.after.get("signature") != signature:
                raise EditConflict("原请求编号已用于另一篇文章，请先查回创建结果。")
            return Response(receipt(row, actor))
        issue = create_issue({"title": data["title"], "article_metadata": {"kind": data["kind"]}}, actor)
        row = AuditEvent.objects.create(actor=actor, action=ACTION, object_type="RecommendationIssue", object_id=str(issue.pk),
            request_id=str(data["request_id"]), after={"signature": signature, "issue_id": str(issue.pk)})
        return Response(receipt(row, actor), status=201)


class IssueCreateReceiptView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    @extend_schema(responses=IssueCreateReceiptSerializer)
    def get(self, request, request_id):
        actor = actor_for(request)
        row = get_object_or_404(AuditEvent, actor=actor, action=ACTION, request_id=str(request_id))
        return Response(receipt(row, actor))

    @extend_schema(request=IssueCreateStopSerializer, responses=IssueCreateReceiptSerializer)
    @transaction.atomic
    def post(self, request, request_id):
        actor = actor_for(request, True)
        if request.data != {"action": "cancel_pending"}:
            raise ValidationError("仅接受停止尚未执行的原请求。")
        row = AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(request_id)).first()
        if not row:
            row = AuditEvent.objects.create(actor=actor, action=ACTION, object_type="RecommendationIssue", object_id="",
                request_id=str(request_id), after={"cancelled": True})
        return Response(receipt(row, actor))
