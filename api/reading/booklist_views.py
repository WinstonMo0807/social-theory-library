from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response

from . import booklists
from .research_serializers import EvidenceReferenceInput, PlanPolicyInput


class ListQuery(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, max_value=10000, default=1)
    q = serializers.CharField(max_length=180, allow_blank=True, default="")
    kind = serializers.ChoiceField(choices=["", "book", "journal_article", "journal_issue", "thesis", "report"], default="")
    order = serializers.ChoiceField(choices=["manual", "newest"], default="manual")
    trash = serializers.BooleanField(default=False)


class ListSummary(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    description = serializers.CharField()
    goal = serializers.CharField()
    tags = serializers.ListField(child=serializers.CharField())
    version = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    item_count = serializers.IntegerField()


class ListItem(serializers.Serializer):
    from catalog.serializers import WorkCardSerializer
    id = serializers.UUIDField()
    work_id = serializers.UUIDField()
    order = serializers.IntegerField()
    work = WorkCardSerializer(allow_null=True)
    created_at = serializers.DateTimeField()
    removed_at = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField(allow_null=True)
    progress_ratio = serializers.FloatField(allow_null=True)
    reader_url = serializers.CharField(allow_null=True)


class ListDirectory(serializers.Serializer):
    owner_id = serializers.CharField()
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    results = ListSummary(many=True)


class ListWorkspace(serializers.Serializer):
    owner_id = serializers.CharField()
    list = ListSummary()
    items = ListItem(many=True)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    active_count = serializers.IntegerField()
    trash_count = serializers.IntegerField()


class ListCommand(serializers.Serializer):
    list_id = serializers.UUIDField()
    request_id = serializers.UUIDField()
    expected_version = serializers.CharField(max_length=100)
    action = serializers.ChoiceField(choices=["create", "edit", "add", "remove", "restore", "purge", "move", "delete"])
    title = serializers.CharField(max_length=240, required=False)
    description = serializers.CharField(max_length=6000, allow_blank=True, required=False)
    goal = serializers.CharField(max_length=2000, allow_blank=True, required=False)
    tags = serializers.ListField(child=serializers.CharField(max_length=40), max_length=12, required=False)
    work_id = serializers.UUIDField(required=False)
    item_id = serializers.UUIDField(required=False)
    item_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=100, required=False)
    direction = serializers.ChoiceField(choices=[-1, 1], required=False)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError("书单操作包含不支持的字段。")
        return super().to_internal_value(data)

    def validate(self, data):
        fields = {"create": ("title", "description"), "edit": ("title", "description", "goal", "tags"),
            "add": ("work_id",), "move": ("item_id", "direction"), "remove": ("item_ids",),
            "restore": ("item_ids",), "purge": ("item_ids",), "delete": ()}[data["action"]]
        if set(data) - {"list_id", "request_id", "expected_version", "action", *fields}:
            raise serializers.ValidationError("本操作包含无关字段。")
        required = ("title",) if data["action"] == "create" else () if data["action"] == "edit" else fields
        if any(field not in data for field in required):
            raise serializers.ValidationError("操作信息不完整。")
        if "item_ids" in data and len(data["item_ids"]) != len(set(data["item_ids"])):
            raise serializers.ValidationError("不要重复选择同一作品。")
        if "tags" in data:
            data["tags"] = list(dict.fromkeys(data["tags"]))
        return data


class ListReceipt(serializers.Serializer):
    request_id = serializers.UUIDField()


class ListResult(serializers.Serializer):
    owner_id = serializers.CharField()
    id = serializers.UUIDField()
    exists = serializers.BooleanField()
    receipt = ListReceipt()


class ListLookup(serializers.Serializer):
    list_id = serializers.UUIDField()
    request_id = serializers.UUIDField()


class CitationListInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    expected_version = serializers.CharField(max_length=100)
    edition_id = serializers.UUIDField()
    reference = EvidenceReferenceInput(required=False)
    save_excerpt = serializers.BooleanField(default=True)
    note = serializers.CharField(max_length=200, allow_blank=True, default="", trim_whitespace=False)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError("保存请求包含不支持的字段。")
        return super().to_internal_value(data)


class CitationListOutput(serializers.Serializer):
    owner_id = serializers.CharField()
    list_id = serializers.UUIDField()
    request_id = serializers.UUIDField()
    exists = serializers.BooleanField()
    undone = serializers.BooleanField()
    note_ids = serializers.ListField(child=serializers.UUIDField())
    undo_token = serializers.CharField(allow_null=True)


class CitationListUndo(serializers.Serializer):
    token = serializers.CharField(max_length=12000)


class ListExport(serializers.Serializer):
    expected_version = serializers.CharField(max_length=100)
    format = serializers.ChoiceField(choices=["pdf", "bibtex", "ris", "csv"])
    include_progress = serializers.BooleanField(default=False)
    include_notes = serializers.BooleanField(default=False)
    include_covers = serializers.BooleanField(default=False)
    item_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=200, required=False)

    def validate_item_ids(self, values):
        if len(values) != len(set(values)):
            raise serializers.ValidationError("不要重复选择作品。")
        return values

    def validate(self, data):
        if data["include_covers"] and data["format"] != "pdf":
            raise serializers.ValidationError({"include_covers": "封面仅能嵌入PDF导出。"})
        return data


class ListPlanPreviewInput(serializers.Serializer):
    expected_version = serializers.CharField(max_length=100)
    item_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=200, required=False)

    def validate_item_ids(self, values):
        if len(values) != len(set(values)):
            raise serializers.ValidationError("不要重复选择作品。")
        return values


class ListPlanInput(ListPlanPreviewInput, PlanPolicyInput):
    request_id = serializers.UUIDField()
    source_token = serializers.RegexField(r"^[0-9a-f]{64}$")
    goal = serializers.CharField(min_length=2, max_length=1200)
    background = serializers.CharField(max_length=4000, allow_blank=True, required=False)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError("书单计划包含不支持的字段。")
        return super().to_internal_value(data)


class ListPlanSource(serializers.Serializer):
    item_id = serializers.UUIDField()
    work_id = serializers.UUIDField()
    title = serializers.CharField()
    reference = EvidenceReferenceInput(allow_null=True)
    source_status = serializers.ChoiceField(choices=["available", "unavailable"])
    reader_url = serializers.CharField(allow_null=True)
    catalog_revision_id = serializers.UUIDField(allow_null=True)


class ListPlanPreview(serializers.Serializer):
    owner_id = serializers.CharField()
    list_id = serializers.UUIDField()
    expected_version = serializers.CharField()
    source_token = serializers.CharField()
    goal = serializers.CharField()
    items = ListPlanSource(many=True)
    ready = serializers.BooleanField()


class ListPlanResult(serializers.Serializer):
    owner_id = serializers.CharField()
    request_id = serializers.UUIDField()
    record_id = serializers.UUIDField(allow_null=True)
    deleted = serializers.BooleanField()


OWNER = OpenApiParameter("X-Reader-Owner", str, location=OpenApiParameter.HEADER, required=True)


class BooklistActions:
    def list_owner(self, request):
        if request.headers.get("X-Reader-Owner") != str(request.user.pk):
            raise PermissionDenied("请重新核对当前书单所属账户。")

    @extend_schema(parameters=[OWNER, OpenApiParameter("request_id", str, required=True)], responses=CitationListOutput)
    @action(detail=True, methods=["get"], url_path="citation")
    def citation(self, request, pk=None):
        from . import citation_booklists, research
        self.list_owner(request)
        return Response(citation_booklists.lookup(request.user, research.identifier(pk),
            research.identifier(request.query_params.get("request_id"), "request_id")))

    @citation.mapping.post
    @extend_schema(parameters=[OWNER], request=CitationListInput, responses=CitationListOutput)
    def save_citation(self, request, pk=None):
        from . import citation_booklists, research
        self.list_owner(request)
        data = CitationListInput(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(citation_booklists.save(request, research.identifier(pk), data.validated_data))

    @extend_schema(parameters=[OWNER], request=CitationListUndo, responses=CitationListOutput)
    @action(detail=True, methods=["post"], url_path="undo-citation")
    def undo_citation(self, request, pk=None):
        from . import citation_booklists, research
        self.list_owner(request)
        data = CitationListUndo(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(citation_booklists.undo(request.user, research.identifier(pk), data.validated_data["token"]))

    @extend_schema(parameters=[OWNER, ListPlanPreviewInput], responses=ListPlanPreview)
    @action(detail=True, methods=["get"], url_path="plan-preview")
    def plan_preview(self, request, pk=None):
        from .booklist_plans import preview
        self.list_owner(request)
        data = ListPlanPreviewInput(data=request.query_params)
        data.is_valid(raise_exception=True)
        return Response(preview(request.user, pk, **data.validated_data))

    @extend_schema(parameters=[OWNER], request=ListPlanInput, responses=ListPlanResult)
    @action(detail=True, methods=["post"], url_path="create-plan")
    def create_plan(self, request, pk=None):
        from .booklist_plans import create
        self.list_owner(request)
        data = ListPlanInput(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(create(request.user, pk, data.validated_data))

    @extend_schema(parameters=[OWNER, OpenApiParameter("request_id", str, required=True)], responses=ListPlanResult)
    @action(detail=False, methods=["get"], url_path="plan-receipt")
    def plan_receipt(self, request):
        from . import research
        from .booklist_plans import lookup
        self.list_owner(request)
        return Response(lookup(request.user, research.identifier(request.query_params.get("request_id"), "request_id")))

    @extend_schema(parameters=[OWNER], request=ListExport, responses={(200, "application/octet-stream"): bytes})
    @action(detail=True, methods=["post"])
    def export(self, request, pk=None):
        from .booklist_exports import download
        self.list_owner(request)
        data = ListExport(data=request.data)
        data.is_valid(raise_exception=True)
        return download(request, self.get_object(), data.validated_data)

    @extend_schema(parameters=[OWNER, ListQuery], responses=ListDirectory)
    @action(detail=False, methods=["get"])
    def directory(self, request):
        self.list_owner(request)
        data = ListQuery(data=request.query_params)
        data.is_valid(raise_exception=True)
        query = data.validated_data
        rows = self.get_queryset().prefetch_related(None).order_by("-updated_at", "-id")
        if query["q"]:
            rows = rows.filter(title__icontains=query["q"])
        count, page = rows.count(), query["page"]
        if page > 1 and (page - 1) * 20 >= count:
            raise NotFound("这一页已没有书单，请返回第一页。")
        return Response({"owner_id": str(request.user.pk), "count": count, "page": page,
            "total_pages": max(1, (count + 19) // 20), "results": [booklists.summary(row) for row in rows[(page - 1) * 20:page * 20]]})

    @extend_schema(parameters=[OWNER, ListQuery], responses=ListWorkspace)
    @action(detail=True, methods=["get"])
    def workspace(self, request, pk=None):
        self.list_owner(request)
        query = ListQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(booklists.workspace(request, self.get_object(), query.validated_data))

    @extend_schema(parameters=[OWNER], request=ListCommand, responses=ListResult)
    @action(detail=False, methods=["post"])
    def command(self, request):
        self.list_owner(request)
        data = ListCommand(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(booklists.command(request.user, data.validated_data))

    @extend_schema(parameters=[OWNER, ListLookup], responses=ListResult)
    @action(detail=False, methods=["get"])
    def receipt(self, request):
        self.list_owner(request)
        data = ListLookup(data=request.query_params)
        data.is_valid(raise_exception=True)
        pk, request_id = data.validated_data["list_id"], data.validated_data["request_id"]
        receipt = booklists.receipt_for(request.user, pk, request_id)
        if receipt is None:
            raise NotFound("尚未找到原操作回执，可以使用原请求重试。")
        return Response(booklists.result(request.user, pk, receipt))
