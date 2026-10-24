from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from catalog.editorial_read import AdminPrivateResponseMixin
from common.permissions import CanRunDestructiveMaintenance
from .storage_cleanup import inspect_plan


class CleanupItem(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    bytes = serializers.IntegerField()
    modified_at = serializers.DateTimeField()
    outcome = serializers.CharField()
    detail = serializers.CharField()


class CleanupPlanOutput(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    status_label = serializers.CharField()
    version = serializers.CharField()
    created_at = serializers.DateTimeField()
    stale = serializers.BooleanField()
    stalled = serializers.BooleanField()
    execution_supported = serializers.BooleanField()
    retention_days = serializers.IntegerField()
    rows = CleanupItem(many=True)
    selected = serializers.ListField(child=serializers.CharField())
    candidate_bytes = serializers.IntegerField()
    candidate_count = serializers.IntegerField()
    released_bytes = serializers.IntegerField()
    deleted_count = serializers.IntegerField()
    examined_count = serializers.IntegerField()
    protected_count = serializers.IntegerField()
    limited = serializers.BooleanField()
    notice = serializers.CharField()
    error_message = serializers.CharField()
    scope = serializers.CharField()


class CleanupPlanView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanRunDestructiveMaintenance]

    @extend_schema(responses=CleanupPlanOutput)
    def get(self, request, cleanup_id):
        return Response(CleanupPlanOutput(inspect_plan(request.user, cleanup_id)).data)
