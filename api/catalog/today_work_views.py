from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.services.today_work import CATEGORIES, KINDS, STATES, today_work_page
from common.permissions import CanAccessBackOffice


class TodayWorkQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=200, allow_blank=True, default="")
    category = serializers.ChoiceField(choices=list(CATEGORIES), default="all")
    kind = serializers.ChoiceField(choices=list(KINDS), default="", allow_blank=True)
    state = serializers.ChoiceField(choices=list(STATES), default="", allow_blank=True)
    owner = serializers.ChoiceField(choices=["all", "me"], default="all")
    ordering = serializers.ChoiceField(choices=["-updated_at", "updated_at"], default="-updated_at")
    page = serializers.IntegerField(min_value=1, default=1)


class TodayWorkItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    object_id = serializers.UUIDField()
    object_type = serializers.CharField()
    title = serializers.CharField()
    label = serializers.CharField()
    updated_at = serializers.DateTimeField()
    url = serializers.CharField()
    state = serializers.CharField()
    state_label = serializers.CharField()
    category = serializers.CharField()
    kind = serializers.CharField()
    action_label = serializers.CharField()
    summary = serializers.CharField()
    thumbnail_url = serializers.CharField(allow_blank=True)


class TodayWorkPageSerializer(serializers.Serializer):
    results = TodayWorkItemSerializer(many=True)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    counts = serializers.DictField(child=serializers.IntegerField())
    checked_at = serializers.DateTimeField()
    restricted = serializers.BooleanField()
    owner_basis = serializers.CharField()
    ordering = serializers.CharField()
    can_upload = serializers.BooleanField()
    can_create_issue = serializers.BooleanField()


class TodayWorkView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(parameters=[TodayWorkQuerySerializer], responses=TodayWorkPageSerializer)
    def get(self, request):
        options = TodayWorkQuerySerializer(data=request.query_params)
        options.is_valid(raise_exception=True)
        return Response(today_work_page(request.user, options.validated_data))
