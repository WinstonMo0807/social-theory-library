from rest_framework import serializers

from .models import AnonymousUsageEvent


class PublicUsageEventRequestSerializer(serializers.Serializer):
    event_type = serializers.ChoiceField(choices=AnonymousUsageEvent.EventType.choices)
    work_id = serializers.UUIDField(required=False)
    asset_id = serializers.UUIDField(required=False)
    query = serializers.CharField(required=False, allow_blank=True)
    result_count = serializers.IntegerField(required=False, min_value=0)
    source = serializers.CharField(required=False, max_length=80)
    scope = serializers.CharField(required=False, max_length=80, help_text="page_view只允许公开页面类别，不接受路径或查询；其他事件沿用原范围。")


class PublicUsageEventResponseSerializer(serializers.Serializer):
    accepted = serializers.BooleanField()
    event_id = serializers.UUIDField(allow_null=True)


class UsageTrendDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    page_views = serializers.IntegerField(allow_null=True, min_value=0)
    searches = serializers.IntegerField(allow_null=True, min_value=0)
    reader_opens = serializers.IntegerField(allow_null=True, min_value=0)


class UsageComparisonSerializer(serializers.Serializer):
    current = serializers.IntegerField(min_value=0)
    previous = serializers.IntegerField(min_value=0)
    change_percent = serializers.FloatField(allow_null=True)
    status = serializers.ChoiceField(choices=("available", "outside_retention", "page_view_history_incomplete", "no_previous_records"))


class UsageRangeSerializer(serializers.Serializer):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    previous_start = serializers.DateTimeField()
    previous_end = serializers.DateTimeField()
    timezone = serializers.CharField()
    custom_dates = serializers.BooleanField()
    checked_at = serializers.DateTimeField()


class UsageCoverageSerializer(serializers.Serializer):
    retention_days = serializers.IntegerField(min_value=1)
    retained_since = serializers.DateTimeField()
    page_views_first_recorded_at = serializers.DateTimeField(allow_null=True)
    range_within_retention = serializers.BooleanField()
    comparison_within_retention = serializers.BooleanField()
    page_views_backfilled = serializers.BooleanField()


class UsageTopWorkSerializer(serializers.Serializer):
    work_id = serializers.UUIDField()
    work__title = serializers.CharField()
    opens = serializers.IntegerField(min_value=0)
    unique_sessions = serializers.IntegerField(min_value=0)
    public_url = serializers.CharField(allow_null=True)


class UsageTopQuerySerializer(serializers.Serializer):
    normalized_query = serializers.CharField()
    search_count = serializers.IntegerField(min_value=0)
    unique_sessions = serializers.IntegerField(min_value=0)
    click_count = serializers.IntegerField(min_value=0)
    zero_result_count = serializers.IntegerField(min_value=0)
    click_through_rate = serializers.FloatField()


class UsagePrivacySerializer(serializers.Serializer):
    stores_ip_identity = serializers.BooleanField()
    links_registered_user = serializers.BooleanField()
    retention_days = serializers.IntegerField(min_value=1)


class AdminUsageAnalyticsSerializer(serializers.Serializer):
    period_days = serializers.IntegerField(min_value=1, max_value=365)
    anonymous_sessions = serializers.IntegerField(min_value=0)
    events = serializers.DictField(child=serializers.IntegerField(min_value=0))
    zero_result_searches = serializers.IntegerField(min_value=0)
    range = UsageRangeSerializer()
    trend = UsageTrendDaySerializer(many=True)
    comparisons = serializers.DictField(child=UsageComparisonSerializer())
    coverage = UsageCoverageSerializer()
    top_works = UsageTopWorkSerializer(many=True)
    top_queries = UsageTopQuerySerializer(many=True)
    privacy = UsagePrivacySerializer()
