from rest_framework import serializers
from catalog.media_views import PublicCoverMediaSerializer

from .models import PublicFeedback

PUBLIC_FEEDBACK_CATEGORIES = PublicFeedback.Category.choices
PUBLIC_FEEDBACK_STATUSES = PublicFeedback.Status.choices


class PublicFeedbackInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    category = serializers.ChoiceField(choices=PublicFeedback.Category.choices, default=PublicFeedback.Category.OTHER)
    body = serializers.CharField(min_length=4, max_length=500, trim_whitespace=True)
    contact = serializers.EmailField(max_length=254, required=False, allow_blank=True, default="")
    path = serializers.CharField(max_length=400, required=False, allow_blank=True, default="")
    consent = serializers.BooleanField()

    def validate_consent(self, value):
        if value is not True:
            raise serializers.ValidationError("请同意将填写的信息用于处理本次反馈。")
        return value


class PublicFeedbackReceipt(serializers.Serializer):
    id = serializers.UUIDField()
    request_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=PublicFeedback.Status.choices)
    created_at = serializers.DateTimeField()
    message = serializers.CharField()


class FeedbackListQuery(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    category = serializers.ChoiceField(choices=["", *PublicFeedback.Category.values], default="")
    status = serializers.ChoiceField(choices=["", *PublicFeedback.Status.values], default="")
    page = serializers.IntegerField(min_value=1, max_value=100000, default=1)


class FeedbackHistoryQuery(serializers.Serializer):
    history_page = serializers.IntegerField(min_value=1, max_value=100000, default=1)


class FeedbackUpdateInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    expected_revision = serializers.IntegerField(min_value=1)
    status = serializers.ChoiceField(choices=PublicFeedback.Status.choices)
    note = serializers.CharField(max_length=2000, allow_blank=True, trim_whitespace=True)
    follow_up = serializers.BooleanField()


class FeedbackSummary(serializers.Serializer):
    id = serializers.UUIDField()
    category = serializers.ChoiceField(choices=PublicFeedback.Category.choices)
    status = serializers.ChoiceField(choices=PublicFeedback.Status.choices)
    excerpt = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    revision = serializers.IntegerField()
    follow_up = serializers.BooleanField()


class FeedbackCounts(serializers.Serializer):
    total = serializers.IntegerField()
    submitted = serializers.IntegerField()
    reviewing = serializers.IntegerField()
    resolved = serializers.IntegerField()


class FeedbackListOutput(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    counts = FeedbackCounts()
    results = FeedbackSummary(many=True)


class FeedbackHandlingState(serializers.Serializer):
    status = serializers.ChoiceField(choices=PublicFeedback.Status.choices)
    note = serializers.CharField(allow_blank=True)
    follow_up = serializers.BooleanField()
    revision = serializers.IntegerField()


class FeedbackHistoryEntry(serializers.Serializer):
    id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    actor = serializers.CharField()
    before = FeedbackHandlingState()
    after = FeedbackHandlingState()


class FeedbackHistoryOutput(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    results = FeedbackHistoryEntry(many=True)


class FeedbackSourceOutput(serializers.Serializer):
    status = serializers.ChoiceField(choices=["available", "replaced", "unavailable", "page"])
    canonical_path = serializers.CharField(allow_blank=True)
    title = serializers.CharField()
    authors = serializers.ListField(child=serializers.CharField())
    cover_url = serializers.CharField(allow_blank=True)
    cover_media = PublicCoverMediaSerializer(allow_null=True, required=False)
    source_type = serializers.CharField(allow_blank=True)
    version_label = serializers.CharField(allow_blank=True)
    location = serializers.CharField(allow_blank=True)
    updated_at = serializers.DateTimeField(allow_null=True)
    checked_at = serializers.DateTimeField()
    reader_url = serializers.CharField(allow_blank=True)
    notice = serializers.CharField()


class FeedbackDetailOutput(FeedbackSummary):
    body = serializers.CharField()
    contact = serializers.CharField(allow_blank=True)
    path = serializers.CharField(allow_blank=True)
    consent_at = serializers.DateTimeField(allow_null=True)
    consent_version = serializers.CharField(allow_blank=True)
    note = serializers.CharField(allow_blank=True)
    handled_by = serializers.CharField(allow_blank=True)
    can_follow_up = serializers.BooleanField()
    history = FeedbackHistoryOutput()
    source = FeedbackSourceOutput()


class FeedbackUpdateOutput(serializers.Serializer):
    request_id = serializers.UUIDField()
    accepted_revision = serializers.IntegerField()
    record = FeedbackDetailOutput()
