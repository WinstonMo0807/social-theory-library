from __future__ import annotations

from django.core.paginator import Paginator
from django.db.models import Count, Q
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import (
    CanAccessBackOffice,
    CanEditMetadata,
    CanPublishWork,
    IsKnowledgeEditor,
)
from ingestion.models import EntityResolutionCandidate, MetadataCandidate, UploadItem
from ingestion.services.indexing import index_asset
from ingestion.services.publication import (
    PublicationBlocked,
    PublicationWarningsRequireConfirmation,
    publish_edition,
    withdraw_edition,
)

from catalog.models import Asset, Edition, EnrichmentCandidate, TheoryReviewTask, Work
from catalog.services.admin_workspace import (
    QUEUE_STATUSES,
    build_admin_workspace,
    serialize_work_library_row,
    serialize_workflow_queue_item,
    work_library_queryset,
)
from catalog.services.work_editor import (
    WorkflowEditConflict,
    WorkflowEditError,
    intake_edition,
    maintenance_edition,
    save_workflow_section,
)
from catalog.workflow_serializers import SECTION_SERIALIZERS


def _edit_error(error: WorkflowEditError) -> Response:
    return Response(
        {
            "detail": str(error),
            "code": "workflow_edit_conflict"
            if isinstance(error, WorkflowEditConflict)
            else "workflow_edit_error",
        },
        status=(
            status.HTTP_409_CONFLICT
            if isinstance(error, WorkflowEditConflict)
            else status.HTTP_400_BAD_REQUEST
        ),
    )


def _section_input(step_key: str, request_data) -> dict:
    root = dict(request_data)
    values = dict(root.get("data") or root)
    for key in ("expected_updated_at", "expected_work_updated_at", "note"):
        if key in root and key not in values:
            values[key] = root[key]
    if step_key == "contributors" and "contributors" not in values:
        values["contributors"] = [
            {
                "person_id": row.get("person_id"),
                "role": row.get("role", "author"),
                "order": row.get("order", index),
            }
            for index, row in enumerate(values.get("items") or [])
            if row.get("person_id")
        ]
    if step_key == "classification" and "disciplines" not in values:
        values["disciplines"] = [
            {**row, "is_primary": True}
            for row in values.get("primary_disciplines") or []
            if row.get("id")
        ] + [
            {**row, "is_primary": False}
            for row in values.get("related_disciplines") or []
            if row.get("id")
        ]
        values["subdisciplines"] = [
            row for row in values.get("subdisciplines") or [] if row.get("id")
        ]
    if step_key == "knowledge" and not any(
        key in values for key in ("theories", "topics", "nodes")
    ):
        values["theories"] = []
        values["topics"] = []
        values["nodes"] = []
        for row in values.get("relations") or []:
            target_id = row.get("target_id")
            if not target_id:
                continue
            target_type = row.get("target_type")
            base = {
                "id": target_id,
                "strength": row.get("strength", "medium"),
                "is_primary": bool(row.get("is_primary")),
            }
            if target_type == "theory":
                values["theories"].append(
                    {
                        **base,
                        "role": row.get("role", "local_mention"),
                        "evidence_asset": row.get("evidence_asset"),
                        "evidence_page": row.get("evidence_page"),
                        "evidence_printed_label": row.get(
                            "evidence_printed_label", ""
                        ),
                        "evidence_text": row.get("evidence_text")
                        or row.get("evidence_summary", ""),
                    }
                )
            elif target_type == "topic":
                values["topics"].append(
                    {
                        **base,
                        "evidence_asset": row.get("evidence_asset"),
                        "evidence_page": row.get("evidence_page"),
                        "evidence_printed_label": row.get(
                            "evidence_printed_label", ""
                        ),
                        "evidence_text": row.get("evidence_text")
                        or row.get("evidence_summary", ""),
                    }
                )
            elif target_type == "knowledge_node":
                values["nodes"].append(
                    {
                        **base,
                        "role": row.get("role", "general_mention"),
                    }
                )
    if step_key == "curation":
        values["skip"] = bool(root.get("skip") or values.get("skip") or values.get("skipped"))
    return values


class WorkflowSectionPermissionMixin:
    def get_permissions(self):
        step_key = self.kwargs.get("step_key", "")
        permission_class = (
            IsKnowledgeEditor if step_key in {"knowledge", "curation"} else CanEditMetadata
        )
        return [permission_class()]


class IntakeWorkflowSectionView(WorkflowSectionPermissionMixin, APIView):
    def patch(self, request, item_id, step_key):
        try:
            item, edition = intake_edition(item_id)
        except WorkflowEditError as error:
            return _edit_error(error)
        serializer_class = SECTION_SERIALIZERS.get(step_key)
        if serializer_class is None:
            return Response({"detail": "未知或不可编辑的工作流步骤。"}, status=400)
        serializer = serializer_class(data=_section_input(step_key, request.data), partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            save_workflow_section(
                edition,
                step_key,
                serializer.validated_data,
                actor=request.user,
            )
        except WorkflowEditError as error:
            return _edit_error(error)
        item.refresh_from_db()
        return Response(
            build_admin_workspace(
                item.edition,
                user=request.user,
                mode="intake",
                item=item,
            )
        )


class WorkMaintenanceWorkspaceView(APIView):
    permission_classes = [CanAccessBackOffice]

    def get(self, request, work_id):
        try:
            edition = maintenance_edition(
                work_id,
                edition_id=request.query_params.get("edition"),
            )
        except WorkflowEditError as error:
            return _edit_error(error)
        return Response(
            build_admin_workspace(
                edition,
                user=request.user,
                mode="maintenance",
            )
        )


class WorkMaintenanceSectionView(WorkflowSectionPermissionMixin, APIView):
    def patch(self, request, work_id, step_key):
        try:
            edition = maintenance_edition(
                work_id,
                edition_id=request.query_params.get("edition"),
            )
        except WorkflowEditError as error:
            return _edit_error(error)
        serializer_class = SECTION_SERIALIZERS.get(step_key)
        if serializer_class is None:
            return Response({"detail": "未知或不可编辑的工作流步骤。"}, status=400)
        serializer = serializer_class(data=_section_input(step_key, request.data), partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            result = save_workflow_section(
                edition,
                step_key,
                serializer.validated_data,
                actor=request.user,
            )
        except WorkflowEditError as error:
            return _edit_error(error)
        return Response(
            build_admin_workspace(
                result.edition,
                user=request.user,
                mode="maintenance",
            )
        )


class WorkLibraryListView(APIView):
    permission_classes = [CanAccessBackOffice]

    def get(self, request):
        query = str(request.query_params.get("q") or "").strip()
        view = str(request.query_params.get("view") or "").strip()
        queryset = work_library_queryset(query=query, view=view)
        try:
            page_number = max(1, int(request.query_params.get("page", 1)))
        except (TypeError, ValueError):
            page_number = 1
        paginator = Paginator(queryset, 40)
        page = paginator.get_page(page_number)
        params = request.query_params.copy()

        def page_url(number):
            if not number:
                return None
            params["page"] = number
            return f"{request.path}?{params.urlencode()}"

        return Response(
            {
                "count": paginator.count,
                "next": page_url(page.next_page_number()) if page.has_next() else None,
                "previous": page_url(page.previous_page_number()) if page.has_previous() else None,
                "results": [serialize_work_library_row(work) for work in page.object_list],
            }
        )


class WorkflowQueueView(APIView):
    permission_classes = [CanAccessBackOffice]

    def get(self, request):
        items = list(
            UploadItem.objects.filter(
                status__in=QUEUE_STATUSES,
                edition__isnull=False,
            )
            .select_related("edition__work")
            .order_by("-priority", "-updated_at")[:30]
        )
        rows = [serialize_workflow_queue_item(item) for item in items]
        continue_items = [row for row in rows if row["overall_status"] in {"working", "draft"}]
        attention_items = [row for row in rows if row["overall_status"] == "attention"]
        exception_items = [row for row in rows if row["blockers_count"]]
        publication_ready = [
            row
            for row in rows
            if row["current_step"] == "publication" and not row["blockers_count"]
        ]
        candidate_count = MetadataCandidate.objects.filter(
            lifecycle=MetadataCandidate.Lifecycle.PROPOSED
        ).count()
        candidate_count += EntityResolutionCandidate.objects.filter(
            status=EntityResolutionCandidate.Status.PROPOSED
        ).count()
        candidate_count += EnrichmentCandidate.objects.filter(
            status=EnrichmentCandidate.Status.PENDING
        ).count()
        candidate_count += TheoryReviewTask.objects.filter(
            status=TheoryReviewTask.TaskStatus.PENDING
        ).count()
        return Response(
            {
                "continue_items": continue_items[:12],
                "attention_items": attention_items[:12],
                "exception_items": exception_items[:12],
                "publication_ready": publication_ready[:12],
                "recent_items": rows[:12],
                "candidate_review_count": candidate_count,
            }
        )


class WorkMaintenancePublicationView(APIView):
    permission_classes = [CanPublishWork]

    def post(self, request, work_id):
        try:
            edition = maintenance_edition(
                work_id,
                edition_id=request.query_params.get("edition")
                or request.data.get("edition_id"),
            )
        except WorkflowEditError as error:
            return _edit_error(error)
        action = str(request.data.get("action") or "publish").strip().casefold()
        if action == "withdraw":
            edition = withdraw_edition(
                edition,
                actor=request.user,
                reason=str(request.data.get("reason") or ""),
            )
            return Response(
                {
                    **build_admin_workspace(
                        edition,
                        user=request.user,
                        mode="maintenance",
                    ),
                    "detail": "馆藏版本已下架，文件和历史记录仍保留。",
                }
            )
        confirmed = request.data.get("confirm_warnings") is True or str(
            request.data.get("confirm_warnings") or ""
        ).casefold() in {"1", "true", "yes"}
        try:
            edition = publish_edition(
                edition,
                actor=request.user,
                idempotency_key=f"maintenance:{edition.id}:{edition.updated_at.isoformat()}",
                allow_low_confidence=True,
                confirm_warnings=confirmed,
            )
        except PublicationBlocked as error:
            return Response(
                {"detail": "存在阻止发布的技术问题。", "blockers": error.reasons},
                status=409,
            )
        except PublicationWarningsRequireConfirmation as error:
            return Response(
                {
                    "detail": "发布前请确认警告。",
                    "warnings": error.warnings,
                    "confirmation_required": True,
                },
                status=409,
            )
        index_warning = ""
        normalized = edition.assets.filter(
            kind=Asset.Kind.NORMALIZED,
            status=Asset.Status.READY,
            is_current=True,
        ).first()
        if normalized:
            try:
                index_asset(normalized, is_public=True)
            except Exception as error:  # Publication is intentionally preserved.
                index_warning = str(error)[:2000]
        workspace = build_admin_workspace(
            edition,
            user=request.user,
            mode="maintenance",
        )
        return Response(
            {
                **workspace,
                "detail": "馆藏版本已发布。",
                "index_warning": index_warning,
                "maintenance_url": f"/admin/library/works/{work_id}#publication",
                "work_id": str(work_id),
                "context": workspace["context"],
            }
        )
