"""Complete website history and explicit restore-to-draft on the original ledger."""
from copy import deepcopy
from hashlib import sha256
import json

from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_issue_serializers import SiteContentSerializer, SiteHistorySerializer
from catalog.editorial_issue_views import EditorialErrorMixin
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import EditorialRevision, SiteSetting
from catalog.services import editorial_issues as ledger
from catalog.site_publication_review import SiteReviewChangeSerializer, SiteReviewCheckSerializer, changes, checks
from catalog.site_layout import HomeCardSerializer, HomeTargetSerializer
from common.permissions import IsLibraryAdmin


def revision_fingerprint(revision):
    return sha256(json.dumps({"id": str(revision.pk), "payload": revision.materialized_preview},
        cls=DjangoJSONEncoder, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def revision_summary(row):
    return {"id": str(row.pk), "revision": row.revision, "state": row.status,
        "saved_at": row.created_at, "saved_by": row.created_by.display_name if row.created_by else "",
        "published_at": row.published_at, "published_by": row.published_by.display_name if row.published_by else ""}


class HistoryQuerySerializer(serializers.Serializer):
    edit_version = serializers.CharField()
    page = serializers.IntegerField(min_value=1, max_value=100000, default=1)
    revision = serializers.UUIDField(required=False)
    compare = serializers.ChoiceField(choices=["public", "saved"], default="public")


class SiteHistoryReferenceSerializer(HomeCardSerializer):
    area = serializers.CharField()
    target = HomeTargetSerializer()


class SiteHistoryPageSerializer(serializers.Serializer):
    edit_version = serializers.CharField()
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    results = SiteHistorySerializer(many=True)
    selected = SiteHistorySerializer(allow_null=True)
    current_public_id = serializers.CharField(allow_blank=True)
    latest_id = serializers.CharField(allow_blank=True)
    compare = serializers.CharField()
    fingerprint = serializers.CharField(allow_blank=True)
    snapshot = SiteContentSerializer(allow_null=True)
    changes = SiteReviewChangeSerializer(many=True)
    checks = SiteReviewCheckSerializer(many=True)
    references = SiteHistoryReferenceSerializer(many=True)


class SiteHistoryView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryAdmin]

    @extend_schema(parameters=[HistoryQuerySerializer], responses=SiteHistoryPageSerializer)
    def get(self, request):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("请从当前管理账户读取网站历史。")
        if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
            raise ValidationError("历史筛选参数不能重复。")
        serializer = HistoryQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        query = serializer.validated_data
        site = get_object_or_404(SiteSetting, key="site_config")
        ledger._check_version("site_content", site.pk, query["edit_version"])
        rows = EditorialRevision.objects.filter(target_type="site_content", target_id=site.pk).select_related("created_by", "published_by").order_by("-revision")
        paginator = Paginator(rows, 20)
        if query["page"] > paginator.num_pages:
            raise ValidationError("这页历史记录已变化，请返回第一页重新读取。")
        page = paginator.page(query["page"])
        entries = list(page.object_list)
        selected = get_object_or_404(rows, pk=query["revision"]) if query.get("revision") else (entries[0] if entries else None)
        current_public = rows.filter(status="published").first() if site.public else None
        latest = rows.first()
        saved = ledger.site_payload()
        snapshot = {**ledger.site_snapshot(selected.materialized_preview), "site_id": str(site.pk),
            "history": [revision_summary(selected)], "edit_version": query["edit_version"],
            "has_unpublished_changes": False} if selected else None
        before = saved if query["compare"] == "saved" else ledger.site_public_payload()
        references = []
        if snapshot:
            for area, cards in snapshot["home_preview"].items():
                slots = {row["id"]: row for row in snapshot["home_layout"].get(area) or []}
                references.extend({**card, "area": area, "target": slots[card["id"]]["target"]} for card in cards or [])
        result = {"edit_version": query["edit_version"], "count": paginator.count, "page": page.number,
            "total_pages": paginator.num_pages, "results": [revision_summary(row) for row in entries],
            "selected": revision_summary(selected) if selected else None,
            "current_public_id": str(current_public.pk) if current_public else "", "latest_id": str(latest.pk) if latest else "",
            "compare": query["compare"], "fingerprint": revision_fingerprint(selected) if selected else "",
            "snapshot": snapshot, "changes": changes(before, snapshot) if snapshot else [],
            "checks": checks(snapshot) if snapshot else [], "references": references}
        ledger._check_version("site_content", site.pk, query["edit_version"])
        return Response(result)


class SiteRestoreSerializer(serializers.Serializer):
    revision_id = serializers.UUIDField()
    edit_version = serializers.CharField()
    expected_fingerprint = serializers.CharField(min_length=64, max_length=64)
    confirm = serializers.BooleanField()
    reason = serializers.CharField(min_length=1, max_length=1000, trim_whitespace=True)


def restore(data, actor):
    # execute() holds the same actor/request locks and atomic receipt as save/publish.
    serializer = SiteRestoreSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    value = serializer.validated_data
    if value["confirm"] is not True:
        raise ValidationError("请确认用所选历史内容创建新草稿。")
    site = ledger.site_target(lock=True)
    ledger._check_version("site_content", site.pk, value["edit_version"])
    original = get_object_or_404(EditorialRevision, pk=value["revision_id"], target_type="site_content", target_id=site.pk)
    if revision_fingerprint(original) != value["expected_fingerprint"]:
        raise ledger.EditConflict("历史内容已变化，请重新核对后再恢复。")
    payload = deepcopy(original.materialized_preview)
    payload["edit_version"] = value["edit_version"]
    return ledger.save_site(payload, actor, retained_layout=payload.get("home_layout", {}))


class SiteRestoreView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryAdmin]

    @extend_schema(request=SiteRestoreSerializer, responses=SiteContentSerializer)
    def post(self, request):
        from catalog.site_commands import execute
        return Response(execute(request, restoring=True))
