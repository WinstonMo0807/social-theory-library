from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.private_responses import PrivateAccountResponses
from . import reader_center
from .serializers import ReadingProgressSerializer
from .privacy_serializers import PrivacyRequestStopInput
from .sharing_serializers import ShareWorkSummary


class ReaderCenterQuery(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["all", *reader_center.KINDS], default="all")
    q = serializers.CharField(max_length=180, allow_blank=True, default="")
    order = serializers.ChoiceField(choices=["newest", "oldest"], default="newest")
    page = serializers.IntegerField(min_value=1, default=1)
    overview = serializers.BooleanField(default=True)
    visibility = serializers.ChoiceField(choices=["all", "active", "archived"], default="all")


class ReaderMaterialOutput(serializers.Serializer):
    source = ShareWorkSummary(allow_null=True, required=False)
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
    editable_title = serializers.CharField(allow_blank=True)
    source_revision = serializers.CharField()
    preference_revision = serializers.IntegerField(min_value=0)


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


class ReaderMaterialTarget(serializers.Serializer):
    kind = serializers.ChoiceField(choices=list(reader_center.KINDS))
    id = serializers.UUIDField()
    revision = serializers.CharField(max_length=80)
    title = serializers.CharField(max_length=240, required=False)


class ReaderMaterialCommand(serializers.Serializer):
    request_id = serializers.UUIDField()
    action = serializers.ChoiceField(choices=["rename", "archive", "restore"])
    targets = ReaderMaterialTarget(many=True, allow_empty=False, max_length=100)


class ReaderMaterialReceipt(serializers.Serializer):
    owner_id = serializers.CharField()
    request_id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    action = serializers.CharField(allow_blank=True)
    applied = serializers.ListField(child=serializers.DictField())


class ReaderMaterialCommandView(PrivateAccountResponses, APIView):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.headers.get("X-Reader-Owner") != str(request.user.pk):
            raise PermissionDenied("请从当前账户的资料列表操作本人资料。")

    @extend_schema(operation_id="reader_material_command", request=ReaderMaterialCommand, responses=ReaderMaterialReceipt)
    def post(self, request):
        from .reader_material_commands import command
        values = ReaderMaterialCommand(data=request.data)
        values.is_valid(raise_exception=True)
        return Response(command(request.user, values.validated_data))


class ReaderMaterialReceiptView(ReaderMaterialCommandView):
    @extend_schema(operation_id="reader_material_receipt", responses=ReaderMaterialReceipt)
    def get(self, request, request_id):
        from .reader_material_commands import receipt
        return Response(receipt(request.user, request_id))

    @extend_schema(operation_id="reader_material_stop_pending", request=PrivacyRequestStopInput, responses=ReaderMaterialReceipt)
    def post(self, request, request_id):
        from .reader_material_commands import stop
        values = PrivacyRequestStopInput(data=request.data)
        values.is_valid(raise_exception=True)
        return Response(stop(request.user, request_id))
