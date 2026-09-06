from rest_framework import serializers
from catalog.models import CatalogingSession


class CatalogingSessionSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(choices=CatalogingSession.Status.choices, read_only=True)
    source_type = serializers.ChoiceField(choices=CatalogingSession.SourceType.choices, read_only=True)
    work_id = serializers.UUIDField(read_only=True, allow_null=True)
    edition_id = serializers.UUIDField(read_only=True, allow_null=True)
    upload_item_id = serializers.UUIDField(read_only=True, allow_null=True)
    base_public_revision_id = serializers.UUIDField(read_only=True, allow_null=True)
    workbench_url = serializers.SerializerMethodField()

    class Meta:
        model = CatalogingSession
        fields = ("id", "source_type", "status", "edition_id", "work_id", "upload_item_id",
                  "base_public_revision_id", "created_at", "updated_at", "workbench_url")

    def get_workbench_url(self, obj) -> str:
        return f"/admin/cataloging/{obj.pk}"


class CatalogingSessionDetailSerializer(serializers.Serializer):
    session = CatalogingSessionSerializer()
    workspace = serializers.JSONField(allow_null=True)


class ApiErrorSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    field = serializers.CharField(allow_null=True)
    severity = serializers.ChoiceField(choices=["blocking", "warning", "info"])
    details = serializers.JSONField()
