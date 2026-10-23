"""Directory review and navigation; presentation is supplied after design approval."""
from uuid import UUID

from django.db.models import Exists, OuterRef, Subquery
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.capabilities import Capability, has_capability
from common.permissions import CanAccessBackOffice, CanRetryJobs
from catalog.models import Asset, DocumentOutlineRevision
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.services.document_outline import (
    OutlineConflict, adopt_outline, edit_outline, outline_job_action,
    outline_state, public_outline, queue_outline_rebuild,
)
from catalog.services.publication_eligibility import active_asset_q
from catalog.services.semantic_search import viewer_access_statuses
from ingestion.models import ProcessingJob


class OutlineNodeSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    parent_id = serializers.UUIDField(required=False, allow_null=True)
    title = serializers.CharField(max_length=600)
    pdf_page = serializers.IntegerField(min_value=1, allow_null=True)
    printed_label = serializers.CharField(max_length=40, required=False, allow_blank=True)
    pdf_position = serializers.ListField(child=serializers.FloatField(min_value=0), required=False)
    normalized_position = serializers.ListField(child=serializers.FloatField(min_value=0, max_value=1), required=False)
    contents_page = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    clear_position = serializers.BooleanField(required=False)
    calibration_status = serializers.ChoiceField(
        choices=["unverified", "needs_review", "confirmed", "native", "matched", "generated"], required=False)


class OutlineCommandSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["rebuild", "edit", "adopt", "restore", "export"])
    expected_revision = serializers.IntegerField(min_value=0, required=False)
    revision_id = serializers.UUIDField(required=False)
    base_revision_id = serializers.UUIDField(required=False, allow_null=True)
    request_id = serializers.UUIDField(required=False)
    nodes = OutlineNodeSerializer(many=True, required=False)


class AdminDocumentOutlineView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, asset_id):
        asset = get_object_or_404(Asset, pk=asset_id, kind=Asset.Kind.NORMALIZED)
        if request.query_params.get("revision_id"):
            try:
                identifier = UUID(request.query_params["revision_id"])
            except ValueError:
                return Response({"detail": "目录修订标识无效。"}, status=400)
            from catalog.services.document_outline import revision_payload
            return Response(revision_payload(get_object_or_404(asset.outline_revisions, pk=identifier)))
        try:
            history_page = int(request.query_params.get("history_page", 1))
        except (TypeError, ValueError):
            return Response({"detail": "历史页码必须是整数。"}, status=400)
        return Response(outline_state(asset, history_page=history_page))

    @extend_schema(request=OutlineCommandSerializer, responses={200: OpenApiTypes.OBJECT, 202: OpenApiTypes.OBJECT})
    def post(self, request, asset_id):
        command = OutlineCommandSerializer(data=request.data)
        command.is_valid(raise_exception=True)
        data = command.validated_data
        action = data["action"]
        capability = Capability.RETRY_JOBS if action in {"rebuild", "export"} else Capability.EDIT_METADATA
        if not has_capability(request.user, capability):
            return Response({"detail": "当前账户没有执行此目录操作的权限。"}, status=403)
        asset = get_object_or_404(Asset, pk=asset_id, kind=Asset.Kind.NORMALIZED)
        if not data.get("request_id"):
            return Response({"detail": "目录操作需要 request_id，以便安全重试。"}, status=400)
        try:
            if action == "export":
                from catalog.services.outline_exports import queue_export
                if not has_capability(request.user, Capability.VIEW_EVIDENCE):
                    return Response({"detail": "当前账户不能下载审核文件。"}, status=403)
                if not data.get("revision_id"):
                    return Response({"detail": "请指定已采用目录的修订。"}, status=400)
                job = queue_export(asset.pk, revision_id=data["revision_id"], request_id=data["request_id"], actor=request.user)
                return Response({"job_id": str(job.pk), "status": job.status}, status=202 if job.status in {"pending", "running"} else 200)
            if action == "rebuild":
                if not data.get("request_id"):
                    return Response({"detail": "重建需要 request_id，以便安全重试。"}, status=400)
                job = queue_outline_rebuild(asset.pk, actor=request.user, request_id=data["request_id"])
                return Response({"job_id": str(job.pk), "status": job.status}, status=202 if job.status in {"pending", "running"} else 200)
            if "expected_revision" not in data:
                return Response({"detail": "请提供当前目录 expected_revision。"}, status=400)
            if action == "edit":
                if "nodes" not in data:
                    return Response({"detail": "请提供目录节点列表。"}, status=400)
                edit_outline(asset.pk, nodes=data["nodes"], expected_revision=data["expected_revision"], actor=request.user,
                             request_id=data["request_id"], base_revision_id=data.get("base_revision_id"))
            else:
                if not data.get("revision_id"):
                    return Response({"detail": "请选择采用或恢复的目录修订。"}, status=400)
                get_object_or_404(asset.outline_revisions, pk=data["revision_id"])
                adopt_outline(asset.pk, revision_id=data["revision_id"], expected_revision=data["expected_revision"], actor=request.user, restore=action == "restore", request_id=data["request_id"])
            return Response(outline_state(asset))
        except OutlineConflict as exc:
            return Response({"detail": str(exc), "code": "outline_conflict"}, status=409)
        except (ValueError, TypeError) as exc:
            return Response({"detail": str(exc)}, status=400)


class PublicDocumentOutlineView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, asset_id):
        staff = bool(request.user.is_authenticated and (request.user.is_staff or getattr(request.user, "role", "") in {"admin", "editor", "reviewer"}))
        access_statuses = viewer_access_statuses(authenticated=request.user.is_authenticated, staff=staff)
        asset = get_object_or_404(Asset.objects.select_related("edition__active_catalog_revision").filter(
            active_asset_q(asset_prefix="")), pk=asset_id, kind="normalized", status="ready",
            validation_status="valid", access_status__in=access_statuses)
        return Response({"asset_id": str(asset.pk), "nodes": public_outline(asset, access_statuses=access_statuses)})


class OutlineBatchSerializer(serializers.Serializer):
    asset_ids = serializers.ListField(child=serializers.UUIDField(), max_length=100)
    request_id = serializers.UUIDField()


class AdminOutlineRebuildBatchView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanRetryJobs]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        """Bounded old-library inventory; GET never schedules a job."""
        queryset = Asset.objects.filter(kind="normalized", is_current=True, status="ready").select_related("edition__work")
        active = DocumentOutlineRevision.objects.filter(asset_id=OuterRef("pk"), is_active=True)
        current = active.filter(source_checksum=OuterRef("sha256"), document_revision__is_active=True)
        latest = DocumentOutlineRevision.objects.filter(asset_id=OuterRef("pk")).order_by("-revision")
        queryset = queryset.annotate(has_outline=Exists(current), has_previous_outline=Exists(active), latest_outline_id=Subquery(latest.values("pk")[:1]))
        queryset = queryset.annotate(needs_review=Exists(DocumentOutlineRevision.objects.filter(pk=OuterRef("latest_outline_id"), reviewed=False)))
        selected_filter = request.query_params.get("filter", "missing")
        if selected_filter == "missing":
            queryset = queryset.filter(has_outline=False)
        elif selected_filter == "stale":
            queryset = queryset.filter(has_outline=False, has_previous_outline=True)
        elif selected_filter == "needs_review":
            queryset = queryset.filter(needs_review=True)
        elif selected_filter != "all":
            return Response({"detail": "filter 请选择 missing、stale、needs_review 或 all。"}, status=400)
        if request.query_params.get("after"):
            try:
                queryset = queryset.filter(pk__gt=UUID(request.query_params["after"]))
            except ValueError:
                return Response({"detail": "分页标识无效。"}, status=400)
        rows = list(queryset.order_by("pk")[:51])
        return Response({"items": [{"asset_id": str(row.pk), "edition_id": str(row.edition_id),
                                    "title": row.edition.work.title, "page_count": row.page_count,
                                    "has_outline": row.has_outline, "needs_review": row.needs_review,
                                    "stale": row.has_previous_outline and not row.has_outline} for row in rows[:50]],
                         "next_cursor": str(rows[49].pk) if len(rows) > 50 else None})

    @extend_schema(request=OutlineBatchSerializer, responses={202: OpenApiTypes.OBJECT})
    def post(self, request):
        from uuid import uuid5

        command = OutlineBatchSerializer(data=request.data)
        command.is_valid(raise_exception=True)
        results = []
        for identifier in dict.fromkeys(command.validated_data["asset_ids"]):
            asset = Asset.objects.filter(pk=identifier, kind="normalized", is_current=True).first()
            if not asset:
                results.append({"asset_id": str(identifier), "status": "unavailable"})
                continue
            try:
                job = queue_outline_rebuild(asset.pk, actor=request.user,
                    request_id=uuid5(command.validated_data["request_id"], str(asset.pk)))
                results.append({"asset_id": str(asset.pk), "job_id": str(job.pk), "status": job.status})
            except OutlineConflict as exc:
                results.append({"asset_id": str(asset.pk), "status": "blocked", "detail": str(exc)})
        return Response({"results": results}, status=202)


class OutlineJobCommandSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["retry", "cancel"])


class AdminOutlineJobView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanRetryJobs]

    @extend_schema(request=OutlineJobCommandSerializer, responses={202: OpenApiTypes.OBJECT})
    def post(self, request, job_id):
        command = OutlineJobCommandSerializer(data=request.data)
        command.is_valid(raise_exception=True)
        get_object_or_404(ProcessingJob, pk=job_id, job_type="text_extraction", stats__operation__in=["outline_rebuild", "outline_export"])
        try:
            job = outline_job_action(job_id, action=command.validated_data["action"], actor=request.user)
        except OutlineConflict as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response({"job_id": str(job.pk), "status": job.status}, status=202)
