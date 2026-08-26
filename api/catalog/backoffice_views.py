from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.models import ProcessingJob, UploadItem
from catalog.models import HealthIncident, PromptRegistryEntry, ResearchTaskProfile

from common.permissions import (
    CanAccessBackOffice,
    CanManageQueryLexicon,
    CanManagePromptRegistry,
    CanRetryJobs,
    CanViewQueryLexicon,
    CanViewEvidence,
    CanViewSystemStatus,
    IsCatalogEditor,
)
from common.capabilities import Capability, has_capability

from catalog.services.backoffice import (
    knowledge_workspace,
    projection_status,
    query_lexicon_term_inspector,
    system_status_snapshot,
)
from catalog.services.admin_workspace import build_admin_workspace
from catalog.serializers import AdminWorkPagePreviewSerializer
from catalog.services.query_lexicon.operations import (
    enqueue_query_lexicon_reconciliation,
    reconcile_preview,
    serialize_job,
)


class AdminQueryLexiconWorkspaceView(APIView):
    """Read-only inspector plus explicit dry-run/reconcile actions."""

    def get_permissions(self):
        return [CanManageQueryLexicon()] if self.request.method == "POST" else [CanViewQueryLexicon()]

    def get(self, request):
        from catalog.services.query_lexicon.operations import query_lexicon_workspace

        payload = query_lexicon_workspace(
                query=request.query_params.get("q", ""),
                entity_type=request.query_params.get("entity_type", ""),
                limit=request.query_params.get("limit", 60),
            )
        payload["permissions"] = {
            "can_manage": CanManageQueryLexicon().has_permission(request, self),
        }
        return Response(payload)

    def post(self, request):
        action = str(request.data.get("action") or "").strip().casefold()
        if action == "dry_run":
            try:
                return Response(reconcile_preview())
            except Exception as exc:
                return Response(
                    {"status": "failed", "error_category": exc.__class__.__name__, "detail": str(exc)[:500]},
                    status=status.HTTP_409_CONFLICT,
                )
        if action == "reconcile":
            try:
                job = enqueue_query_lexicon_reconciliation(actor=request.user)
                return Response(serialize_job(job), status=status.HTTP_202_ACCEPTED)
            except Exception as exc:
                return Response(
                    {"status": "failed", "error_category": exc.__class__.__name__, "detail": str(exc)[:500]},
                    status=status.HTTP_409_CONFLICT,
                )
        return Response({"detail": "action 必须是 dry_run 或 reconcile。"}, status=status.HTTP_400_BAD_REQUEST)


class AdminQueryLexiconTermInspectorView(APIView):
    permission_classes = [CanViewQueryLexicon]

    def get(self, request):
        return Response(
            query_lexicon_term_inspector(
                query=request.query_params.get("q", ""),
                entity_type=request.query_params.get("entity_type", ""),
                limit=request.query_params.get("limit", 60),
            )
        )


class AdminKnowledgeWorkspaceView(APIView):
    permission_classes = [CanAccessBackOffice, CanViewEvidence]

    def get(self, request):
        from catalog.services.knowledge_studio import knowledge_studio_workspace

        # Keep the established candidate overview in the response while the
        # Studio adds a bounded read model over canonical, derived and draft
        # stores.  All mutations remain on their specialist endpoints.
        payload = knowledge_workspace(
            status=request.query_params.get("status", "pending"),
            entity_type=request.query_params.get("entity_type", ""),
            work_id=request.query_params.get("work_id", ""),
        )
        payload["studio"] = knowledge_studio_workspace(
            query=request.query_params.get("q", ""),
            object_type=request.query_params.get("object_type", ""),
            selected_type=request.query_params.get("selected_type", ""),
            selected_id=request.query_params.get("selected_id", ""),
            limit=request.query_params.get("limit", 40),
            reviewer=request.user,
        )
        return Response(payload)


def _prompt_registry_row(prompt: PromptRegistryEntry) -> dict:
    return {
        "id": str(prompt.id),
        "key": prompt.key,
        "version": prompt.version,
        "capability": prompt.capability,
        "task_profile_key": prompt.task_profile_key,
        "content": prompt.content,
        "output_schema": prompt.output_schema,
        "provider_guidance": prompt.provider_guidance,
        "content_hash": prompt.content_hash,
        "schema_hash": prompt.schema_hash,
        "status": prompt.status,
        "created_by": str(prompt.created_by_id) if prompt.created_by_id else None,
        "activated_by": (
            str(prompt.activated_by_id) if prompt.activated_by_id else None
        ),
        "activated_at": prompt.activated_at,
        "created_at": prompt.created_at,
        "updated_at": prompt.updated_at,
    }


class AdminPromptRegistryView(APIView):
    """Immutable prompt revisions with explicit Superadmin activation."""

    permission_classes = [CanManagePromptRegistry]

    def get(self, request):
        queryset = PromptRegistryEntry.objects.all()
        key = str(request.query_params.get("key") or "").strip()
        status_value = str(request.query_params.get("status") or "").strip()
        if key:
            queryset = queryset.filter(key=key)
        if status_value:
            queryset = queryset.filter(status=status_value)
        try:
            limit = max(1, min(int(request.query_params.get("limit", 100)), 200))
        except (TypeError, ValueError):
            limit = 100
        profiles = list(
            ResearchTaskProfile.objects.filter(is_active=True)
            .order_by("key")
            .values(
                "key",
                "version",
                "name",
                "prompt_key",
                "required_capability",
            )
        )
        return Response(
            {
                "immutable_revisions": True,
                "activation_requires_superadmin": True,
                "results": [
                    _prompt_registry_row(row)
                    for row in queryset.order_by("key", "-version")[:limit]
                ],
                "active_task_profiles": profiles,
            }
        )

    def post(self, request):
        from common.ai_runtime import AICapability
        from catalog.services.research.prompt_registry import (
            activate_prompt_revision,
            create_prompt_revision,
        )

        action = str(request.data.get("action") or "create_revision").strip().casefold()
        try:
            if action == "create_revision":
                output_schema = request.data.get("output_schema") or {}
                provider_guidance = request.data.get("provider_guidance") or {}
                if not isinstance(output_schema, dict):
                    return Response(
                        {"output_schema": ["output_schema 必须是 JSON 对象。"]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if not isinstance(provider_guidance, dict):
                    return Response(
                        {"provider_guidance": ["provider_guidance 必须是 JSON 对象。"]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                capability = str(request.data.get("capability") or "").strip()
                if capability not in AICapability.VALUES:
                    return Response(
                        {"capability": ["请选择已注册的 AI capability。"]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                prompt = create_prompt_revision(
                    key=request.data.get("key", ""),
                    capability=capability,
                    content=request.data.get("content", ""),
                    output_schema=output_schema,
                    actor=request.user,
                    task_profile_key=request.data.get("task_profile_key", ""),
                    provider_guidance=provider_guidance,
                )
                return Response(
                    _prompt_registry_row(prompt),
                    status=status.HTTP_201_CREATED,
                )
            if action == "activate":
                prompt = get_object_or_404(
                    PromptRegistryEntry,
                    pk=request.data.get("prompt_id"),
                )
                return Response(
                    _prompt_registry_row(
                        activate_prompt_revision(prompt=prompt, actor=request.user)
                    )
                )
        except (PermissionError, ValueError) as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"detail": "action 必须是 create_revision 或 activate。"},
            status=status.HTTP_400_BAD_REQUEST,
        )


class AdminProjectionStatusView(APIView):
    permission_classes = [CanViewEvidence]

    def get(self, request, target_type, target_id):
        return Response(projection_status(target_type=target_type, target_id=target_id))


class AdminSystemStatusView(APIView):
    permission_classes = [CanViewSystemStatus]

    def get(self, request):
        return Response(system_status_snapshot())


class AdminFunctionalHealthView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [CanViewSystemStatus(), CanRetryJobs()]
        return [CanViewSystemStatus()]

    def get(self, request):
        from catalog.services.system_health import functional_health_snapshot

        return Response(functional_health_snapshot())

    def post(self, request):
        from catalog.services.system_health import (
            functional_health_snapshot,
            request_recovery,
            run_health_probe,
        )

        action = str(request.data.get("action") or "").strip().casefold()
        if action == "run_probe":
            try:
                run = run_health_probe(
                    str(request.data.get("probe_key") or ""),
                    source="manual",
                    actor=request.user,
                )
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            return Response({
                "id": str(run.id),
                "probe_key": run.probe_key,
                "status": run.status,
                "snapshot": functional_health_snapshot(),
            })
        if action == "recover":
            recovery_action = str(request.data.get("recovery_action") or "").strip().casefold()
            elevated_capability = {
                "recover_query_lexicon": Capability.MANAGE_QUERY_LEXICON,
                "recover_semantic_queue": Capability.MANAGE_SEMANTIC_INDEX,
            }.get(recovery_action)
            if elevated_capability and not has_capability(request.user, elevated_capability):
                return Response(
                    {"detail": "当前账户不能执行该系统恢复动作。"},
                    status=status.HTTP_403_FORBIDDEN,
                )
            incident = get_object_or_404(HealthIncident, pk=request.data.get("incident_id"))
            try:
                recovery, created = request_recovery(
                    incident,
                    action=recovery_action,
                    actor=request.user,
                    request_key=str(request.data.get("idempotency_key") or ""),
                )
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            return Response({
                "id": str(recovery.id),
                "status": recovery.status,
                "action": recovery.action,
                "created": created,
            }, status=status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK)
        return Response(
            {"detail": "action 必须是 run_probe 或 recover。"},
            status=status.HTTP_400_BAD_REQUEST,
        )


class AdminIntakeWorkspaceView(APIView):
    permission_classes = [CanAccessBackOffice]

    def get(self, request, item_id):
        item = UploadItem.objects.select_related("edition__work").filter(pk=item_id).first()
        if item is None:
            return Response({"detail": "上架项目不存在。"}, status=status.HTTP_404_NOT_FOUND)
        if item.edition_id is None:
            from catalog.services.admin_workflow import build_intake_workflow

            legacy = {
                "mode": "intake",
                "context": {
                    "item_id": str(item.id),
                    "title": item.source_filename,
                    "filename": item.source_filename,
                    "return_href": "/admin/review",
                },
                "workflow": build_intake_workflow(item),
                "data": {
                    "file": {
                        "filename": item.source_filename,
                        "status": item.status,
                        "workflow_state": item.workflow_state,
                        "error_code": item.error_code,
                        "error_message": item.error_message,
                        "can_retry": item.status == UploadItem.Status.FAILED,
                    }
                },
                "candidates": {},
                "permissions": {"can_edit": True, "can_publish": False},
                "queue": {"return_href": "/admin/review"},
            }
            return Response(legacy)
        return Response(
            build_admin_workspace(
                item.edition,
                user=request.user,
                mode="intake",
                item=item,
            )
        )


class AdminWorkPagePreviewView(APIView):
    permission_classes = [CanViewEvidence]

    def get(self, request, edition_id):
        from catalog.models import Edition, EditorialRevision
        from catalog.services.editorial_revision import serialize_editorial_revision

        edition = get_object_or_404(
            Edition.objects.select_related("work").prefetch_related(
                "assets__pages",
                "contributions__person",
                "work__editions",
                "work__knowledge_relations",
                "work__discipline_relations__discipline",
                "work__subdiscipline_relations__subdiscipline",
                "work__node_relations__node",
                "work__node_relations__evidence",
            ),
            pk=edition_id,
        )
        normalized = edition.assets.filter(
            kind="normalized",
            is_current=True,
            status="ready",
        ).order_by("-version").first()
        draft_revision = EditorialRevision.objects.filter(
            target_type=EditorialRevision.TargetType.WORK,
            target_id=edition.work_id,
            status=EditorialRevision.Status.DRAFT,
        ).order_by("-revision").first()
        data = AdminWorkPagePreviewSerializer(
            edition.work,
            context={
                "request": request,
                "preview_edition": edition,
                "editorial_preview": (
                    draft_revision.materialized_preview if draft_revision else None
                ),
            },
        ).data
        return Response({
            "preview_mode": True,
            "publication_state": edition.state,
            "editorial_revision": (
                serialize_editorial_revision(draft_revision)
                if draft_revision is not None
                else None
            ),
            "public_url": f"/works/{edition.public_slug}" if edition.state == "published" and edition.public_slug else "",
            "pdf_preview_url": f"/api/distribution/admin/assets/{normalized.id}/preview/" if normalized else "",
            "work": data,
        })


class AdminKnowledgeObjectPreviewView(APIView):
    """Protected draft/public preview backed by the public serializer contract."""

    permission_classes = [CanViewEvidence]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response

    def get(self, request, object_type, object_id):
        from catalog.services.knowledge_studio import knowledge_object_preview_payload

        payload = knowledge_object_preview_payload(
            object_type=object_type,
            object_id=str(object_id),
            reviewer=request.user,
        )
        if payload is None:
            return Response(
                {"detail": "知识对象不存在，或对象类型与标识不匹配。"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(payload)


class AdminProjectionRefreshView(APIView):
    """Queue a bounded, explicit projection refresh without touching source data."""

    permission_classes = [IsCatalogEditor]

    def post(self, request, target_type, target_id):
        from catalog.services.projection_refresh import queue_projection_refresh

        try:
            force_value = request.data.get("force", False)
            force = force_value is True or str(force_value).strip().casefold() in {"1", "true", "yes"}
            job = queue_projection_refresh(
                target_type=target_type,
                target_id=str(target_id),
                actor=request.user,
                force=force,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "job_id": str(job.id),
                "status": job.status,
                "target_type": target_type,
                "target_id": str(target_id),
                "queued": bool(job.task_id and job.status == ProcessingJob.Status.PENDING),
                "detail": "已建立幂等投影刷新任务，具体投影由现有 worker 处理。",
            },
            status=status.HTTP_202_ACCEPTED,
        )
