from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from . import research_replay, research_replay_tree, research_replay_history


def owner(request):
    if request.headers.get("X-Reader-Owner") != str(request.user.pk):
        raise PermissionDenied("登录账户需重新核对，原研究保留。")


class ReplayQuery(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, default=1)
    turn_id = serializers.UUIDField(required=False)
    compare_id = serializers.UUIDField(required=False)


class ReplayOutput(serializers.Serializer):
    owner_id = serializers.CharField()
    project = serializers.DictField(required=False)
    project_id = serializers.UUIDField(required=False)
    project_revision = serializers.IntegerField(required=False)
    count = serializers.IntegerField(required=False)
    page = serializers.IntegerField(required=False)
    total_pages = serializers.IntegerField(required=False)
    current_turn_id = serializers.UUIDField(allow_null=True, required=False)
    results = serializers.ListField(child=serializers.DictField(), required=False)
    turn = serializers.DictField(required=False)
    scope = serializers.DictField(required=False)
    materials = serializers.ListField(child=serializers.DictField(), required=False)
    evidence = serializers.ListField(child=serializers.DictField(), required=False)
    added_ids = serializers.ListField(child=serializers.CharField(), required=False)
    unchanged_ids = serializers.ListField(child=serializers.CharField(), required=False)
    removed = serializers.ListField(child=serializers.DictField(), required=False)
    compared = serializers.DictField(allow_null=True, required=False)
    scope_changed = serializers.BooleanField(required=False)
    previous_scope = serializers.DictField(allow_null=True, required=False)
    notes = serializers.CharField(allow_blank=True, required=False)
    tags = serializers.ListField(child=serializers.CharField(), required=False)
    snapshot_notes = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    snapshot_title = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    unavailable_count = serializers.IntegerField(required=False)
    notice = serializers.CharField(required=False)


class ReplayEdit(serializers.Serializer):
    turn_id = serializers.UUIDField()
    expected_revision = serializers.IntegerField(min_value=1)
    title = serializers.CharField(max_length=240, required=False)
    notes = serializers.CharField(max_length=20000, allow_blank=True, trim_whitespace=False, required=False)
    tags = serializers.ListField(child=serializers.CharField(max_length=40), max_length=12, required=False)
    restore_id = serializers.UUIDField(required=False)

    def validate_tags(self, values):
        from unicodedata import normalize
        result = [normalize("NFKC", value).strip() for value in values]
        if any(not value or len(value) > 40 for value in result) or len({value.casefold() for value in result}) != len(result):
            raise serializers.ValidationError("主题标签不可为空或重复，每项最多40字。")
        return result

    def validate(self, values):
        if set(self.initial_data) - set(self.fields):
            raise serializers.ValidationError("回放编辑含有不支持的字段。")
        fields = {"title", "notes", "tags"}.intersection(values)
        if values.get("restore_id") and fields:
            raise serializers.ValidationError("历史恢复和新的文字编辑需分别确认。")
        if not fields and not values.get("restore_id"):
            raise serializers.ValidationError("请提供要保存的轮次名称、主题标签或回放笔记。")
        return values


class ReplayHistoryQuery(serializers.Serializer):
    turn_id = serializers.UUIDField()
    page = serializers.IntegerField(min_value=1, default=1)
    revision_id = serializers.UUIDField(required=False)


class ReplayHistoryEntry(serializers.Serializer):
    id = serializers.UUIDField()
    revision = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=["baseline", "edit", "restore"])
    recorded_at = serializers.DateTimeField()
    source_updated_at = serializers.DateTimeField(allow_null=True)
    title = serializers.CharField(allow_blank=True)
    tags = serializers.ListField(child=serializers.CharField())
    note_length = serializers.IntegerField()
    restored_from = serializers.UUIDField(allow_null=True)
    notes = serializers.CharField(allow_blank=True, required=False)


class ReplayHistoryOutput(serializers.Serializer):
    owner_id = serializers.CharField()
    project_id = serializers.UUIDField()
    turn_id = serializers.UUIDField()
    current_revision = serializers.IntegerField()
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    results = ReplayHistoryEntry(many=True)
    selected = ReplayHistoryEntry(allow_null=True)
    notice = serializers.CharField()


class ReplayFork(serializers.Serializer):
    turn_id = serializers.UUIDField()
    expected_revision = serializers.IntegerField(min_value=1)
    expected_project_revision = serializers.IntegerField(min_value=1)
    request_id = serializers.UUIDField()
    title = serializers.CharField(max_length=50)
    question = serializers.CharField(max_length=200, allow_blank=True, required=False)
    reference_ids = serializers.ListField(child=serializers.CharField(max_length=600), min_length=1, max_length=400)
    include_notes = serializers.BooleanField(default=False)


class ReplayReceiptQuery(serializers.Serializer):
    request_id = serializers.UUIDField()


class ReplayForkStop(ReplayReceiptQuery):
    action = serializers.ChoiceField(choices=["cancel_pending"])

    def validate(self, data):
        if set(self.initial_data) != set(self.fields):
            raise serializers.ValidationError("仅接受停止原分支创建请求。")
        return data


class ReplayForkOutput(serializers.Serializer):
    owner_id = serializers.CharField()
    request_id = serializers.UUIDField()
    project_id = serializers.UUIDField(allow_null=True)
    deleted = serializers.BooleanField()
    state = serializers.ChoiceField(choices=["applied", "cancelled"])


class ReplayTreeQuery(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, default=1)
    parent_id = serializers.UUIDField(required=False)
    view = serializers.ChoiceField(choices=["turns", "projects"], default="turns")


class ReplayTreeOutput(serializers.Serializer):
    owner_id = serializers.CharField()
    project_id = serializers.UUIDField()
    parent_id = serializers.UUIDField(allow_null=True, required=False)
    parent = serializers.DictField(allow_null=True, required=False)
    origin_unavailable = serializers.BooleanField(required=False)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    results = serializers.ListField(child=serializers.DictField())


class ReplayActions:
    @extend_schema(parameters=[ReplayHistoryQuery], responses=ReplayHistoryOutput)
    @action(detail=True, methods=["get"], url_path="replay-history")
    def replay_history(self, request, pk=None):
        owner(request)
        query = ReplayHistoryQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(research_replay_history.history(request.user, pk, **query.validated_data))

    @extend_schema(parameters=[ReplayTreeQuery], responses=ReplayTreeOutput)
    @action(detail=True, methods=["get"], url_path="replay-tree")
    def replay_tree(self, request, pk=None):
        owner(request)
        query = ReplayTreeQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        if values["view"] == "projects":
            return Response(research_replay_tree.project_links(request.user, pk, values["page"]))
        return Response(research_replay_tree.turn_tree(request.user, pk, values.get("parent_id"), values["page"]))

    @extend_schema(methods=["GET"], parameters=[ReplayQuery], responses=ReplayOutput)
    @extend_schema(methods=["PATCH"], request=ReplayEdit, responses=ReplayOutput)
    @action(detail=True, methods=["get", "patch"], url_path="replay")
    def replay(self, request, pk=None):
        owner(request)
        if request.method == "PATCH":
            data = ReplayEdit(data=request.data)
            data.is_valid(raise_exception=True)
            values = dict(data.validated_data)
            turn_id = values.pop("turn_id")
            return Response(research_replay.edit_turn(request.user, pk, turn_id, values))
        query = ReplayQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        if values.get("turn_id"):
            return Response(research_replay.detail(request.user, pk, values["turn_id"], values.get("compare_id")))
        return Response(research_replay.timeline(request.user, pk, values["page"]))

    @extend_schema(request=ReplayFork, responses=ReplayForkOutput)
    @action(detail=True, methods=["post"], url_path="fork-from-replay")
    def fork_from_replay(self, request, pk=None):
        owner(request)
        data = ReplayFork(data=request.data)
        data.is_valid(raise_exception=True)
        values = dict(data.validated_data)
        turn_id = values.pop("turn_id")
        return Response(research_replay.fork_project(request.user, pk, turn_id, values))

    @extend_schema(methods=["GET"], parameters=[ReplayReceiptQuery], responses=ReplayForkOutput)
    @extend_schema(methods=["POST"], request=ReplayForkStop, responses=ReplayForkOutput)
    @action(detail=False, methods=["get", "post"], url_path="replay-fork-receipt")
    def replay_fork_receipt(self, request):
        owner(request)
        if request.method == "POST":
            data = ReplayForkStop(data=request.data)
            data.is_valid(raise_exception=True)
            return Response(research_replay.stop_fork(request.user, data.validated_data["request_id"]))
        data = ReplayReceiptQuery(data=request.query_params)
        data.is_valid(raise_exception=True)
        return Response(research_replay.fork_receipt(request.user, **data.validated_data))
