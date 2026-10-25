from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, PolymorphicProxySerializer, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.capabilities import Capability, has_capability
from common.private_responses import PrivateAccountResponses
from . import reader_groups, reader_shares, research, share_scope
from .sharing_models import ReaderGroupInvite, ReaderShare, ReaderShareNotice
from .models import ReadingList, ResearchProject

from . import sharing_serializers as output

OWNER = OpenApiParameter("X-Reader-Owner", str, location=OpenApiParameter.HEADER, required=True)


class StrictInput(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError("请求包含不支持的字段。")
        return super().to_internal_value(data)


class GroupCreateInput(StrictInput):
    request_id = serializers.UUIDField()
    title = serializers.CharField(max_length=80)
    kind = serializers.ChoiceField(choices=["campus", "team"])


class GroupCommandInput(StrictInput):
    request_id = serializers.UUIDField()
    expected_revision = serializers.IntegerField(min_value=1)
    action = serializers.ChoiceField(choices=["rename", "archive", "leave", "remove", "invite", "revoke_invite"])
    title = serializers.CharField(max_length=80, required=False)
    username = serializers.CharField(max_length=150, required=False)
    membership_id = serializers.UUIDField(required=False)
    invitation_id = serializers.UUIDField(required=False)

    def validate(self, data):
        extra = {"rename": {"title"}, "archive": set(), "leave": set(), "remove": {"membership_id"},
            "invite": {"username"}, "revoke_invite": {"invitation_id"}}[data["action"]]
        if set(data) != {"request_id", "expected_revision", "action", *extra}:
            raise serializers.ValidationError("小组操作的输入不完整或包含无关字段。")
        return data


class GroupAcceptInput(StrictInput):
    token = serializers.CharField(min_length=32, max_length=80, required=False)
    invitation_id = serializers.UUIDField(required=False)

    def validate(self, data):
        if len(data) != 1:
            raise serializers.ValidationError("请提供邀请链接或本人待处理邀请标识。")
        return data


class ShareSelectionInput(StrictInput):
    source_kind = serializers.ChoiceField(choices=["research", "booklist"])
    source_id = serializers.UUIDField()
    expected_version = serializers.CharField(max_length=100, required=False)
    section = serializers.ChoiceField(choices=share_scope.SECTIONS)
    page = serializers.IntegerField(min_value=1, max_value=10000, default=1)


class ShareIncludedSourceInput(StrictInput):
    source_kind = serializers.ChoiceField(choices=["research", "booklist"])
    source_id = serializers.UUIDField()
    expected_version = serializers.CharField(max_length=100)
    questions = serializers.ListField(child=serializers.CharField(max_length=200), max_length=20, default=list)
    materials = serializers.ListField(child=serializers.CharField(max_length=200), max_length=20, default=list)
    notes = serializers.ListField(child=serializers.CharField(max_length=200), max_length=20, default=list)


class SharePreviewInput(ShareIncludedSourceInput):
    additional_sources = ShareIncludedSourceInput(many=True, max_length=4, required=False)
    destination = serializers.ChoiceField(choices=["group", "public", "proposal"])
    group_id = serializers.UUIDField(required=False)
    group_revision = serializers.IntegerField(min_value=1, required=False)
    member_ids = serializers.ListField(child=serializers.RegexField(r"^[1-9][0-9]{0,19}$"), min_length=1, max_length=100, required=False)
    message = serializers.CharField(max_length=200, allow_blank=True, default="", trim_whitespace=False)
    expires_days = serializers.IntegerField(min_value=1, max_value=365, default=30)

    def validate(self, data):
        share_scope.source_specs(data)
        for key in (*share_scope.SECTIONS, "member_ids"):
            values = data.get(key, [])
            if len(values) != len(set(values)):
                raise serializers.ValidationError("同一内容或接收成员不能重复选择。")
        if data["destination"] == "group" and not all(key in data for key in ("group_id", "group_revision", "member_ids")):
            raise serializers.ValidationError("请选择小组及其当前成员。")
        if data["destination"] != "group" and any(key in data for key in ("group_id", "group_revision", "member_ids")):
            raise serializers.ValidationError("当前目的地不能包含小组信息。")
        return data


class ShareCreateInput(SharePreviewInput):
    request_id = serializers.UUIDField()
    preview_hash = serializers.RegexField(r"^[0-9a-f]{64}$")
    confirmed = serializers.BooleanField()


class ShareStopInput(StrictInput):
    request_id = serializers.UUIDField()
    action = serializers.ChoiceField(choices=['cancel_pending'])


class ShareCommandInput(StrictInput):
    action = serializers.ChoiceField(choices=["revoke", "notify", "review"])
    expected_revision = serializers.IntegerField(min_value=1)
    state = serializers.ChoiceField(choices=["submitted", "considering", "declined"], required=False)

    def validate(self, data):
        if (data["action"] == "review") != ("state" in data):
            raise serializers.ValidationError("请按当前操作填写审核状态。")
        return data


class NoticeReadInput(StrictInput):
    ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=100)


class PageQuery(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, max_value=10000, default=1)
    invitation_page = serializers.IntegerField(min_value=1, max_value=10000, default=1)
    tab = serializers.ChoiceField(choices=["own", "received", "proposals"], default="own")
    kind = serializers.ChoiceField(choices=["", "campus", "team"], default="")


class ShareSourcesQuery(serializers.Serializer):
    source_kind = serializers.ChoiceField(choices=["research", "booklist"])
    page = serializers.IntegerField(min_value=1, max_value=10000, default=1)


def parsed(cls, data):
    serializer = cls(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def page(rows, number, mapper):
    count = len(rows) if isinstance(rows, list) else rows.count()
    start = (number - 1) * 20
    if number > 1 and start >= count:
        raise NotFound("这一页已没有记录，请返回第一页。")
    return {"page": number, "count": count, "total_pages": max(1, (count + 19) // 20),
        "results": [mapper(row) for row in rows[start:start + 20]]}


class SharingPrivateView(PrivateAccountResponses, APIView):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.headers.get("X-Reader-Owner") != str(request.user.pk):
            raise PermissionDenied("请重新核对当前读者账户。")


class ReaderGroupsView(SharingPrivateView):
    @extend_schema(parameters=[OWNER, PageQuery], responses=output.GroupDirectory, operation_id="reader_groups_list")
    def get(self, request):
        query = parsed(PageQuery, request.query_params)
        groups = reader_groups.accessible(request.user).order_by("-updated_at", "-id")
        if query["kind"]:
            groups = groups.filter(kind=query["kind"])
        invites = ReaderGroupInvite.objects.select_related("user", "group").filter(user=request.user, group__archived=False,
            group__user__is_active=True, accepted_at__isnull=True, revoked_at__isnull=True, expires_at__gt=timezone.now()).order_by("-created_at", "-id")
        return Response({"owner_id": str(request.user.pk), "groups": page(groups, query["page"], lambda row: reader_groups.summary(row, request.user)),
            "invitations": page(invites, query["invitation_page"], lambda row: {**reader_groups.invite_output(row),
                "title": research.unpack(row.group).get("title", "小组")})})

    @extend_schema(parameters=[OWNER], request=GroupCreateInput, responses=output.GroupResult, operation_id="reader_groups_create")
    def post(self, request):
        return Response(reader_groups.create(request.user, parsed(GroupCreateInput, request.data)))


class ReaderGroupDetailView(SharingPrivateView):
    @extend_schema(parameters=[OWNER], responses=output.GroupDetail, operation_id="reader_groups_detail")
    def get(self, request, pk):
        return Response(reader_groups.detail(request.user, pk))

    @extend_schema(parameters=[OWNER], request=GroupCommandInput, responses=output.GroupResult, operation_id="reader_groups_command")
    def post(self, request, pk):
        return Response(reader_groups.command(request.user, pk, parsed(GroupCommandInput, request.data)))


class ReaderGroupAcceptView(SharingPrivateView):
    @extend_schema(parameters=[OWNER], request=GroupAcceptInput, responses=output.GroupAcceptOutput, operation_id="reader_groups_accept")
    def post(self, request):
        return Response(reader_groups.accept(request.user, **parsed(GroupAcceptInput, request.data)))


class ReaderGroupReceiptView(SharingPrivateView):
    @extend_schema(parameters=[OWNER, OpenApiParameter("request_id", str, required=True), OpenApiParameter("group_id", str)],
        responses=output.GroupResult, operation_id="reader_group_receipt")
    def get(self, request):
        return Response(reader_groups.lookup(request.user, research.identifier(request.query_params.get("request_id")),
            research.identifier(request.query_params["group_id"]) if request.query_params.get("group_id") else None))


class ShareSelectionView(SharingPrivateView):
    @extend_schema(parameters=[OWNER], request=ShareSelectionInput, responses=output.ShareSelectionOutput, operation_id="reader_share_selection")
    def post(self, request):
        return Response(share_scope.candidates(request.user, parsed(ShareSelectionInput, request.data)))


class ShareSourcesView(SharingPrivateView):
    @extend_schema(parameters=[OWNER, ShareSourcesQuery], responses=output.ShareSourcesPage, operation_id="reader_share_sources")
    def get(self, request):
        query = parsed(ShareSourcesQuery, request.query_params)
        model = ResearchProject if query["source_kind"] == "research" else ReadingList
        rows = model.objects.filter(user=request.user).order_by("-updated_at", "-id")
        return Response({"owner_id": str(request.user.pk), **page(rows, query["page"], lambda row:
            share_scope.directory_source(row, query["source_kind"]))})


class SharePreviewView(SharingPrivateView):
    @extend_schema(parameters=[OWNER], request=SharePreviewInput, responses=output.SharePreviewOutput, operation_id="reader_share_preview")
    def post(self, request):
        output, _ = share_scope.preview(request.user, parsed(SharePreviewInput, request.data))
        return Response(output)


class ReaderSharesView(SharingPrivateView):
    @extend_schema(parameters=[OWNER, PageQuery], responses=output.ShareDirectory, operation_id="reader_shares_list")
    def get(self, request):
        query = parsed(PageQuery, request.query_params)
        if query["tab"] == "own":
            rows = ReaderShare.objects.filter(user=request.user).order_by("-created_at", "-id")
        elif query["tab"] == "proposals":
            if not has_capability(request.user, Capability.REVIEW_CANDIDATE):
                raise PermissionDenied("当前账户没有策划提案审核权限。")
            rows = reader_shares.visible(request.user).filter(destination="proposal").order_by("-created_at", "-id")
        else:
            candidates = list(reader_shares.visible(request.user).exclude(user=request.user).exclude(destination="proposal").select_related("group__user").order_by("-created_at", "-id")[:5001])
            if len(candidates) > 5000:
                raise ValidationError("接收记录超过单次筛选范围，请先整理过期分享。")
            rows = [row for row in candidates if reader_shares.permitted(row, request.user)]
        return Response({"owner_id": str(request.user.pk), **page(rows, query["page"], lambda row: reader_shares.brief(row, request.user))})

    @extend_schema(parameters=[OWNER], request=ShareCreateInput, responses=output.ShareReceipt, operation_id="reader_shares_create")
    def post(self, request):
        return Response(reader_shares.create(request.user, parsed(ShareCreateInput, request.data)))


class ShareReceiptView(SharingPrivateView):
    @extend_schema(parameters=[OWNER, OpenApiParameter("request_id", str, required=True)], responses=output.ShareReceipt, operation_id="reader_share_receipt")
    def get(self, request):
        return Response(reader_shares.receipt(request.user, research.identifier(request.query_params.get("request_id"))))

    @extend_schema(parameters=[OWNER], request=ShareStopInput, responses=output.ShareRecoveryResult, operation_id='reader_share_stop_pending')
    def post(self, request):
        data=parsed(ShareStopInput,request.data)
        return Response(reader_shares.stop_create(request.user,data['request_id']))


class ShareDetailView(SharingPrivateView):
    @extend_schema(parameters=[OWNER], responses=output.ShareDetail, operation_id="reader_share_detail")
    def get(self, request, pk):
        row = ReaderShare.objects.select_related("user", "group__user").filter(pk=pk).first()
        if row is None:
            raise NotFound("分享已不存在。")
        return Response({"owner_id": str(request.user.pk), "share": reader_shares.brief(row, request.user), "content": reader_shares.read(row, user=request.user)})

    @extend_schema(parameters=[OWNER], request=ShareCommandInput, responses=PolymorphicProxySerializer(component_name='ShareCommandResult', serializers=[output.ShareBrief, output.ShareNotifyResult], resource_type_field_name=None), operation_id="reader_share_command")
    def post(self, request, pk):
        data = parsed(ShareCommandInput, request.data)
        if data["action"] == "notify":
            return Response(reader_shares.notify(request.user, pk, data["expected_revision"]))
        if data["action"] == "review":
            return Response(reader_shares.review(request.user, pk, data["expected_revision"], data["state"]))
        return Response(reader_shares.revoke(request.user, pk, data["expected_revision"]))


class ShareNoticesView(SharingPrivateView):
    @extend_schema(parameters=[OWNER, PageQuery], responses=output.ShareNoticePage, operation_id="reader_share_notices")
    def get(self, request):
        query = parsed(PageQuery, request.query_params)
        rows = ReaderShareNotice.objects.filter(user=request.user).order_by("-created_at", "-id")
        return Response({"owner_id": str(request.user.pk), "unread": rows.filter(read_at__isnull=True).count(),
            **page(rows, query["page"], lambda row: {"id": str(row.pk), "share_id": str(row.share_id), "created_at": row.created_at, "read_at": row.read_at})})

    @extend_schema(parameters=[OWNER], request=NoticeReadInput, responses=output.ShareNoticeRead, operation_id="reader_share_mark_read")
    def post(self, request):
        data = parsed(NoticeReadInput, request.data)
        changed = ReaderShareNotice.objects.filter(user=request.user, pk__in=data["ids"], read_at__isnull=True).update(read_at=timezone.now(), updated_at=timezone.now())
        return Response({"owner_id": str(request.user.pk), "marked": changed})


class PublicShareView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        response["Referrer-Policy"] = "no-referrer"
        response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        return response

    @extend_schema(parameters=[OpenApiParameter("X-Share-Key", str, location=OpenApiParameter.HEADER, required=True)], responses=output.ShareContent, operation_id="public_share_content")
    def get(self, request, pk):
        token = request.headers.get("X-Share-Key", "")
        if not 32 <= len(token) <= 80:
            raise NotFound("分享链接无效或已撤回。")
        row = ReaderShare.objects.select_related("user").filter(pk=pk, destination="public").first()
        if row is None:
            raise NotFound("分享链接无效或已撤回。")
        return Response(reader_shares.read(row, token=token))
