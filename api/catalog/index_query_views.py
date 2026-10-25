"""A recoverable start for the original Discovery query, without another index."""
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
from catalog.index_maintenance_views import IndexMaintenanceStopSerializer, locked_actor
from catalog.services.discovery_sessions import create_session, normalize_filters
from catalog.services.editorial_issues import EditConflict
from common.capabilities import Capability
from common.permissions import IsLibraryStaff
from ingestion.models import AuditEvent

ACTION = "index.query.preview"


class IndexQueryCommandSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    q = serializers.CharField(min_length=2, max_length=1200)
    work_id = serializers.UUIDField(required=False)

    def validate(self, data):
        if set(self.initial_data) - set(self.fields):
            raise serializers.ValidationError("查询包含不支持的参数。")
        return data


class IndexQueryReceiptSerializer(serializers.Serializer):
    owner_id = serializers.CharField()
    request_id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    session_id = serializers.UUIDField(allow_null=True)
    next_url = serializers.CharField(allow_blank=True)


def receipt(row):
    return {"owner_id": str(row.actor_id), "request_id": row.request_id, "state": "cancelled" if row.after.get("cancelled") else "applied",
            "session_id": row.after.get("session_id"), "next_url": ""}


class IndexQueryView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryStaff]

    @extend_schema(request=IndexQueryCommandSerializer, responses=IndexQueryReceiptSerializer)
    @transaction.atomic
    def post(self, request):
        actor = locked_actor(request, capability=Capability.VIEW_SYSTEM_STATUS)
        serializer = IndexQueryCommandSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        signature = sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
        prior = AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(data["request_id"])).first()
        if prior:
            if not prior.after.get("cancelled") and prior.after.get("signature") != signature:
                raise EditConflict("同一次请求不能更换作品或检索词。")
            return Response(receipt(prior))
        filters = {"access": ["public"]}
        if data.get("work_id"):
            from catalog.models import Work
            get_object_or_404(Work, pk=data["work_id"])
            filters["work_ids"] = [str(data["work_id"])]
        request.user = actor
        session, _ = create_session(request, data["q"], normalize_filters(filters))
        # Facets constrain passages; cap every channel before dispatch as well.
        session.access_statuses = sorted(set(session.access_statuses).intersection({"public"}))
        session.save(update_fields=["access_statuses", "updated_at"])
        row = AuditEvent.objects.create(actor=actor, action=ACTION, object_type="discovery_search_session", object_id=str(session.pk),
            request_id=str(data["request_id"]), after={"signature": signature, "session_id": str(session.pk)})
        return Response(receipt(row))


class IndexQueryReceiptView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryStaff]

    @extend_schema(responses=IndexQueryReceiptSerializer)
    @transaction.atomic
    def get(self, request, request_id):
        actor = locked_actor(request, capability=Capability.VIEW_SYSTEM_STATUS)
        return Response(receipt(get_object_or_404(AuditEvent, actor=actor, action=ACTION, request_id=str(request_id))))

    @extend_schema(request=IndexMaintenanceStopSerializer, responses=IndexQueryReceiptSerializer)
    @transaction.atomic
    def post(self, request, request_id):
        actor = locked_actor(request, capability=Capability.VIEW_SYSTEM_STATUS)
        serializer = IndexMaintenanceStopSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        if set(request.data) != {"action"}: raise ValidationError("只可停止原待定查询请求。")
        row = AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(request_id)).first()
        if row is None:
            row = AuditEvent.objects.create(actor=actor, action=ACTION, object_type="discovery_search_session", object_id="", request_id=str(request_id), after={"cancelled": True})
        return Response(receipt(row))
