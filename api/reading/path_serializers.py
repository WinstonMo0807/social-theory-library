"""Explicit owner commands, never a client-supplied copy of public material."""
from collections.abc import Mapping

from rest_framework import serializers


class PathInput(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, Mapping) or set(data) - set(self.fields):
            raise serializers.ValidationError("请求包含不支持的字段；公开路径内容由服务端读取。")
        return super().to_internal_value(data)


class PathInteger(serializers.IntegerField):
    def to_internal_value(self, value):
        if isinstance(value, bool):
            self.fail("invalid")
        return super().to_internal_value(value)


class PathBoolean(serializers.BooleanField):
    def to_internal_value(self, value):
        if type(value) is not bool:
            self.fail("invalid", input=value)
        return value


class PathCreateInput(PathInput):
    request_id = serializers.UUIDField()
    path_id = serializers.UUIDField()
    expected_source_revision = serializers.CharField(max_length=160)
    bookmarked = PathBoolean(default=True)


class PathRevisionInput(PathInput):
    request_id = serializers.UUIDField()
    expected_revision = PathInteger(min_value=1)


class PathUpdateInput(PathRevisionInput):
    action = serializers.ChoiceField(choices=("bookmark", "progress", "note"))
    bookmarked = PathBoolean(required=False)
    item_id = serializers.UUIDField(required=False)
    status = serializers.ChoiceField(choices=("pending", "reading", "completed", "skipped"), required=False)
    note = serializers.CharField(max_length=4000, allow_blank=True, required=False)

    def validate(self, attrs):
        required = {"bookmark": {"bookmarked"}, "progress": {"item_id", "status"}, "note": {"item_id", "note"}}[attrs["action"]]
        supplied = set(attrs) - {"request_id", "expected_revision", "action"}
        if supplied != required:
            raise serializers.ValidationError("请只提供当前操作要求的完整字段。")
        return attrs


class PathCopyInput(PathRevisionInput):
    title = serializers.CharField(max_length=240, allow_blank=True, required=False, default="")


class PathUpgradeInput(PathRevisionInput):
    target_revision = serializers.CharField(max_length=160)


class PathProgressOutput(serializers.Serializer):
    status = serializers.ChoiceField(choices=("pending", "reading", "completed", "skipped"))
    note = serializers.CharField(allow_blank=True)


class PathSourceRevisionOutput(serializers.Serializer):
    id = serializers.CharField(allow_null=True)
    token = serializers.CharField()
    number = serializers.IntegerField(allow_null=True)
    published_at = serializers.DateTimeField(allow_null=True)
    change_note = serializers.CharField(allow_blank=True)
    legacy = serializers.BooleanField()


class PathRecordOutput(serializers.Serializer):
    id = serializers.UUIDField()
    revision = serializers.IntegerField(min_value=1)
    type = serializers.ChoiceField(choices=("path_follow", "personal_plan"))
    path_id = serializers.UUIDField()
    path_slug = serializers.CharField(allow_blank=True)
    bookmarked = serializers.BooleanField()
    source_revision = PathSourceRevisionOutput()
    latest_source_revision = PathSourceRevisionOutput(allow_null=True)
    source_status = serializers.ChoiceField(choices=("available", "unavailable", "revision_changed"))
    path = serializers.JSONField(help_text="Original public stages/items with current source availability; no draft content.")
    progress = serializers.DictField(child=PathProgressOutput())
    completed_items = serializers.IntegerField()
    total_items = serializers.IntegerField()
    completed_stages = serializers.IntegerField()
    total_stages = serializers.IntegerField()
    history = serializers.ListField(child=serializers.JSONField())
    data = serializers.JSONField(help_text="Personal plan data; the existing plan editor uses the same encrypted record.")
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class PathReceiptOutput(serializers.Serializer):
    request_id = serializers.UUIDField()
    applied_revision = serializers.IntegerField(min_value=1)
    deleted = serializers.BooleanField()


class PathCommandOutput(serializers.Serializer):
    owner_id = serializers.CharField()
    record = PathRecordOutput(allow_null=True)
    receipt = PathReceiptOutput(allow_null=True)


class PathPageOutput(serializers.Serializer):
    owner_id = serializers.CharField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = PathRecordOutput(many=True)


class PathDiffOutput(serializers.Serializer):
    added = serializers.ListField(child=serializers.UUIDField())
    removed = serializers.ListField(child=serializers.UUIDField())
    changed = serializers.ListField(child=serializers.UUIDField())
    unchanged = serializers.ListField(child=serializers.UUIDField())


class PathUpgradePreviewOutput(serializers.Serializer):
    owner_id = serializers.CharField()
    record_id = serializers.UUIDField()
    expected_revision = serializers.IntegerField(min_value=1)
    source_revision = PathSourceRevisionOutput()
    target_revision = PathSourceRevisionOutput()
    diff = PathDiffOutput()
    retained_completed = serializers.ListField(child=serializers.UUIDField())
    retained_notes = serializers.ListField(child=serializers.UUIDField())
