from __future__ import annotations

from django.core.paginator import Paginator
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError, transaction
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .editorial_read import AdminPrivateResponseMixin

from common.permissions import (
    CanAccessBackOffice,
    CanEditMetadata,
    CanPublishWork,
    CanWithdrawWork,
    IsKnowledgeEditor,
    IsCatalogEditor,
)
from ingestion.models import EntityResolutionCandidate, MetadataCandidate, UploadItem
from ingestion.services.publication import (
    PublicationBlocked,
    PublicationWarningsRequireConfirmation,
    publish_edition,
    withdraw_edition,
)

from catalog.models import (
    Edition,
    EditorialRevision,
    EnrichmentCandidate,
    TheoryReviewTask,
    Work,
)
from catalog.services.admin_workspace import (
    build_admin_workspace,
    serialize_work_library_row,
    work_library_queryset,
)
from catalog.services.work_editor import (
    WorkflowEditConflict,
    WorkflowEditError,
    intake_edition,
    maintenance_edition,
    save_workflow_section,
)
from catalog.services.editorial_revision import (
    EditorialRevisionConflict,
    EditorialRevisionError,
    publish_editorial_revision,
    save_workflow_editorial_revision,
    serialize_editorial_revision,
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


def _confirm_section(request_data) -> bool:
    value = request_data.get("confirm_section", True)
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in {"true", "1", "yes"}:
        return True
    if isinstance(value, str) and value.strip().lower() in {"false", "0", "no"}:
        return False
    raise WorkflowEditError("confirm_section 必须是布尔值。")


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
            confirm_section = _confirm_section(request.data)
            save_workflow_section(
                edition,
                step_key,
                serializer.validated_data,
                actor=request.user,
                confirm_section=confirm_section,
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


class WorkMaintenanceWorkspaceView(AdminPrivateResponseMixin, APIView):
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


class WorkspaceEditsSerializer(serializers.Serializer):
    edition_id = serializers.UUIDField()
    item_id = serializers.UUIDField(required=False, allow_null=True)
    edit_version = serializers.CharField(max_length=64)
    request_id = serializers.UUIDField()
    sections = serializers.DictField(child=serializers.DictField(), allow_empty=False)
    confirm_sections = serializers.ListField(child=serializers.ChoiceField(choices=list(SECTION_SERIALIZERS)), default=list)
    suggestions = serializers.ListField(child=serializers.DictField(), default=list, max_length=40)


class WorkWorkspaceEditsView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    def post(self, request, work_id):
        from catalog.field_assistant_views import FieldAssistantDecisionSerializer
        from catalog.services.field_assistant import FieldAssistantError
        from catalog.services.workspace_edits import save_workspace_edits

        serializer = WorkspaceEditsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        sections = {}
        for step, values in data["sections"].items():
            section_class = SECTION_SERIALIZERS.get(step)
            if section_class is None:
                raise serializers.ValidationError({"sections": "包含不能保存的内容。"})
            if step in {"knowledge", "curation"} and not IsKnowledgeEditor().has_permission(request, self):
                raise PermissionDenied(IsKnowledgeEditor.message)
            section = section_class(data=_section_input(step, {"data": values}), partial=True)
            section.is_valid(raise_exception=True)
            sections[step] = section.validated_data
        if set(data["confirm_sections"]) - set(sections):
            raise serializers.ValidationError({"confirm_sections": "请同时提交需要确认的内容。"})
        suggestions = []
        for row in data["suggestions"]:
            if not IsCatalogEditor().has_permission(request, self):
                raise PermissionDenied(IsCatalogEditor.message)
            suggestion = FieldAssistantDecisionSerializer(data={**row, "edition_id": data["edition_id"]})
            suggestion.is_valid(raise_exception=True)
            values = {key: value for key, value in suggestion.validated_data.items() if key != "edition_id"}
            if row.get("selected_entity_id"):
                values["selected_entity_id"] = serializers.UUIDField().run_validation(row["selected_entity_id"])
            suggestions.append(values)
        item = None
        if data.get("item_id"):
            item = UploadItem.objects.filter(pk=data["item_id"], edition_id=data["edition_id"]).first()
            if item is None:
                raise serializers.ValidationError({"item_id": "上传来源与当前版本不一致。"})
        try:
            edition, receipt, replayed = save_workspace_edits(
                work_id=work_id, edition_id=data["edition_id"], expected_version=data["edit_version"],
                request_id=str(data["request_id"]), sections=sections,
                confirmations=set(data["confirm_sections"]), suggestions=suggestions, actor=request.user,
            )
        except WorkflowEditError as error:
            return _edit_error(error)
        except EditorialRevisionConflict as error:
            return _edit_error(WorkflowEditConflict(str(error)))
        except (EditorialRevisionError, FieldAssistantError, ObjectDoesNotExist) as error:
            return Response({"detail": str(error), "code": "workspace_save_failed"}, status=400)
        except DatabaseError as error:
            sqlstate = getattr(error.__cause__, "sqlstate", "")
            if sqlstate not in {"55P03", "40P01", "40001"}:
                raise
            return Response({"detail": "书目正在被其他操作更新，请稍后重试。", "code": "workspace_busy"}, status=409)
        workspace = build_admin_workspace(edition, user=request.user, mode="intake" if item else "maintenance", item=item)
        workspace["save_result"] = {"request_id": str(receipt.request_id), "saved_at": receipt.created_at,
                                    "sections": receipt.after["sections"], "replayed": replayed}
        return Response(workspace)


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
            confirm_section = _confirm_section(request.data)
        except WorkflowEditError as error:
            return _edit_error(error)
        if step_key in {
            "work",
            "bibliography",
            "contributors",
            "classification",
            "knowledge",
            "reader",
        } and edition.work.editions.filter(
            state="published"
        ).exists():
            raw_values = dict(serializer.validated_data)
            change_note = str(raw_values.pop("note", "") or "")
            expected_edition = raw_values.pop("expected_updated_at", None)
            expected_work = raw_values.pop("expected_work_updated_at", None)
            if expected_edition is not None and edition.updated_at != expected_edition:
                return _edit_error(WorkflowEditConflict("当前版本已被其他操作更新，请刷新后重试。"))
            if expected_work is not None and edition.work.updated_at != expected_work:
                return _edit_error(WorkflowEditConflict("当前作品已被其他操作更新，请刷新后重试。"))
            if step_key == "work":
                patch = {
                    key: value
                    for key, value in raw_values.items()
                    if key in {
                        "document_type",
                        "title",
                        "subtitle",
                        "original_title",
                        "uniform_title",
                        "language",
                        "original_language",
                        "first_publication_date",
                        "translation_of",
                        "abstract",
                    }
                }
            elif step_key in {"classification", "knowledge"}:
                patch = {step_key: raw_values}
            else:
                patch = {
                    step_key: {
                        "edition_id": str(edition.id),
                        "values": raw_values,
                    }
                }
            try:
                from catalog.services.work_editor import save_editorial_workflow_section

                revision = save_editorial_workflow_section(
                    edition, step_key, raw_values,
                    confirm_section=confirm_section,
                    section_patch=patch,
                    actor=request.user,
                    idempotency_key=str(
                        request.headers.get("Idempotency-Key") or ""
                    ).strip(),
                    change_note=change_note or "馆藏维护工作台保存正式作品草稿",
                )
                if revision is not None:
                    workspace = build_admin_workspace(
                        edition,
                        user=request.user,
                        mode="maintenance",
                    )
                    workspace["editorial_revision"] = serialize_editorial_revision(revision)
                    return Response(workspace, status=status.HTTP_202_ACCEPTED)
                return Response(
                    build_admin_workspace(
                        edition,
                        user=request.user,
                        mode="maintenance",
                    )
                )
            except EditorialRevisionConflict as error:
                return _edit_error(WorkflowEditConflict(str(error)))
            except EditorialRevisionError as error:
                return Response(
                    {"detail": str(error), "code": "editorial_revision_error"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        try:
            result = save_workflow_section(
                edition,
                step_key,
                serializer.validated_data,
                actor=request.user,
                confirm_section=confirm_section,
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


class WorkLibraryListView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    def get(self, request):
        query = str(request.query_params.get("q") or "").strip()
        view = str(request.query_params.get("view") or "").strip()
        ordering = str(request.query_params.get("ordering") or "title")
        if ordering not in {"title", "-title", "updated_at", "-updated_at"}:
            return Response({"detail": "未知馆藏排序。"}, status=400)
        queryset = work_library_queryset(query=query, view=view, ordering=ordering)
        document_type = str(request.query_params.get("document_type") or "").strip()
        if document_type:
            queryset = queryset.filter(document_type=document_type)
        work_id = str(request.query_params.get("work_id") or "").strip()
        if work_id:
            from uuid import UUID

            try:
                queryset = queryset.filter(pk=UUID(work_id))
            except ValueError:
                return Response({"detail": "作品编号格式不正确。"}, status=400)
        edition_mode = view == "editions"
        if edition_mode:
            edition_order = {"title": "work__title", "-title": "-work__title"}.get(ordering, ordering)
            queryset = Edition.objects.filter(work_id__in=queryset.values("id")).order_by(edition_order, "work_id", "-is_primary", "-publication_year", "id")
            edition_id = str(request.query_params.get("edition_id") or "").strip()
            if edition_id:
                from uuid import UUID
                try:
                    queryset = queryset.filter(pk=UUID(edition_id))
                except ValueError:
                    return Response({"detail": "出版版本编号格式不正确。"}, status=400)
        try:
            page_number = max(1, int(request.query_params.get("page", 1)))
        except (TypeError, ValueError):
            page_number = 1
        paginator = Paginator(queryset, 40)
        page = paginator.get_page(page_number)
        from catalog.services.admin_queue import attach_library_editions, load_admin_editions, serialize_edition_library_row

        if edition_mode:
            results = [serialize_edition_library_row(row, user=request.user) for row in load_admin_editions(page.object_list)]
        else:
            results = [serialize_work_library_row(row, user=request.user) for row in attach_library_editions(list(page.object_list))]
        params = request.query_params.copy()

        def page_url(number):
            if not number:
                return None
            params["page"] = number
            return f"{request.path}?{params.urlencode()}"

        return Response(
            {
                "count": paginator.count,
                "page": page.number, "page_size": paginator.per_page, "total_pages": paginator.num_pages,
                "ordering": f"{ordering},work_id,-is_primary,-publication_year,id" if edition_mode else f"{ordering},id",
                "next": page_url(page.next_page_number()) if page.has_next() else None,
                "previous": page_url(page.previous_page_number()) if page.has_previous() else None,
                "results": results,
            }
        )


class WorkflowQueueView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    def get(self, request):
        from catalog.services.admin_queue import CATEGORIES
        from catalog.services.admin_queue_query import QUEUE_ORDERING, queue_page

        category = str(request.query_params.get("category") or "all")
        if category not in CATEGORIES:
            return Response({"detail": "未知待办分类。"}, status=400)
        ordering = str(request.query_params.get("ordering") or "priority")
        if ordering not in QUEUE_ORDERING:
            return Response({"detail": "未知待办排序方式。"}, status=400)
        source = str(request.query_params.get("source") or "").strip()
        public_state = str(request.query_params.get("publication") or "").strip()
        query = str(request.query_params.get("q") or "").strip().casefold()
        page, counts, rows, groups = queue_page(
            user=request.user, category=category, page=request.query_params.get("page", 1),
            source=source, publication=public_state, query=query, ordering=ordering,
            publication_scope=request.query_params.get("scope") == "publication",
        )
        paginator = page.paginator
        params = request.query_params.copy()

        def page_url(number):
            params["page"] = number
            return f"{request.path}?{params.urlencode()}"
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
                "count": paginator.count, "page": page.number, "page_size": paginator.per_page,
                "total_pages": paginator.num_pages, "counts": counts, "ordering": "-priority,updated_at,id" if ordering == "priority" else f"{ordering},id",
                "next": page_url(page.next_page_number()) if page.has_next() else None,
                "previous": page_url(page.previous_page_number()) if page.has_previous() else None,
                "results": rows,
                "continue_items": groups["continue"][:12],
                "attention_items": groups["attention"][:12],
                "exception_items": groups["exception"][:12],
                "publication_ready": groups["publication_ready"][:12],
                "recent_items": rows[:12],
                "candidate_review_count": candidate_count,
            }
        )


class WorkMaintenancePublicationView(APIView):
    permission_classes = [CanPublishWork]

    def get_permissions(self):
        if self.request.method == "POST" and str(self.request.data.get("action") or "").strip().casefold() == "withdraw":
            return [CanWithdrawWork()]
        return super().get_permissions()

    def publication_response(self, request, work_id, edition, *, published_revision=None, receipt=None, replayed=False):
        from catalog.services.publication_commands import catalog_publication_state

        workspace = build_admin_workspace(edition, user=request.user, mode="maintenance")
        visibility = catalog_publication_state(edition)
        return Response({
            **workspace, **visibility, "intelligence_status": edition.intelligence_status,
            "published_editorial_revision": serialize_editorial_revision(published_revision) if published_revision else None,
            "maintenance_url": f"/admin/library/works/{work_id}?edition={edition.pk}#publication",
            "work_id": str(work_id), "context": workspace["context"],
            "request_receipt": {"id": str(receipt.pk), "accepted": True, "replayed": replayed,
                                "accepted_at": receipt.created_at} if receipt else None,
            **({"detail": "此前发布请求已确认；已读取当前状态，没有再次发布或覆盖后续修改。"} if replayed else {}),
        })

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
        published_revision = None
        receipt = None
        try:
            # One publication action owns the complete public mutation.  A
            # warning or blocker raised by Edition publication therefore also
            # rolls back a pending Work EditorialRevision and its projection
            # events instead of leaving a half-published canonical object.
            with transaction.atomic():
                # The existing publication service can touch sibling Editions.
                # Claim the Work first, then all its Editions without waiting:
                # an older Edition-first worker must not form a lock cycle.
                Work.objects.select_for_update().get(pk=edition.work_id)
                editions = list(Edition.objects.filter(work_id=edition.work_id).order_by("id").select_for_update(of=("self",), nowait=True))
                edition = next(row for row in editions if row.pk == edition.pk)
                if request.data.get("prepared_fingerprint"):
                    from catalog.services.publication_commands import prepare_revision
                    from ingestion.models import AuditEvent

                    receipt = AuditEvent.objects.filter(
                        action="catalog.publication_requested", object_type="Edition", object_id=str(edition.pk), actor=request.user,
                        after__prepared_fingerprint=request.data["prepared_fingerprint"],
                    ).first()
                    if receipt is not None:
                        return self.publication_response(request, work_id, edition, receipt=receipt, replayed=True)
                    if prepare_revision(edition)["fingerprint"] != request.data["prepared_fingerprint"]:
                        raise PublicationBlocked(["内容已在准备发布后变化，请重新检查差异。"])
                pending_revision = (
                    EditorialRevision.objects.select_for_update()
                    .filter(
                        target_type=EditorialRevision.TargetType.WORK,
                        target_id=edition.work_id,
                        status=EditorialRevision.Status.DRAFT,
                    )
                    .order_by("-revision")
                    .first()
                )
                if pending_revision is not None:
                    from catalog.services.publication_commands import pending_edition_supplement, editorial_draft_applies_to_edition

                    if not editorial_draft_applies_to_edition(pending_revision, edition):
                        raise PublicationBlocked(["待发布草稿属于此作品的另一个出版版本，请打开对应版本核对后发布。"])
                    supplementary_reader = pending_edition_supplement(edition)
                    published_revision = publish_editorial_revision(
                        pending_revision.id,
                        actor=request.user,
                        content_asset_id=supplementary_reader.pk if supplementary_reader else None,
                    )
                edition = Edition.objects.select_related("work").get(pk=edition.pk)
                edition = publish_edition(
                    edition,
                    actor=request.user,
                    idempotency_key=(
                        f"maintenance:{edition.id}:revision:{published_revision.id}"
                        if published_revision is not None
                        else f"maintenance:{edition.id}:{edition.updated_at.isoformat()}"
                    ),
                    allow_low_confidence=True,
                    confirm_warnings=confirmed,
                    force_update=published_revision is not None,
                    changed_fields=(
                        published_revision.changed_fields
                        if published_revision is not None
                        else None
                    ),
                )
                if request.data.get("prepared_fingerprint"):
                    receipt = AuditEvent.objects.create(
                        action="catalog.publication_requested", object_type="Edition", object_id=str(edition.pk), actor=request.user,
                        after={"prepared_fingerprint": request.data["prepared_fingerprint"],
                               "editorial_revision_id": str(published_revision.pk) if published_revision else None,
                               "publication_revision_id": str(edition.catalog_revisions.order_by("-revision").values_list("pk", flat=True).first() or "")},
                    )
        except DatabaseError as error:
            if getattr(error.__cause__, "sqlstate", None) == "55P03":
                return Response({"code": "publication.concurrent_edit", "detail": "此作品的出版版本正在被其他操作处理，请稍后刷新后重试。"}, status=409)
            raise
        except PublicationBlocked as error:
            return Response(
                {"detail": "还有信息需要处理，暂时无法发布。", "blockers": error.reasons},
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
        except (EditorialRevisionConflict, EditorialRevisionError) as error:
            return Response(
                {
                    "detail": str(error),
                    "code": (
                        "editorial_revision_conflict"
                        if isinstance(error, EditorialRevisionConflict)
                        else "editorial_revision_error"
                    ),
                },
                status=(
                    status.HTTP_409_CONFLICT
                    if isinstance(error, EditorialRevisionConflict)
                    else status.HTTP_400_BAD_REQUEST
                ),
            )
        return self.publication_response(request, work_id, edition, published_revision=published_revision, receipt=receipt)
