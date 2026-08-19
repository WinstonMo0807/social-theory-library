from __future__ import annotations

from rest_framework import serializers

from catalog.models import (
    ReadingPathItem,
    ReadingPathStage,
    RecommendationItem,
    RecommendationOverride,
    RecommendationPolicy,
    Work,
)


class ReadingPathPlacementCreateSerializer(serializers.Serializer):
    reading_path_id = serializers.UUIDField()
    stage_id = serializers.UUIDField()
    recommendation_reason = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    is_required = serializers.BooleanField(required=False, default=False)
    editorial_note = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    expected_path_updated_at = serializers.DateTimeField(required=False, allow_null=True)


class ReadingPathPlacementUpdateSerializer(serializers.Serializer):
    stage_id = serializers.UUIDField(required=False)
    recommendation_reason = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    is_required = serializers.BooleanField(required=False)
    editorial_note = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    expected_path_updated_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs):
        editable = {"stage_id", "recommendation_reason", "is_required", "editorial_note"}
        if not editable.intersection(attrs):
            raise serializers.ValidationError("至少需要提交一项 placement 修改。")
        return attrs


class ExpectedPathVersionSerializer(serializers.Serializer):
    expected_path_updated_at = serializers.DateTimeField(required=False, allow_null=True)


class WorkRecommendationOverrideInputSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=RecommendationOverride.Action.choices)
    position = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    note = serializers.CharField(required=False, allow_blank=True, max_length=300)

    def validate(self, attrs):
        action = attrs["action"]
        if action == RecommendationOverride.Action.EXCLUDE:
            attrs["position"] = None
        return attrs


class CurationWorkSerializer(serializers.ModelSerializer):
    class Meta:
        model = Work
        fields = ("id", "title", "document_type", "language", "updated_at")


class ReadingPathStageSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ReadingPathStage
        fields = ("id", "name", "description", "position")


class WorkReadingPathPlacementSerializer(serializers.ModelSerializer):
    stage = ReadingPathStageSummarySerializer(read_only=True)
    reading_path = serializers.SerializerMethodField()
    path_updated_at = serializers.DateTimeField(source="reading_path.updated_at", read_only=True)

    class Meta:
        model = ReadingPathItem
        fields = (
            "id",
            "reading_path",
            "path_updated_at",
            "stage",
            "work",
            "recommendation_reason",
            "is_required",
            "editorial_note",
            "position",
            "reading_order",
            "created_at",
            "updated_at",
        )

    def get_reading_path(self, obj):
        path = obj.reading_path
        return {
            "id": str(path.id),
            "title": path.title,
            "slug": path.slug,
            "status": path.status,
        }


class WorkRecommendationOverrideSerializer(serializers.ModelSerializer):
    placement = serializers.CharField(source="policy.placement", read_only=True)
    policy_title = serializers.CharField(source="policy.title", read_only=True)

    class Meta:
        model = RecommendationOverride
        fields = (
            "id",
            "policy",
            "placement",
            "policy_title",
            "work",
            "action",
            "position",
            "active",
            "note",
            "created_at",
            "updated_at",
        )


class WorkRecommendationCurrentItemSerializer(serializers.ModelSerializer):
    placement = serializers.CharField(source="snapshot.policy.placement", read_only=True)
    policy_title = serializers.CharField(source="snapshot.policy.title", read_only=True)
    snapshot_id = serializers.UUIDField(source="snapshot.id", read_only=True)
    snapshot_source = serializers.CharField(source="snapshot.source", read_only=True)
    starts_at = serializers.DateTimeField(source="snapshot.starts_at", read_only=True)
    expires_at = serializers.DateTimeField(source="snapshot.expires_at", read_only=True)

    class Meta:
        model = RecommendationItem
        fields = (
            "id",
            "placement",
            "policy_title",
            "snapshot_id",
            "snapshot_source",
            "starts_at",
            "expires_at",
            "position",
            "reason",
        )


class WorkRecommendationPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = RecommendationPolicy
        fields = (
            "id",
            "placement",
            "title",
            "item_count",
            "rotation_days",
            "enabled",
            "last_generated_at",
            "next_refresh_at",
            "updated_at",
        )
