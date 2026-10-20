from rest_framework import serializers

from reading.research_serializers import EvidenceReferenceInput


class ParallelVersionsQuery(serializers.Serializer):
    asset_id = serializers.UUIDField()


class ParallelSegmentsQuery(ParallelVersionsQuery):
    document_revision_id = serializers.UUIDField(required=False)
    page = serializers.IntegerField(min_value=1, default=1)
    offset = serializers.IntegerField(min_value=0, max_value=10000, default=0)
    focus = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")


class ParallelReferenceInput(EvidenceReferenceInput):
    evidence_span_id = serializers.UUIDField(required=False, allow_null=True)
    asset_id = serializers.UUIDField()
    document_revision_id = serializers.UUIDField()
    pdf_page = serializers.IntegerField(min_value=1)
    content_hash = serializers.RegexField(r"^[0-9a-f]{64}$")
    work_id = serializers.UUIDField(required=False)
    edition_id = serializers.UUIDField(required=False)


class ParallelCandidatesInput(serializers.Serializer):
    left_reference = ParallelReferenceInput()
    target_asset_id = serializers.UUIDField()
    target_document_revision_id = serializers.UUIDField()


class ParallelReferenceOutput(serializers.Serializer):
    reference_id = serializers.CharField()
    source_status = serializers.ChoiceField(choices=["available", "unavailable"])
    work_id = serializers.UUIDField()
    edition_id = serializers.UUIDField()
    asset_id = serializers.UUIDField()
    document_revision_id = serializers.UUIDField()
    evidence_span_id = serializers.UUIDField(allow_null=True, required=False)
    pdf_page = serializers.IntegerField()
    content_hash = serializers.CharField()
    printed_label = serializers.CharField(allow_blank=True)
    title = serializers.CharField()
    authors = serializers.ListField(child=serializers.CharField())
    quote = serializers.CharField()
    reader_url = serializers.CharField(allow_null=True)
    locator_precision = serializers.CharField()
    selection_start = serializers.IntegerField(required=False)
    selection_end = serializers.IntegerField(required=False)
    page_text_range = serializers.JSONField(allow_null=True, required=False)
    anchors = serializers.ListField(child=serializers.JSONField(), required=False)


class ParallelVersionOutput(serializers.Serializer):
    work_id = serializers.UUIDField()
    edition_id = serializers.UUIDField()
    asset_id = serializers.UUIDField(allow_null=True)
    document_revision_id = serializers.UUIDField(allow_null=True)
    title = serializers.CharField()
    original_title = serializers.CharField(allow_blank=True)
    authors = serializers.ListField(child=serializers.CharField())
    language = serializers.CharField(allow_blank=True)
    publication_year = serializers.IntegerField(allow_null=True)
    version_label = serializers.CharField(allow_blank=True)
    publisher = serializers.CharField(allow_blank=True)
    cover_url = serializers.CharField(allow_null=True)
    total_pages = serializers.IntegerField()
    relation = serializers.ChoiceField(choices=["same_work", "translation"])
    current = serializers.BooleanField()
    state = serializers.ChoiceField(choices=["available", "metadata_only"])
    notice = serializers.CharField(allow_blank=True)


class ParallelVersionsOutput(serializers.Serializer):
    source_asset_id = serializers.UUIDField()
    versions = ParallelVersionOutput(many=True)
    truncated = serializers.BooleanField()


class ParallelSegmentOutput(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    order = serializers.IntegerField()
    reference = ParallelReferenceOutput()
    printed_label = serializers.CharField(allow_blank=True)
    text = serializers.CharField()
    text_truncated = serializers.BooleanField()


class ParallelSegmentsOutput(serializers.Serializer):
    asset_id = serializers.UUIDField()
    edition_id = serializers.UUIDField()
    document_revision_id = serializers.UUIDField(allow_null=True)
    page = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    previous_page = serializers.IntegerField(allow_null=True)
    next_page = serializers.IntegerField(allow_null=True)
    state = serializers.ChoiceField(choices=["ready", "unstructured", "empty", "text_unavailable"])
    notice = serializers.CharField(allow_blank=True)
    segments = ParallelSegmentOutput(many=True)
    offset = serializers.IntegerField()
    has_more = serializers.BooleanField()
    next_offset = serializers.IntegerField(allow_null=True)


class ParallelCandidateOutput(serializers.Serializer):
    reference = ParallelReferenceOutput()
    label = serializers.CharField()
    text = serializers.CharField()
    status = serializers.ChoiceField(choices=["pending"])
    text_truncated = serializers.BooleanField()


class ParallelWarning(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()


class ParallelCandidatesOutput(serializers.Serializer):
    state = serializers.ChoiceField(choices=["ready", "partial", "empty", "unavailable"])
    notice = serializers.CharField()
    candidates = ParallelCandidateOutput(many=True)
    warnings = ParallelWarning(many=True)
    allows_no_correspondence = serializers.BooleanField()
