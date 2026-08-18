from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.models import ProcessingJob

from common.permissions import (
    CanAccessBackOffice,
    CanManageQueryLexicon,
    CanViewQueryLexicon,
    CanViewEvidence,
    CanViewSystemStatus,
    IsCatalogEditor,
)

from catalog.services.backoffice import (
    intake_workspace,
    knowledge_workspace,
    projection_status,
    query_lexicon_term_inspector,
    system_status_snapshot,
)
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
    permission_classes = [CanAccessBackOffice]

    def get(self, request):
        return Response(
            knowledge_workspace(
                status=request.query_params.get("status", "pending"),
                entity_type=request.query_params.get("entity_type", ""),
                work_id=request.query_params.get("work_id", ""),
            )
        )


class AdminProjectionStatusView(APIView):
    permission_classes = [CanViewEvidence]

    def get(self, request, target_type, target_id):
        return Response(projection_status(target_type=target_type, target_id=target_id))


class AdminSystemStatusView(APIView):
    permission_classes = [CanViewSystemStatus]

    def get(self, request):
        return Response(system_status_snapshot())


class AdminIntakeWorkspaceView(APIView):
    permission_classes = [CanAccessBackOffice]

    def get(self, request, item_id):
        payload = intake_workspace(item_id=str(item_id))
        if not payload.get("exists"):
            return Response({"detail": "上架项目不存在。"}, status=status.HTTP_404_NOT_FOUND)
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
