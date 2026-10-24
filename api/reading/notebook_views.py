from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.private_responses import PrivateAccountResponses
from . import notebook
from .privacy_serializers import PrivacyTargetInput


class NotebookQuery(serializers.Serializer):
    q = serializers.CharField(max_length=180, allow_blank=True, default="")
    page = serializers.IntegerField(min_value=1, default=1)
    kind = serializers.ChoiceField(choices=["all", "note", "excerpt", "bookmark"], default="all")
    order = serializers.ChoiceField(choices=["newest", "oldest"], default="newest")
    work = serializers.UUIDField(required=False)
    asset = serializers.UUIDField(required=False)
    project = serializers.UUIDField(required=False)
    booklist = serializers.UUIDField(required=False)
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)

    def validate(self, data):
        if data.get("start") and data.get("end") and data["end"] < data["start"]:
            raise serializers.ValidationError("结束日期不能早于开始日期。")
        return data


class NotebookPage(serializers.Serializer):
    owner_id = serializers.CharField()
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    results = serializers.ListField(child=serializers.DictField())


class NotebookRecord(serializers.Serializer):
    owner_id = serializers.CharField()
    id = serializers.UUIDField()
    category = serializers.CharField()
    revision = serializers.CharField()
    key = serializers.CharField()
    kind = serializers.CharField()
    asset_id = serializers.UUIDField()
    page_id = serializers.UUIDField()
    pdf_page = serializers.IntegerField()
    work = serializers.DictField()
    body = serializers.CharField(allow_blank=True)
    label = serializers.CharField(allow_blank=True)
    tags = serializers.ListField(child=serializers.CharField())
    saved_quote = serializers.CharField(allow_blank=True)
    source = serializers.DictField()
    notice = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class NotebookEdit(serializers.Serializer):
    expected_version = serializers.CharField(max_length=80)
    body = serializers.CharField(allow_blank=True, trim_whitespace=False, required=False)
    tags = serializers.ListField(child=serializers.CharField(max_length=40, allow_blank=False), max_length=12, required=False)
    label = serializers.CharField(max_length=240, allow_blank=True, required=False)


class NotebookTargetsInput(serializers.Serializer):
    targets = PrivacyTargetInput(many=True)

    def validate_targets(self, value):
        if not 1 <= len(value) <= 20 or any(row["category"] not in notebook.MODELS for row in value):
            raise serializers.ValidationError("请选择本页1至20条阅读记录。")
        if len({(row["category"], str(row["id"])) for row in value}) != len(value):
            raise serializers.ValidationError("同一记录不能重复选择。")
        return value


class NotebookProjectInput(NotebookTargetsInput):
    request_id = serializers.UUIDField()
    project_id = serializers.UUIDField()
    expected_revision = serializers.IntegerField(min_value=1)
    note = serializers.CharField(max_length=200, allow_blank=True, required=False)


class NotebookExportInput(NotebookTargetsInput):
    format = serializers.ChoiceField(choices=["pdf", "markdown", "bibtex", "ris"])
    include_quotes = serializers.BooleanField(default=False)
    include_notes = serializers.BooleanField(default=False)


class NotebookProjectOutput(serializers.Serializer):
    owner_id = serializers.CharField()
    project_id = serializers.UUIDField()
    revision = serializers.IntegerField(allow_null=True)
    exists = serializers.BooleanField(required=False)


class NotebookProjectReceiptQuery(serializers.Serializer):
    project_id = serializers.UUIDField()
    request_id = serializers.UUIDField()


class BookmarkNoteInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    expected_version = serializers.CharField(max_length=80)
    body = serializers.CharField(max_length=500, allow_blank=False, trim_whitespace=False)
    tags = serializers.ListField(child=serializers.CharField(max_length=40, allow_blank=False), max_length=12, required=False)


class BookmarkNoteReceiptQuery(serializers.Serializer):
    request_id = serializers.UUIDField()


class BookmarkNoteReceipt(serializers.Serializer):
    owner_id = serializers.CharField()
    id = serializers.UUIDField()
    exists = serializers.BooleanField()
    retired = serializers.BooleanField()
    record = NotebookRecord(allow_null=True)


class NotebookBase(PrivateAccountResponses, APIView):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.headers.get("X-Reader-Owner") != str(request.user.pk):
            raise PermissionDenied("请重新核对当前登录账户。")


class NotebookView(NotebookBase):
    @extend_schema(operation_id="reader_notebook_list", parameters=[NotebookQuery], responses=NotebookPage)
    def get(self, request):
        query = NotebookQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(notebook.listing(request.user, query.validated_data))


class NotebookExportView(NotebookBase):
    @extend_schema(request=NotebookExportInput, responses={(200, "application/octet-stream"): bytes})
    def post(self, request):
        from .notebook_exports import download
        data = NotebookExportInput(data=request.data)
        data.is_valid(raise_exception=True)
        return download(request.user, data.validated_data)


class NotebookChoicesView(NotebookBase):
    @extend_schema(parameters=[NotebookQuery], responses=NotebookPage)
    def get(self, request, kind):
        if kind not in {"works", "projects"}:
            raise ValidationError("筛选类型无效。")
        query = NotebookQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(notebook.choices(request.user, kind, query.validated_data["page"]))


class NotebookDetailView(NotebookBase):
    def category(self, value):
        if value not in notebook.MODELS:
            raise ValidationError("记录类型无效。")
        return value

    @extend_schema(responses=NotebookRecord)
    def get(self, request, category, pk):
        category = self.category(category)
        return Response(notebook.record(request.user, category, notebook.owned(request.user, category, pk)))

    @extend_schema(request=NotebookEdit, responses=NotebookRecord)
    def patch(self, request, category, pk):
        data = NotebookEdit(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(notebook.edit(request.user, self.category(category), pk, data.validated_data))


class NotebookProjectView(NotebookBase):
    @extend_schema(parameters=[NotebookProjectReceiptQuery], responses=NotebookProjectOutput)
    def get(self, request):
        data = NotebookProjectReceiptQuery(data=request.query_params)
        data.is_valid(raise_exception=True)
        return Response(notebook.project_receipt(request.user, **data.validated_data))

    @extend_schema(request=NotebookProjectInput, responses=NotebookProjectOutput)
    def post(self, request):
        data = NotebookProjectInput(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(notebook.add_to_project(request.user, data.validated_data))


class NotebookBookmarkNoteView(NotebookBase):
    @extend_schema(parameters=[BookmarkNoteReceiptQuery], responses=BookmarkNoteReceipt)
    def get(self, request, pk):
        data = BookmarkNoteReceiptQuery(data=request.query_params)
        data.is_valid(raise_exception=True)
        return Response(notebook.bookmark_note_receipt(request.user, pk, data.validated_data["request_id"]))

    @extend_schema(request=BookmarkNoteInput, responses=NotebookRecord)
    def post(self, request, pk):
        data = BookmarkNoteInput(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(notebook.add_bookmark_note(request, pk, data.validated_data))
