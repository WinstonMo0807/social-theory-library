"""Explicit guest import into the existing private history and bookmark records."""
from datetime import timedelta
from uuid import uuid5, NAMESPACE_URL

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from common.private_responses import PrivateAccountResponses
from catalog.models import Page
from catalog.services.editorial_issues import published_issues, public_issue_revision
from ingestion.models import AuditEvent
from . import privacy, research
from .models import Bookmark, ReaderSearchRecord, ReadingHistory, ReadingProgress
from .services import readable_assets_for_user

ACTION = "reader_guest_import"


class GuestRecordInput(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=["reading", "article", "search", "bookmark"])
    at = serializers.DateTimeField()
    asset_id = serializers.UUIDField(required=False)
    page_id = serializers.UUIDField(required=False)
    revision_id = serializers.UUIDField(required=False)
    pdf_page = serializers.IntegerField(min_value=1, max_value=100000, required=False)
    issue_id = serializers.UUIDField(required=False)
    query = serializers.CharField(max_length=500, required=False)
    filters = serializers.DictField(child=serializers.JSONField(), required=False)
    label = serializers.CharField(max_length=240, required=False, allow_blank=True)

    def validate(self, data):
        required = {"reading": ("asset_id", "revision_id", "pdf_page"),
                    "bookmark": ("asset_id", "revision_id", "pdf_page", "page_id"),
                    "article": ("issue_id", "revision_id"), "search": ("query", "filters")}[data["kind"]]
        if any(key not in data for key in required):
            raise serializers.ValidationError("本机记录缺少来源身份，原记录保留。")
        if data["at"] > timezone.now() + timedelta(minutes=5):
            raise serializers.ValidationError("本机记录时间晚于当前时间，请核对设备时钟。")
        filters = data.get("filters", {})
        if len(filters) > 30 or any(len(key) > 60 or not (
            isinstance(value, str) and len(value) <= 1000 or isinstance(value, list) and len(value) <= 50 and
            all(isinstance(item, str) and len(item) <= 500 for item in value)) for key, value in filters.items()):
            raise serializers.ValidationError("检索筛选格式不受支持，原记录保留。")
        return data


class GuestImportInput(serializers.Serializer):
    owner_id = serializers.CharField(max_length=30)
    records = GuestRecordInput(many=True, min_length=1, max_length=200)


class GuestImportResult(serializers.Serializer):
    id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=["imported", "already_imported", "disabled", "unavailable"])
    message = serializers.CharField()


class GuestImportOutput(serializers.Serializer):
    owner_id = serializers.CharField()
    results = GuestImportResult(many=True)


@transaction.atomic
def import_records(user, records):
    user = privacy.command_owner(user)
    results = []
    for data in records:
        identity = str(data["id"])
        fingerprint = research.request_fingerprint(data, data.keys())
        prior = AuditEvent.objects.filter(actor=user, action=ACTION, request_id=identity).first()
        if prior:
            if prior.after.get("fingerprint") != fingerprint:
                raise research.ResearchConflict("同一本机记录的内容已改变，请保留原记录并重新核对。")
            # A receipt survives private erasure, so a late retry never recreates it.
            results.append({"id": identity, "state": "already_imported", "message": "已处理过此记录，不重复写入。"})
            continue
        kind = data["kind"]
        policy = "search_history" if kind == "search" else "personal_notes" if kind == "bookmark" else "reading_history"
        if not privacy.retention_enabled(user, policy):
            results.append({"id": identity, "state": "disabled", "message": f"账户已关闭{privacy.RETENTION_LABELS[policy]}保存，仍保留在本机。"})
            continue
        row = None
        created = False
        if kind == "search":
            row, created = ReaderSearchRecord.objects.get_or_create(user=user,
                request_id=uuid5(NAMESPACE_URL, f"stl:guest-search:{identity}"),
                defaults={"data_ciphertext": research.pack({"query": data["query"], "filters": data["filters"], "origin": "guest"})})
        elif kind == "article":
            issue = published_issues().filter(pk=data["issue_id"]).first()
            if issue and public_issue_revision(issue).pk == data["revision_id"]:
                row = ReadingHistory.objects.create(user=user, issue=issue)
                created = True
        else:
            # Guest sources must still be publicly readable at the exact saved revision.
            asset = readable_assets_for_user(None).filter(pk=data["asset_id"],
                edition__active_catalog_revision__document_revision_id=data["revision_id"]).first()
            page = Page.objects.filter(asset=asset, index=data["pdf_page"]).first() if asset else None
            if page and (kind != "bookmark" or page.pk == data["page_id"]):
                if kind == "bookmark":
                    row, created = Bookmark.objects.get_or_create(user=user, asset=asset, page=page,
                        defaults={"label": data.get("label", "")})
                else:
                    row = ReadingHistory.objects.create(user=user, asset=asset, page_index=page.index)
                    created = True
                    # Import cannot overwrite a newer position already kept by the account.
                    ReadingProgress.objects.get_or_create(user=user, asset=asset, defaults={
                        "current_page": page.index, "last_position": {"page": page.index},
                        "progress_ratio": page.index / max(1, asset.page_count or page.index)})
        if row is None:
            results.append({"id": identity, "state": "unavailable", "message": "原版本已变更或不可公开读取，未替换为其他来源。"})
            continue
        if created:
            type(row).objects.filter(pk=row.pk).update(created_at=data["at"])
        AuditEvent.objects.create(actor=user, action=ACTION, request_id=identity, object_type=type(row).__name__,
            object_id=str(row.pk), after={"fingerprint": fingerprint, "state": "imported"})
        results.append({"id": identity, "state": "imported", "message": "已转存到本人账户。"})
    return {"owner_id": str(user.pk), "results": results}


class GuestRecordsImportView(PrivateAccountResponses, APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=GuestImportInput, responses=GuestImportOutput)
    def post(self, request):
        data = GuestImportInput(data=request.data)
        data.is_valid(raise_exception=True)
        if data.validated_data["owner_id"] != str(request.user.pk):
            raise PermissionDenied("登录账户已变化，本机记录尚未上传到其他账户。")
        return Response(import_records(request.user, data.validated_data["records"]))
