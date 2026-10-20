from rest_framework import serializers


class PrivacyPreferencesInput(serializers.Serializer):
    expected_revision = serializers.IntegerField(min_value=1)
    retention = serializers.DictField(child=serializers.BooleanField())


class PrivacyTargetInput(serializers.Serializer):
    category = serializers.ChoiceField(choices=["reading_history", "search_history", "annotations", "memories", "parallel_alignments", "plans", "followed_topics", "source_follows"])
    id = serializers.UUIDField()
    revision = serializers.CharField(max_length=80)


class PrivacyOperationInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=["export", "erase"])
    categories = serializers.ListField(child=serializers.ChoiceField(choices=["research", "notes", "plans", "audits", "source_follows"]), max_length=5, required=False)
    targets = PrivacyTargetInput(many=True, required=False)

    def validate(self, attrs):
        if attrs["kind"] == "export" and (not attrs.get("categories") or attrs.get("targets")):
            raise serializers.ValidationError("导出需要明确选择资料类型。")
        if attrs["kind"] == "erase" and (not attrs.get("targets") or attrs.get("categories") or len(attrs["targets"]) > 500):
            raise serializers.ValidationError("删除预览需要明确选择 1 至 500 项本人资料。")
        return attrs


class PrivacyCommandInput(serializers.Serializer):
    expected_revision = serializers.IntegerField(min_value=1)
    action = serializers.ChoiceField(choices=["confirm", "cancel", "retry"])


class PrivacyOperationOutput(serializers.Serializer):
    id = serializers.UUIDField()
    owner_id = serializers.CharField()
    revision = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=["export", "erase"])
    status = serializers.ChoiceField(choices=["preview", "queued", "running", "completed", "partial", "failed", "canceled"])
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    finished_at = serializers.DateTimeField(allow_null=True)
    total = serializers.IntegerField()
    completed = serializers.IntegerField()
    failed = serializers.IntegerField()
    remaining = serializers.IntegerField()
    categories = serializers.ListField(child=serializers.CharField())
    results = serializers.ListField(child=serializers.DictField())
    preview = serializers.ListField(child=serializers.DictField())
    error_code = serializers.CharField(allow_blank=True)
    download_available = serializers.BooleanField()
    notice = serializers.CharField()


class PrivacySummaryOutput(serializers.Serializer):
    owner_id = serializers.CharField()
    revision = serializers.IntegerField()
    retention = serializers.DictField(child=serializers.BooleanField())
    automatic_memory_use = serializers.BooleanField()
    confirmed_notes = serializers.IntegerField()
    authorized_contexts = serializers.IntegerField()
    export_counts = serializers.DictField(child=serializers.IntegerField())
    erase_counts = serializers.DictField(child=serializers.IntegerField())
    operations = PrivacyOperationOutput(many=True)
    preference_history = serializers.ListField(child=serializers.DictField())
    max_operation_items = serializers.IntegerField()
    export_formats = serializers.ListField(child=serializers.CharField())
    notice = serializers.CharField()


class PrivacyItemsOutput(serializers.Serializer):
    owner_id = serializers.CharField()
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    results = serializers.ListField(child=serializers.DictField())


class PrivacyOperationsPage(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = PrivacyOperationOutput(many=True)
