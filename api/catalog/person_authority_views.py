from drf_spectacular.utils import extend_schema
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import CanAccessBackOffice
from common.private_responses import PrivateAccountResponses
from catalog.models import Person, PersonNameVariant
from catalog.services import person_authority as service
from catalog.person_resolution_views import PersonResolutionSummarySerializer


class StrictInput(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError("包含不支持的字段，请重新读取人物规范。")
        return super().to_internal_value(data)


class AuthorityMaterial(StrictInput):
    id = serializers.UUIDField()
    rendition_id = serializers.UUIDField()
    caption = serializers.CharField(max_length=500, allow_blank=True)


class AuthorityValues(StrictInput):
    biographical_materials = AuthorityMaterial(many=True, max_length=100, required=False)
    key_concerns = serializers.ListField(child=serializers.CharField(max_length=240), max_length=100, required=False)
    preferred_name = serializers.CharField(max_length=240)
    original_name = serializers.CharField(max_length=240, allow_blank=True)
    citation_name = serializers.CharField(max_length=240, allow_blank=True, required=False)
    preferred_language = serializers.CharField(max_length=24, allow_blank=True)
    original_language = serializers.CharField(max_length=24, allow_blank=True)
    country_region = serializers.CharField(max_length=120, allow_blank=True)
    birth_year = serializers.IntegerField(allow_null=True)
    death_year = serializers.IntegerField(allow_null=True)
    biography = serializers.CharField(max_length=10000, allow_blank=True, trim_whitespace=False)
    authority_note = serializers.CharField(max_length=5000, allow_blank=True, trim_whitespace=False)
    external_ids = serializers.DictField(child=serializers.JSONField())
    identifier_sources = serializers.DictField(child=serializers.CharField(max_length=2000, allow_blank=True))
    authority_status = serializers.ChoiceField(choices=["draft", "needs_review", "verified"])

    def validate_external_ids(self, value):
        import re
        if len(value) > 50 or any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,40}", key) or "__" in key for key in value):
            raise serializers.ValidationError("最多50个规范标识类别，请核对类别名称。")
        return value


class AuthorityVariant(StrictInput):
    id = serializers.UUIDField(required=False)
    name = serializers.CharField(max_length=240)
    language = serializers.CharField(max_length=24)
    variant_type = serializers.ChoiceField(choices=[("alias", "别名"), ("translation", "译名"), ("abbreviation", "简称"), ("historical", "历史名称"), ("transliteration", "音译")])
    source_note = serializers.CharField(max_length=5000, allow_blank=True)
    is_verified = serializers.BooleanField()
    displayable = serializers.BooleanField()


class AuthorityInput(StrictInput):
    operation = serializers.ChoiceField(choices=["create", "update", "decision"])
    person_id = serializers.UUIDField(required=False)
    expected_version = serializers.RegexField(regex=r"^[a-f0-9]{64}$", required=False)
    values = AuthorityValues(required=False)
    variants = AuthorityVariant(many=True, required=False, max_length=200)
    target_id = serializers.UUIDField(required=False)
    target_version = serializers.RegexField(regex=r"^[a-f0-9]{64}$", required=False)
    decision = serializers.ChoiceField(choices=["independent", "needs_evidence"], required=False)
    reason = serializers.CharField(min_length=2, max_length=1000)

    def validate(self, data):
        shared = {"operation", "reason", "request_id", "confirmed", "preview_hash"}
        required = {"create": {"values", "variants"}, "update": {"person_id", "expected_version", "values", "variants"},
            "decision": {"person_id", "expected_version", "target_id", "target_version", "decision"}}[data["operation"]]
        if required - set(data) or set(data) - required - shared:
            raise serializers.ValidationError("字段与当前操作不匹配。")
        return data


class AuthorityCommand(AuthorityInput):
    request_id = serializers.UUIDField()
    confirmed = serializers.BooleanField()
    preview_hash = serializers.RegexField(regex=r"^[a-f0-9]{64}$")


class AuthorityQuery(serializers.Serializer):
    search = serializers.CharField(max_length=200, allow_blank=True, default="")
    status = serializers.ChoiceField(choices=["", *Person.AuthorityStatus.values], default="")
    page = serializers.IntegerField(min_value=1, default=1)


class AuthorityDirectory(serializers.Serializer):
    actor_id = serializers.CharField()
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    results = PersonResolutionSummarySerializer(many=True)


class AuthorityDetail(serializers.Serializer):
    actor_id = serializers.CharField()
    id = serializers.UUIDField()
    version = serializers.CharField()
    updated_at = serializers.DateTimeField()
    values = serializers.JSONField()
    variants = serializers.ListField(child=serializers.JSONField())
    identifiers = serializers.ListField(child=serializers.JSONField())
    can_edit = serializers.BooleanField()
    can_verify = serializers.BooleanField()
    scholar_id = serializers.UUIDField(allow_null=True)
    portrait_url = serializers.CharField(allow_blank=True)
    portrait_notice = serializers.CharField(allow_blank=True)
    public_url = serializers.CharField(allow_blank=True)
    pending_draft = serializers.BooleanField()
    impact = serializers.JSONField()
    impact_complete = serializers.BooleanField()
    history = serializers.ListField(child=serializers.JSONField())


class AuthorityVariantChange(serializers.Serializer):
    before = AuthorityVariant(allow_null=True)
    after = AuthorityVariant()


class AuthorityPreview(serializers.Serializer):
    actor_id = serializers.CharField()
    person_id = serializers.UUIDField(allow_null=True)
    preview_hash = serializers.CharField()
    fields = serializers.ListField(child=serializers.CharField())
    edition_count = serializers.IntegerField()
    profile_count = serializers.IntegerField()
    public_update = serializers.BooleanField()
    reason = serializers.CharField()
    decision = serializers.CharField(allow_blank=True)
    before = serializers.JSONField(allow_null=True)
    after = serializers.JSONField(allow_null=True)
    variant_changes = AuthorityVariantChange(many=True)


class AuthorityReceipt(serializers.Serializer):
    actor_id = serializers.CharField()
    request_id = serializers.UUIDField()
    person_id = serializers.UUIDField(allow_null=True)
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    created_at = serializers.DateTimeField()
    operation = serializers.CharField()
    event_ids = serializers.ListField(child=serializers.UUIDField())


class AuthorityStop(StrictInput):
    action = serializers.ChoiceField(choices=["cancel_pending"])


class AuthorityBase(PrivateAccountResponses, APIView):
    permission_classes = [CanAccessBackOffice]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("请重新核对当前编辑账户。")


class AuthorityDirectoryView(AuthorityBase):
    @extend_schema(operation_id="person_authority_directory", parameters=[AuthorityQuery], responses=AuthorityDirectory)
    def get(self, request):
        query = AuthorityQuery(data=request.query_params); query.is_valid(raise_exception=True)
        data = query.validated_data
        rows = service.authority_rows(data["search"], data["status"])
        count, page = rows.count(), data["page"]
        if page > 1 and (page - 1) * 20 >= count:
            raise NotFound("当前页已没有人物，请返回第一页。")
        return Response(AuthorityDirectory({"actor_id": str(request.user.pk), "count": count, "page": page,
            "total_pages": max(1, (count + 19) // 20), "results": rows[(page - 1) * 20:page * 20]}).data)


class AuthorityDetailView(AuthorityBase):
    @extend_schema(operation_id="person_authority_detail", responses=AuthorityDetail)
    def get(self, request, person_id):
        return Response(AuthorityDetail(service.detail(get_object_or_404(Person, pk=person_id), request.user)).data)


class AuthorityPreviewView(AuthorityBase):
    @extend_schema(request=AuthorityInput, responses=AuthorityPreview)
    def post(self, request):
        data = AuthorityInput(data=request.data); data.is_valid(raise_exception=True)
        return Response(AuthorityPreview(service.prepare(request.user, data.validated_data)[0]).data)


class AuthorityCommandView(AuthorityBase):
    @extend_schema(request=AuthorityCommand, responses=AuthorityReceipt)
    def post(self, request):
        data = AuthorityCommand(data=request.data); data.is_valid(raise_exception=True)
        return Response(AuthorityReceipt(service.command(request.user, data.validated_data)).data)


class AuthorityReceiptView(AuthorityBase):
    @extend_schema(responses=AuthorityReceipt)
    def get(self, request, request_id):
        return Response(AuthorityReceipt(service.receipt(request.user, request_id)).data)

    @extend_schema(request=AuthorityStop, responses=AuthorityReceipt)
    def post(self, request, request_id):
        data = AuthorityStop(data=request.data); data.is_valid(raise_exception=True)
        return Response(AuthorityReceipt(service.stop_pending(request.user, request_id)).data)
