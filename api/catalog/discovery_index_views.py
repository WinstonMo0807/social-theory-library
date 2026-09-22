"""Staff-only visibility into actual reading, text and projection completion."""
from datetime import timedelta

from django.db.models import Count, Exists, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.discovery_index_models import DiscoveryDocument, DiscoverySourceState
from catalog.models import Asset, CatalogingSession, Edition, KnowledgeProjectionDelivery, Page
from catalog.services.discovery_inference import DiscoveryInferenceError, inference_health
from catalog.services.discovery_indexing import request_rebuild, retry_job
from catalog.services.discovery_projection import active_generation, DiscoveryIndexError, discovery_coverage
from catalog.services.discovery_sources import source_header, source_queryset
from catalog.services.publication_eligibility import public_editions
from common.capabilities import Capability, has_capability
from common.permissions import IsLibraryStaff
from ingestion.models import ProcessingJob


class IndexActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["rebuild", "retry"])
    job_id = serializers.UUIDField(required=False)


class IndexActionResultSerializer(serializers.Serializer):
    job_id = serializers.UUIDField()
    status = serializers.CharField()
    message = serializers.CharField()


class IndexStatusSerializer(serializers.Serializer):
    active_generation = serializers.JSONField(allow_null=True)
    model = serializers.JSONField()
    summary = serializers.JSONField()
    capabilities = serializers.JSONField()
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    results = serializers.ListField(child=serializers.JSONField())
    jobs = serializers.ListField(child=serializers.JSONField())
    warnings = serializers.ListField(child=serializers.JSONField())


def _stage(status, message="", **values):
    return {"status": status, "message": message, **values}


def _integer(params, field, default, maximum):
    try:
        value = int(params.get(field, default))
    except (TypeError, ValueError):
        raise ValidationError({field: "需要有效页码。"})
    if not 1 <= value <= maximum:
        raise ValidationError({field: "页码或每页数量超出范围。"})
    return value


class DiscoveryIndexView(APIView):
    permission_classes = [IsLibraryStaff]

    @extend_schema(responses=IndexStatusSerializer, parameters=[
        OpenApiParameter("page", int), OpenApiParameter("page_size", int)])
    def get(self, request):
        page, page_size = _integer(request.query_params, "page", 1, 100000), _integer(request.query_params, "page_size", 15, 50)
        can_retry = has_capability(request.user, Capability.RETRY_JOBS)
        generation = active_generation()
        latest_asset = Asset.objects.filter(edition_id=OuterRef("pk"), kind="normalized", is_current=True).order_by("-version", "-created_at")
        editions = Edition.objects.select_related("work", "active_catalog_revision").annotate(
            effective_asset_id=Coalesce("active_catalog_revision__reader_asset_id", Subquery(latest_asset.values("pk")[:1])))
        total = editions.count()
        rows = list(editions.order_by("-updated_at", "id")[(page - 1) * page_size:page * page_size])
        assets = {str(row.pk): row for row in Asset.objects.filter(pk__in=[row.effective_asset_id for row in rows if row.effective_asset_id])}
        page_counts = {str(row["asset_id"]): row for row in Page.objects.filter(asset_id__in=assets).values("asset_id").annotate(
            total=Count("id"), text=Count("id", filter=~Q(text="")))}
        states = {str(row.source_id): row for row in DiscoverySourceState.objects.filter(generation=generation,
            source_type="edition", source_id__in=[row.pk for row in rows]).select_related("job")} if generation else {}
        eligible = {str(row.pk): row for row in source_queryset("edition").filter(pk__in=[row.pk for row in rows])}
        published_ids = set(public_editions().filter(pk__in=[row.pk for row in rows]).values_list("pk", flat=True))
        indexed_counts = {(str(item["source_id"]), item["source_revision"]): item
            for item in DiscoveryDocument.objects.filter(generation=generation, source_type="edition",
                source_id__in=[row.pk for row in rows]).values("source_id", "source_revision").annotate(
                    keywords=Count("id", filter=Q(keyword_ready=True)), vectors=Count("id", filter=Q(vector_ready=True)))} if generation else {}
        sessions = {str(row.edition_id): str(row.pk) for row in CatalogingSession.objects.filter(
            edition_id__in=[row.pk for row in rows]).order_by("created_at")}
        deliveries = {str(row["event__catalog_revision_id"]): row for row in KnowledgeProjectionDelivery.objects.filter(
            event__catalog_revision_id__in=[row.active_catalog_revision_id for row in rows if row.active_catalog_revision_id],
            consumer="knowledge_graph").values("event__catalog_revision_id", "status", "last_error_message").order_by("updated_at")}
        results = []
        for row in rows:
            asset = assets.get(str(row.effective_asset_id))
            state = states.get(str(row.pk))
            current = eligible.get(str(row.pk))
            header = source_header("edition", current) if current else None
            counts = page_counts.get(str(row.effective_asset_id), {})
            text_pages, pages = counts.get("text", 0), max(counts.get("total", 0), asset.page_count if asset else 0)
            readable = bool(asset and asset.status == "ready" and asset.validation_status == "valid")
            read_status = "ready" if readable else "missing"
            if readable and (row.pk not in published_ids or asset.access_status not in {"public", "inherit"}):
                read_status = "private"
            text_ready = bool(text_pages and row.ocr_status in {"not_required", "succeeded"})
            text_status = "ready" if text_ready else "partial" if text_pages else "failed" if row.ocr_status == "failed" else "pending"
            same = bool(header and state and state.source_revision == header["source_revision"])
            job = state.job if state else None
            indexed = indexed_counts.get((str(row.pk), header["source_revision"]), {}) if header else {}
            n, vectors = indexed.get("keywords", 0), indexed.get("vectors", 0)
            done = bool(same and state.indexed_at and n == state.expected_count == state.completed_count and n)
            index_status = "ready" if done else "failed" if job and job.status == "failed" else "running" if job and job.status == "running" else "pending"
            if not header:
                index_status = "private" if row.state != "published" else "waiting"
            delivery = deliveries.get(str(row.active_catalog_revision_id))
            knowledge = _stage("ready" if delivery and delivery["status"] == "completed" else "failed" if delivery and delivery["status"] == "failed" else "pending",
                delivery["last_error_message"] if delivery and delivery["last_error_message"] else "按当前馆藏发布修订核对知识关系投影。")
            last_activity = max(filter(None, [state.indexed_at if state else None, job.updated_at if job else None, row.updated_at]))
            results.append({"edition_id": str(row.pk), "title": row.work.title, "asset_id": str(asset.pk) if asset else "",
                "source_revision": str(row.active_catalog_revision.document_revision_id or "") if row.active_catalog_revision else "",
                "readable": _stage(read_status, "阅读文件已通过校验。" if readable else "阅读文件尚未就绪。"),
                "text": _stage(text_status, "页数表示含可检索文字的页面，空白页不计入。OCR状态：" + row.get_ocr_status_display(), completed_pages=text_pages, total_pages=pages),
                "keyword": _stage(index_status, job.error_message if job and job.status == "failed" else "按当前有效公开修订确认索引写入。", count=n),
                "vector": _stage("ready" if done and vectors == n else index_status if index_status != "ready" else "partial", count=vectors),
                "knowledge": knowledge, "last_activity": last_activity.isoformat(), "job_id": str(job.pk) if job else None,
                "retry_allowed": bool(can_retry and job and job.status == "failed"),
                "overdue": bool(header and not done and row.updated_at < timezone.now() - timedelta(hours=24)),
                "workbench_url": f"/admin/cataloging/{sessions[str(row.pk)]}" if str(row.pk) in sessions else ""})
        warnings = []
        try:
            health = inference_health()
            emb = bool(health.get("models", {}).get("embedding", {}).get("inference_completed"))
            rer = bool(health.get("models", {}).get("reranker", {}).get("inference_completed"))
            model = {"ready": emb and rer, "embedding_ready": emb, "reranker_ready": rer,
                     "message": "本地编码与重排已实际执行。" if emb and rer else "模型文件已准备，尚未完成本次服务启动后的编码和重排确认。"}
        except DiscoveryInferenceError:
            model = {"ready": False, "embedding_ready": False, "reranker_ready": False, "message": "本地推理服务暂不可用；请检查模型准备与容器状态。"}
        from catalog.services.semantic_search import viewer_access_statuses
        coverage = discovery_coverage(viewer_access_statuses(authenticated=True, staff=True))
        has_text = Page.objects.filter(asset_id=OuterRef("effective_asset_id")).exclude(text="")
        text_total = editions.filter(ocr_status__in=["not_required", "succeeded"]).filter(Exists(has_text)).count()
        graph_total = Edition.objects.filter(active_catalog_revision__knowledge_events__deliveries__consumer="knowledge_graph",
            active_catalog_revision__knowledge_events__deliveries__status="completed").distinct().count()
        jobs = list(ProcessingJob.objects.filter(job_type="discovery_index").order_by("-created_at").values(
            "id", "status", "progress", "error_message", "created_at")[:20])
        summary = {"readable": Asset.objects.filter(kind="normalized", is_current=True, status="ready", validation_status="valid").values("edition_id").distinct().count(),
            "text_ready": text_total, "keyword_ready": coverage.get("indexed_editions", 0), "vector_ready": coverage.get("vector_editions", 0),
            "knowledge_ready": graph_total, "waiting": coverage.get("pending_editions", 0),
            "failed": ProcessingJob.objects.filter(job_type="discovery_index", status="failed").count()}
        if not generation:
            warnings.append({"message": "尚无生效的观点检索版本；新版本核对完成前，原文检索和阅读继续使用既有索引。"})
        return Response({"active_generation": {"id": str(generation.pk), "index_uid": generation.uid,
            "model": generation.model_repo_id, "revision": generation.model_revision,
            "artifact_id": generation.config_snapshot.get("embedding_artifact", ""), "created_at": generation.created_at.isoformat()} if generation else None,
            "model": model, "summary": summary, "capabilities": {"rebuild": has_capability(request.user, Capability.MANAGE_SEMANTIC_INDEX), "retry": can_retry},
            "count": total, "page": page, "page_size": page_size, "results": results, "jobs": jobs, "warnings": warnings})

    @extend_schema(request=IndexActionSerializer, responses={202: IndexActionResultSerializer})
    def post(self, request):
        data = IndexActionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        action = data.validated_data["action"]
        capability = Capability.MANAGE_SEMANTIC_INDEX if action == "rebuild" else Capability.RETRY_JOBS
        if not has_capability(request.user, capability):
            raise PermissionDenied("当前账号无权执行此索引操作。")
        try:
            if action == "rebuild":
                job = request_rebuild(request.user)
            else:
                if not data.validated_data.get("job_id"):
                    raise ValidationError({"job_id": "请选择需要重试的任务。"})
                job = retry_job(data.validated_data["job_id"])
        except DiscoveryIndexError as exc:
            raise ValidationError({"detail": str(exc), "code": exc.code})
        return Response({"job_id": str(job.pk), "status": job.status,
                         "message": "索引任务已登记，写入核对完成后生效；原有效版本保留。"}, status=202)
