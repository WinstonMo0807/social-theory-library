from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.private_responses import PrivateAccountResponses
from . import reader_center
from .serializers import ReadingProgressSerializer


class ReaderCenterQuery(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["all", *reader_center.KINDS], default="all")
    q = serializers.CharField(max_length=180, allow_blank=True, default="")
    order = serializers.ChoiceField(choices=["newest", "oldest"], default="newest")
    page = serializers.IntegerField(min_value=1, default=1)
    overview = serializers.BooleanField(default=True)


class ReaderMaterialOutput(serializers.Serializer):
    id = serializers.UUIDField()
    key = serializers.CharField()
    kind = serializers.ChoiceField(choices=list(reader_center.KINDS))
    kind_label = serializers.CharField()
    title = serializers.CharField()
    question = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    href = serializers.CharField()
    updated_at = serializers.DateTimeField()
    revision = serializers.CharField()


class ReaderPendingOutput(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField()
    question = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    updated_at = serializers.DateTimeField()
    href = serializers.CharField()


class ReaderCenterOutput(serializers.Serializer):
    owner_id = serializers.CharField()
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    counts = serializers.DictField(child=serializers.IntegerField())
    results = ReaderMaterialOutput(many=True)
    recent_reading = ReadingProgressSerializer(many=True, required=False)
    pending_tasks = ReaderPendingOutput(many=True, required=False)


class ReaderCenterView(PrivateAccountResponses, APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ReaderCenterOutput

    @extend_schema(parameters=[ReaderCenterQuery], responses=ReaderCenterOutput)
    def get(self, request):
        query = ReaderCenterQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        options = dict(query.validated_data)
        overview = options.pop("overview")
        data = reader_center.materials(request.user, **options)
        if overview:
            data.update(recent_reading=reader_center.recent_reading(request), pending_tasks=reader_center.pending_tasks(request.user))
        return Response(data)
