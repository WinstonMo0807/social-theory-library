"""Parallel reading command contracts. Unknown fields cannot carry private data into publication."""
from rest_framework import serializers

from catalog.parallel_serializers import ParallelReferenceInput


class StrictInput(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - self.fields.keys()
            if unknown:
                raise serializers.ValidationError({key: "不支持此字段。" for key in sorted(unknown)})
        return super().to_internal_value(data)


class ParallelPositionInput(StrictInput):
    left_page = serializers.IntegerField(min_value=1, default=1)
    right_page = serializers.IntegerField(min_value=1, default=1)
    left_segment_id = serializers.CharField(max_length=160, allow_blank=True, allow_null=True, required=False)
    right_segment_id = serializers.CharField(max_length=160, allow_blank=True, allow_null=True, required=False)


class ParallelAlignmentInput(StrictInput):
    id = serializers.UUIDField()
    left = ParallelReferenceInput(allow_null=True, required=False)
    right = ParallelReferenceInput(allow_null=True, required=False)
    status = serializers.ChoiceField(choices=["confirmed", "no_match", "addition"])
    note = serializers.CharField(max_length=8000, allow_blank=True, default="")


class ParallelTermInput(StrictInput):
    id = serializers.UUIDField()
    original = serializers.CharField(max_length=500)
    translation = serializers.CharField(max_length=500, allow_blank=True, default="")
    note = serializers.CharField(max_length=8000, allow_blank=True, default="")
    left = ParallelReferenceInput(allow_null=True, required=False)
    right = ParallelReferenceInput(allow_null=True, required=False)


class ParallelTaskDataInput(StrictInput):
    left_asset_id = serializers.UUIDField()
    right_asset_id = serializers.UUIDField()
    left_document_revision_id = serializers.UUIDField()
    right_document_revision_id = serializers.UUIDField()
    positions = ParallelPositionInput(required=False)
    sync_scroll = serializers.BooleanField(default=True)
    alignments = ParallelAlignmentInput(many=True, default=list)
    terms = ParallelTermInput(many=True, default=list)

    def validate_alignments(self, value):
        if len(value) > 200:
            raise serializers.ValidationError("一项并读任务最多保存 200 条对齐。")
        return value

    def validate_terms(self, value):
        if len(value) > 200:
            raise serializers.ValidationError("一项并读任务最多保存 200 条术语。")
        return value


class ParallelTaskCreateInput(StrictInput):
    request_id = serializers.UUIDField()
    data = ParallelTaskDataInput()


class ParallelTaskUpdateInput(ParallelTaskCreateInput):
    expected_revision = serializers.IntegerField(min_value=1)


class ParallelCalibrationCreateInput(StrictInput):
    request_id = serializers.UUIDField()
    task_id = serializers.UUIDField()
    expected_revision = serializers.IntegerField(min_value=1)
    alignment_id = serializers.UUIDField(required=False)
    scope = serializers.ChoiceField(choices=["bibliography", "passages"])
    basis = serializers.CharField(max_length=4000)


class ParallelReviewInput(StrictInput):
    request_id = serializers.UUIDField()
    expected_revision = serializers.IntegerField(min_value=1)
    note = serializers.CharField(max_length=2000, allow_blank=True, default="")


class ParallelStoredReferenceOutput(serializers.Serializer):
    asset_id = serializers.UUIDField()
    document_revision_id = serializers.UUIDField()
    pdf_page = serializers.IntegerField()
    content_hash = serializers.CharField()
    evidence_span_id = serializers.UUIDField(required=False, allow_null=True)
    work_id = serializers.UUIDField(required=False)
    edition_id = serializers.UUIDField(required=False)
    reference_id = serializers.CharField()
    source_status = serializers.ChoiceField(choices=["available", "unavailable"])
    quote = serializers.CharField(allow_blank=True)
    reader_url = serializers.CharField(allow_null=True)
    title = serializers.CharField(required=False, allow_blank=True)
    authors = serializers.ListField(child=serializers.CharField(), required=False)
    printed_label = serializers.CharField(required=False, allow_blank=True)
    selection_start = serializers.IntegerField(required=False)
    selection_end = serializers.IntegerField(required=False)
    anchors = serializers.ListField(child=serializers.JSONField(), required=False)


class ParallelAlignmentOutput(serializers.Serializer):
    id = serializers.UUIDField()
    left = ParallelStoredReferenceOutput(allow_null=True)
    right = ParallelStoredReferenceOutput(allow_null=True)
    status = serializers.ChoiceField(choices=["confirmed", "no_match", "addition"])
    note = serializers.CharField(allow_blank=True, required=False)


class ParallelTermOutput(serializers.Serializer):
    id = serializers.UUIDField()
    original = serializers.CharField()
    translation = serializers.CharField(allow_blank=True)
    note = serializers.CharField(allow_blank=True)
    left = ParallelStoredReferenceOutput(allow_null=True)
    right = ParallelStoredReferenceOutput(allow_null=True)


class ParallelPairOutput(serializers.Serializer):
    left_asset_id = serializers.UUIDField()
    right_asset_id = serializers.UUIDField()
    left_document_revision_id = serializers.UUIDField()
    right_document_revision_id = serializers.UUIDField()


class ParallelTaskDataOutput(ParallelPairOutput):
    positions = ParallelPositionInput()
    sync_scroll = serializers.BooleanField()
    alignments = ParallelAlignmentOutput(many=True)
    terms = ParallelTermOutput(many=True)


class ParallelCalibrationDataOutput(ParallelPairOutput):
    basis = serializers.CharField()
    alignments = ParallelAlignmentOutput(many=True)


class ParallelSourceSummaryOutput(serializers.Serializer):
    title = serializers.CharField(allow_blank=True)
    version_label = serializers.CharField(allow_blank=True)
    authors = serializers.ListField(child=serializers.CharField())
    asset_id = serializers.UUIDField()
    document_revision_id = serializers.UUIDField()
    reader_url = serializers.CharField()


class ParallelPairSourcesOutput(serializers.Serializer):
    left = ParallelSourceSummaryOutput()
    right = ParallelSourceSummaryOutput()


class ParallelTaskOutput(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    revision = serializers.IntegerField(read_only=True)
    request_id = serializers.UUIDField(read_only=True, required=False)
    applied_revision = serializers.IntegerField(read_only=True, required=False)
    data = ParallelTaskDataOutput(read_only=True)
    source_available = serializers.BooleanField(read_only=True)
    pair_sources = ParallelPairSourcesOutput(read_only=True, allow_null=True)
    notice = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class ParallelCalibrationOutput(ParallelTaskOutput):
    data = ParallelCalibrationDataOutput(read_only=True)
    status = serializers.ChoiceField(choices=["submitted", "reviewed", "published", "rejected"], read_only=True)
    scope = serializers.ChoiceField(choices=["bibliography", "passages"], read_only=True)
    review_note = serializers.CharField(read_only=True, required=False)
    reviewer_id = serializers.IntegerField(read_only=True, allow_null=True, required=False)


class ParallelTaskPageOutput(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = ParallelTaskOutput(many=True)


class ParallelCalibrationPageOutput(ParallelTaskPageOutput):
    results = ParallelCalibrationOutput(many=True)


class PublicParallelCalibrationPageOutput(ParallelCalibrationPageOutput):
    count = serializers.IntegerField(allow_null=True,
        help_text="始终为 null；公开读取逐页复核来源，不以未复核候选数冒充可见校准总数。")
    notice = serializers.CharField()
