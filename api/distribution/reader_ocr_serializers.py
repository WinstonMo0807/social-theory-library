"""Narrow Reader OCR contract, without administrative workspace contents."""
from rest_framework import serializers


class ReaderOCRCommandInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=["pause", "resume"])
    request_id = serializers.UUIDField()
    job_id = serializers.UUIDField()
    job_version = serializers.CharField(max_length=80)
    source_sha256 = serializers.RegexField(r"^[0-9a-f]{64}$")
    document_revision_id = serializers.UUIDField(allow_null=True)

    def to_internal_value(self, data):
        if isinstance(data, dict) and (unknown := set(data) - self.fields.keys()):
            raise serializers.ValidationError({key: "不支持此字段。" for key in sorted(unknown)})
        return super().to_internal_value(data)


class ReaderOCRJobOutput(serializers.Serializer):
    id = serializers.UUIDField()
    job_version = serializers.CharField(help_text="固定字符串；提交命令时原样传回，不重新格式化时间。")
    status = serializers.CharField()
    phase = serializers.CharField(allow_blank=True)
    phase_label = serializers.CharField()
    completed_pages = serializers.IntegerField(allow_null=True)
    total_pages = serializers.IntegerField(allow_null=True, help_text="本次任务目标页数，不一定等于整份文件页数。")
    percent = serializers.FloatField(allow_null=True)
    phase_elapsed_seconds = serializers.IntegerField()
    updated_at = serializers.DateTimeField()
    pause_requested = serializers.BooleanField()
    stale = serializers.BooleanField()


class ReaderOCRContentOutput(serializers.Serializer):
    state = serializers.ChoiceField(choices=["unavailable", "awaiting_publication", "published", "admin_preview"])
    url = serializers.CharField(allow_null=True)
    label = serializers.CharField()
    notice = serializers.CharField(allow_blank=True)


class ReaderOCRReceiptOutput(serializers.Serializer):
    request_id = serializers.UUIDField()
    action = serializers.ChoiceField(choices=["pause", "resume"])
    job_id = serializers.UUIDField()
    applied = serializers.BooleanField()


class ReaderOCRStatusOutput(serializers.Serializer):
    asset_id = serializers.UUIDField()
    edition_id = serializers.UUIDField()
    owner_id = serializers.IntegerField(allow_null=True)
    document_revision_id = serializers.UUIDField(allow_null=True)
    source_sha256 = serializers.CharField()
    file_page_count = serializers.IntegerField()
    ocr_status = serializers.CharField()
    checked_at = serializers.DateTimeField()
    job = ReaderOCRJobOutput(allow_null=True)
    can_pause = serializers.BooleanField()
    can_resume = serializers.BooleanField()
    denied_reason = serializers.CharField(allow_blank=True)
    management_url = serializers.CharField(allow_null=True)
    processed_content = ReaderOCRContentOutput()
    receipt = ReaderOCRReceiptOutput(allow_null=True)
