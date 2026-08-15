from django.db import transaction
from django.db.models import Count
from rest_framework import serializers

from .models import BackupJob, CloudBudgetPolicy, CloudObject, CloudProvider, CloudUsageSnapshot


class CloudBudgetInputSerializer(serializers.Serializer):
    monthly_budget = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
        min_value=0,
    )
    warning_ratio = serializers.FloatField(required=False, min_value=0, max_value=1)
    stop_new_publications_ratio = serializers.FloatField(required=False, min_value=0.01)
    pause_new_cdn_on_limit = serializers.BooleanField(required=False)
    preserve_existing_reads = serializers.BooleanField(required=False)
    notification_emails = serializers.ListField(
        child=serializers.EmailField(),
        required=False,
    )


class CloudProviderSerializer(serializers.ModelSerializer):
    budget = CloudBudgetInputSerializer(write_only=True, required=False)
    budget_policy = serializers.SerializerMethodField()
    latest_usage = serializers.SerializerMethodField()
    object_status_counts = serializers.SerializerMethodField()

    class Meta:
        model = CloudProvider
        fields = (
            "id",
            "name",
            "provider_type",
            "endpoint_url",
            "bucket",
            "region",
            "public_base_url",
            "credential_reference",
            "enabled",
            "is_default",
            "budget",
            "budget_policy",
            "latest_usage",
            "object_status_counts",
        )

    def get_budget_policy(self, obj):
        try:
            policy = obj.budget_policy
        except CloudBudgetPolicy.DoesNotExist:
            return None
        return {
            "monthly_budget": policy.monthly_budget,
            "warning_ratio": policy.warning_ratio,
            "stop_new_publications_ratio": policy.stop_new_publications_ratio,
            "pause_new_cdn_on_limit": policy.pause_new_cdn_on_limit,
            "preserve_existing_reads": policy.preserve_existing_reads,
            "notification_emails": policy.notification_emails,
        }

    def get_latest_usage(self, obj):
        snapshot = obj.usage_snapshots.order_by("-period", "-created_at").first()
        return CloudUsageSnapshotSerializer(snapshot).data if snapshot else None

    def get_object_status_counts(self, obj):
        return {
            row["status"]: row["count"]
            for row in obj.cloud_objects.values("status").annotate(count=Count("id"))
        }

    def _save_budget(self, provider, budget):
        if budget is None:
            return
        allowed = {
            "monthly_budget",
            "warning_ratio",
            "stop_new_publications_ratio",
            "pause_new_cdn_on_limit",
            "preserve_existing_reads",
            "notification_emails",
        }
        values = {key: value for key, value in budget.items() if key in allowed}
        CloudBudgetPolicy.objects.update_or_create(provider=provider, defaults=values)

    @transaction.atomic
    def create(self, validated_data):
        budget = validated_data.pop("budget", None)
        if validated_data.get("is_default"):
            CloudProvider.objects.filter(is_default=True).update(is_default=False)
        provider = super().create(validated_data)
        self._save_budget(provider, budget)
        return provider

    @transaction.atomic
    def update(self, instance, validated_data):
        budget = validated_data.pop("budget", None)
        if validated_data.get("is_default"):
            CloudProvider.objects.filter(is_default=True).exclude(pk=instance.pk).update(is_default=False)
        provider = super().update(instance, validated_data)
        self._save_budget(provider, budget)
        return provider


class CloudObjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = CloudObject
        fields = (
            "id",
            "asset",
            "provider",
            "object_key",
            "etag",
            "sha256",
            "byte_size",
            "status",
            "cdn_enabled",
            "last_verified_at",
            "error_message",
        )
        read_only_fields = (
            "etag",
            "sha256",
            "byte_size",
            "status",
            "last_verified_at",
            "error_message",
        )


class BackupJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = BackupJob
        fields = (
            "id",
            "status",
            "destination_path",
            "include_originals",
            "archive_path",
            "manifest",
            "checksum",
            "error_message",
            "started_at",
            "completed_at",
            "created_at",
        )
        read_only_fields = (
            "id",
            "status",
            "archive_path",
            "manifest",
            "checksum",
            "error_message",
            "started_at",
            "completed_at",
            "created_at",
        )


class CloudUsageSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = CloudUsageSnapshot
        fields = (
            "id",
            "provider",
            "period",
            "storage_bytes",
            "egress_bytes",
            "request_count",
            "estimated_cost",
            "source_payload",
            "created_at",
        )
        read_only_fields = ("id", "provider", "created_at")

    def validate_period(self, value):
        if len(value) != 7 or value[4] != "-" or not value[:4].isdigit() or not value[5:].isdigit():
            raise serializers.ValidationError("月份必须使用 YYYY-MM 格式。")
        month = int(value[5:])
        if not 1 <= month <= 12:
            raise serializers.ValidationError("月份无效。")
        return value
