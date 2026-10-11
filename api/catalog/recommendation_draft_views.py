from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import CanEditMetadata, IsLibraryStaff
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import RecommendationPolicy
from catalog.services.recommendation_drafts import save_selection, selection_state


class RecommendationSelectionInputSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    target_type = serializers.ChoiceField(choices=["work", "topic", "scholar"])


class RecommendationSelectionItemSerializer(RecommendationSelectionInputSerializer):
    name = serializers.CharField()
    image_url = serializers.CharField(allow_blank=True)
    available = serializers.BooleanField()


class RecommendationSelectionDraftSerializer(serializers.Serializer):
    policy_id = serializers.UUIDField()
    exists = serializers.BooleanField()
    edit_version = serializers.CharField()
    expected_updated_at = serializers.DateTimeField()
    expected_snapshot_id = serializers.UUIDField(allow_null=True)
    items = RecommendationSelectionItemSerializer(many=True)
    public_unchanged = serializers.BooleanField()


class SaveRecommendationSelectionSerializer(serializers.Serializer):
    items = RecommendationSelectionInputSerializer(many=True, max_length=50)
    edit_version = serializers.CharField(max_length=100)
    expected_updated_at = serializers.DateTimeField()
    expected_snapshot_id = serializers.UUIDField(allow_null=True)
    request_key = serializers.UUIDField()


class AdminRecommendationSelectionDraftView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryStaff, CanEditMetadata]

    @extend_schema(responses=RecommendationSelectionDraftSerializer)
    def get(self, request, placement):
        policy = get_object_or_404(RecommendationPolicy, placement=placement)
        return Response(RecommendationSelectionDraftSerializer(selection_state(policy)).data)

    @extend_schema(request=SaveRecommendationSelectionSerializer, responses=RecommendationSelectionDraftSerializer)
    @transaction.atomic
    def put(self, request, placement):
        policy = get_object_or_404(RecommendationPolicy.objects.select_for_update(), placement=placement)
        serializer = SaveRecommendationSelectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(RecommendationSelectionDraftSerializer(save_selection(policy, serializer.validated_data, request.user)).data)
