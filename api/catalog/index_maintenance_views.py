"""PDF M13 maintenance over Discovery and the existing authority-derived lexicon."""
from hashlib import sha256
import json

from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.discovery_index_views import DiscoveryIndexView, IndexStatusSerializer
from catalog.editorial_issue_views import EditorialErrorMixin
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import SemanticIndexVersion, SiteSetting
from catalog.services.discovery_indexing import index_writer, request_rebuild, retry_job, _activate_generation
from catalog.services.discovery_projection import DiscoveryIndexError
from catalog.services.editorial_issues import EditConflict
from common.capabilities import Capability, has_capability
from common.permissions import IsLibraryStaff
from ingestion.models import AuditEvent, ProcessingJob
from ingestion.services.processing_commands import task_version

ACTION = "index.maintenance.command"
CAPABILITIES = {"rebuild": Capability.MANAGE_SEMANTIC_INDEX, "activate": Capability.MANAGE_SEMANTIC_INDEX,
                "retry": Capability.RETRY_JOBS, "reconcile": Capability.MANAGE_QUERY_LEXICON}


def maintenance_version():
    rows = SemanticIndexVersion.discovery_objects.order_by("id").values_list("id", "status", "activated_at", "updated_at")
    return sha256(json.dumps(list(rows), default=str).encode()).hexdigest()


def locked_actor(request, *, capability=None):
    if request.headers.get("X-Editor-Owner") != str(request.user.pk):
        raise PermissionDenied("登录账户已变化，请重新读取索引维护页面。")
    actor = get_object_or_404(get_user_model().objects.select_for_update(), pk=request.user.pk, is_active=True)
    allowed = has_capability(actor, capability) if capability else any(has_capability(actor, value) for value in CAPABILITIES.values())
    if actor.token_version != request.user.token_version or not allowed:
        raise PermissionDenied("当前会话没有索引维护权限。")
    return actor


class IndexMaintenanceCommandSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    action = serializers.ChoiceField(choices=list(CAPABILITIES))
    expected_version = serializers.CharField(max_length=64)
    job_id = serializers.UUIDField(required=False)
    expected_job_version = serializers.CharField(max_length=64, required=False)
    generation_id = serializers.UUIDField(required=False)
    confirmed = serializers.BooleanField(required=False)

    def validate(self, data):
        fields = {"request_id", "action", "expected_version"}
        fields |= {"job_id", "expected_job_version"} if data["action"] == "retry" else {"generation_id", "confirmed"} if data["action"] == "activate" else set()
        if set(self.initial_data) != fields: raise serializers.ValidationError("请使用当前页面的完整操作参数。")
        if data["action"] == "activate" and data.get("confirmed") is not True:
            raise serializers.ValidationError("请确认此版本将用于后续公开检索。")
        return data


class IndexMaintenanceReceiptSerializer(serializers.Serializer):
    owner_id = serializers.CharField()
    request_id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    next_url = serializers.CharField(allow_blank=True)
    message = serializers.CharField(allow_blank=True)
    job_id = serializers.UUIDField(allow_null=True)


class IndexGenerationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    model = serializers.CharField(allow_blank=True)
    revision = serializers.CharField(allow_blank=True)
    dimensions = serializers.IntegerField(allow_null=True)
    count = serializers.IntegerField()
    expected_count = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    activated_at = serializers.DateTimeField(allow_null=True)
    verified_at = serializers.CharField(allow_blank=True)
    error = serializers.CharField(allow_blank=True)


class IndexMaintenanceJobSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    progress = serializers.IntegerField()
    error_message = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
    title = serializers.CharField()
    action = serializers.CharField()
    version = serializers.CharField()
    can_retry = serializers.BooleanField()


class IndexStageSerializer(serializers.Serializer):
    status = serializers.CharField()
    message = serializers.CharField(allow_blank=True)
    count = serializers.IntegerField(required=False)
    completed_pages = serializers.IntegerField(required=False)
    total_pages = serializers.IntegerField(required=False)


class IndexMaterialSerializer(serializers.Serializer):
    edition_id = serializers.UUIDField()
    work_id = serializers.UUIDField()
    title = serializers.CharField()
    title_has_unpublished_changes = serializers.BooleanField()
    edition_label = serializers.CharField(allow_blank=True)
    cover_url = serializers.CharField(allow_blank=True)
    published = serializers.BooleanField()
    asset_id = serializers.CharField(allow_blank=True)
    source_revision = serializers.CharField(allow_blank=True)
    readable = IndexStageSerializer()
    text = IndexStageSerializer()
    keyword = IndexStageSerializer()
    vector = IndexStageSerializer()
    knowledge = IndexStageSerializer()
    last_activity = serializers.DateTimeField()
    job_id = serializers.UUIDField(allow_null=True)
    retry_allowed = serializers.BooleanField()
    overdue = serializers.BooleanField()
    workbench_url = serializers.CharField(allow_blank=True)


class IndexMaintenanceCapabilitiesSerializer(serializers.Serializer):
    rebuild = serializers.BooleanField()
    retry = serializers.BooleanField()
    reconcile = serializers.BooleanField()


class IndexMaintenanceModelSerializer(serializers.Serializer):
    ready = serializers.BooleanField(allow_null=True)
    message = serializers.CharField()


class IndexMaintenanceWarningSerializer(serializers.Serializer):
    message = serializers.CharField()


class IndexActiveGenerationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    index_uid = serializers.CharField()
    model = serializers.CharField(allow_blank=True)
    revision = serializers.CharField(allow_blank=True)
    artifact_id = serializers.CharField(allow_blank=True)
    dimensions = serializers.IntegerField(allow_null=True)
    pipeline = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()


class IndexMaintenanceSerializer(IndexStatusSerializer):
    active_generation = IndexActiveGenerationSerializer(allow_null=True)
    summary = serializers.DictField(child=serializers.IntegerField())
    capabilities = IndexMaintenanceCapabilitiesSerializer()
    model = IndexMaintenanceModelSerializer()
    warnings = IndexMaintenanceWarningSerializer(many=True)
    results = IndexMaterialSerializer(many=True)
    version = serializers.CharField()
    checked_at = serializers.DateTimeField()
    versions = IndexGenerationSerializer(many=True)
    versions_count = serializers.IntegerField()
    versions_page = serializers.IntegerField()
    jobs = IndexMaintenanceJobSerializer(many=True)
    jobs_count = serializers.IntegerField()
    jobs_page = serializers.IntegerField()


def receipt(row):
    return {"owner_id": str(row.actor_id), "request_id": row.request_id,
            "state": "cancelled" if row.after.get("cancelled") else "applied",
            "next_url": row.after.get("next_url", ""), "message": row.after.get("message", ""), "job_id": row.after.get("job_id")}


class IndexMaintenanceView(EditorialErrorMixin, DiscoveryIndexView):
    maintenance = True

    def handle_exception(self, error):
        if isinstance(error, DiscoveryIndexError):
            return Response({"code": error.code, "detail": str(error)}, status=409)
        return super().handle_exception(error)

    @extend_schema(responses=IndexMaintenanceSerializer, parameters=[OpenApiParameter(name, type=str) for name in ("q", "scope", "edition_id", "page", "jobs_page", "versions_page")])
    def get(self, request):
        if not has_capability(request.user, Capability.VIEW_SEMANTIC_INDEX): raise PermissionDenied("当前账户不能查看全站索引维护记录。")
        from catalog.discovery_index_views import _integer
        from ingestion.services.processing_identity import task_titles, processing_identity
        payload = super().get(request).data
        page = _integer(request.query_params, "versions_page", 1, 100000)
        versions = SemanticIndexVersion.discovery_objects.order_by("-created_at", "pk")
        rows = [{"id": row.pk, "status": row.status, "model": row.model_repo_id, "revision": row.model_revision,
                 "dimensions": row.dimensions, "count": row.document_count, "expected_count": row.expected_document_count,
                 "created_at": row.created_at, "activated_at": row.activated_at,
                 "verified_at": str(row.validation_details.get("verified_at") or ""), "error": row.error_message}
                for row in versions[(page - 1) * 10:page * 10]]
        job_page = _integer(request.query_params, "jobs_page", 1, 100000)
        jobs = ProcessingJob.objects.filter(job_type="discovery_index").select_related("edition__work", "asset__edition__work").order_by("-created_at", "pk")
        recent = list(jobs[(job_page - 1) * 15:job_page * 15]); titles = task_titles(recent)
        payload.update(version=maintenance_version(), checked_at=timezone.now(), versions=rows, versions_count=versions.count(), versions_page=page,
            jobs_count=jobs.count(), jobs_page=job_page, jobs=[{"id": job.pk, "status": job.status, "progress": job.progress,
                "error_message": job.error_message, "created_at": job.created_at,
                "title": "建立候选索引" if job.stats.get("action") == "build" else processing_identity(job, titles)["title"],
                "action": str(job.stats.get("action") or "source"), "version": task_version(job),
                "can_retry": has_capability(request.user, Capability.RETRY_JOBS) and job.status in {"failed", "paused"}} for job in recent])
        payload["capabilities"]["reconcile"] = has_capability(request.user, Capability.MANAGE_QUERY_LEXICON)
        return Response(payload)

    @extend_schema(request=IndexMaintenanceCommandSerializer, responses=IndexMaintenanceReceiptSerializer)
    @transaction.atomic
    def post(self, request):
        actor = locked_actor(request)
        serializer = IndexMaintenanceCommandSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not has_capability(actor, CAPABILITIES[data["action"]]): raise PermissionDenied("当前账户不能执行此索引操作。")
        signature = sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
        prior = AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(data["request_id"])).first()
        if prior:
            if not prior.after.get("cancelled") and prior.after.get("signature") != signature: raise EditConflict("原请求编号不能用于不同操作。")
            return Response(receipt(prior))
        job = None
        try:
            # Same writer fence as the coordinator: no live index can change under a cutover.
            with index_writer() as acquired:
                if not acquired: raise EditConflict("索引正在写入，请稍后重新读取再操作。")
                lock, _ = SiteSetting.objects.get_or_create(key="discovery_build_lock", defaults={"value": {}})
                SiteSetting.objects.select_for_update().get(pk=lock.pk)
                if maintenance_version() != data["expected_version"]: raise EditConflict("索引版本状态已经变化，请读取最新记录。")
                if data["action"] == "rebuild":
                    job = request_rebuild(actor, activate=False)
                    message = "候选索引任务已登记。写入核对完成后，再明确选择切换；当前索引保留。" if not job.stats.get("activate", True) else "已有建立任务正在执行，已复用原任务；其原定完成后切换策略保留。"
                elif data["action"] == "retry":
                    target = get_object_or_404(ProcessingJob.objects.select_for_update(), pk=data["job_id"], job_type="discovery_index")
                    if task_version(target) != data["expected_job_version"]: raise EditConflict("任务执行轮次已变化，请读取最新状态。")
                    job = retry_job(target.pk, actor=actor); message = "原索引任务已重新排队，成功片段与来源身份保留。"
                elif data["action"] == "activate":
                    target = get_object_or_404(SemanticIndexVersion.discovery_objects, pk=data["generation_id"])
                    _activate_generation(target); message = "已切换检索版本，原版本及派生记录保留。"
                else:
                    from catalog.services.query_lexicon.operations import enqueue_query_lexicon_reconciliation
                    job = enqueue_query_lexicon_reconciliation(actor=actor); message = "已登记查询词同步任务，沿已有权威来源同步。"
        except DiscoveryIndexError as error:
            raise EditConflict(str(error)) from error
        next_url = f"/admin/processing?task_id={job.pk}&task_source=processing_job" if job else "/admin/processing/semantic-index?tab=versions"
        row = AuditEvent.objects.create(actor=actor, action=ACTION, object_type="index_maintenance", object_id=str(job.pk) if job else str(data.get("generation_id", "")),
            request_id=str(data["request_id"]), after={"signature": signature, "operation": data["action"], "job_id": str(job.pk) if job else None, "message": message, "next_url": next_url})
        return Response(receipt(row))


class IndexMaintenanceStopSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["cancel_pending"])


class IndexMaintenanceReceiptView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryStaff]

    @extend_schema(responses=IndexMaintenanceReceiptSerializer)
    def get(self, request, request_id):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk): raise PermissionDenied("请使用原账户查看回执。")
        return Response(receipt(get_object_or_404(AuditEvent, actor=request.user, action=ACTION, request_id=str(request_id))))

    @extend_schema(request=IndexMaintenanceStopSerializer, responses=IndexMaintenanceReceiptSerializer)
    @transaction.atomic
    def post(self, request, request_id):
        actor = locked_actor(request)
        serializer = IndexMaintenanceStopSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        if set(request.data) != {"action"}: raise ValidationError("只可停止原待定请求。")
        row = AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(request_id)).first()
        if row is None: row = AuditEvent.objects.create(actor=actor, action=ACTION, object_type="index_maintenance", object_id="", request_id=str(request_id), after={"cancelled": True})
        return Response(receipt(row))


class IndexTermSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    term = serializers.CharField()
    entity_label = serializers.CharField()
    entity_type = serializers.CharField()
    language = serializers.CharField()
    term_type = serializers.CharField()
    trust_level = serializers.CharField()
    source_kind = serializers.CharField()
    public_active = serializers.BooleanField()
    admin_resolvable = serializers.BooleanField()
    edit_url = serializers.CharField(allow_blank=True)


class IndexTermsSerializer(serializers.Serializer):
    initialized = serializers.BooleanField()
    revision = serializers.IntegerField(allow_null=True)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    pages = serializers.IntegerField()
    entries = serializers.IntegerField()
    public_active_entries = serializers.IntegerField()
    pending_events = serializers.IntegerField()
    failed_events = serializers.IntegerField()
    terms = IndexTermSerializer(many=True)


class IndexTermsView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryStaff]

    @extend_schema(responses=IndexTermsSerializer, parameters=[OpenApiParameter(name, type=str) for name in ("q", "entity_type", "page")])
    def get(self, request):
        if not has_capability(request.user, Capability.VIEW_QUERY_LEXICON): raise PermissionDenied("当前账户不能查看查询词来源。")
        from catalog.discovery_index_views import _integer
        from catalog.services.query_lexicon.operations import query_lexicon_workspace
        payload = query_lexicon_workspace(query=str(request.query_params.get("q", ""))[:200], entity_type=request.query_params.get("entity_type", ""),
            limit=30, page=_integer(request.query_params, "page", 1, 100000))
        for row in payload["terms"]:
            entity_id = row["entity_id"]
            row["edit_url"] = {"person": f"/admin/people?source={entity_id}", "knowledge_node": f"/admin/theories/{entity_id}",
                "work": f"/admin/library/works/{entity_id}", "topic": f"/admin/topics/{entity_id}",
                "discipline": "/admin/theories/disciplines", "subdiscipline": "/admin/theories/subdisciplines", "theory_school": "/admin/theories"}.get(row["entity_type"], "")
        # No raw provenance or private source payload in the maintenance list.
        return Response(IndexTermsSerializer(payload).data)
