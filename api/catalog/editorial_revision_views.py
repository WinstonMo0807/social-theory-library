from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.capabilities import Capability, has_capability
from common.permissions import CanAccessBackOffice

from .models import CanonicalObjectRevision, EditorialRevision
from .editorial_read import AdminPrivateResponseMixin
from .services.editorial_revision import (
    EditorialRevisionConflict,
    EditorialRevisionError,
    changed_editorial_patch,
    create_editorial_revision,
    editorial_idempotency_key,
    publish_editorial_revision,
    serialize_editorial_revision,
    TARGET_POLICIES,
)


EDIT_CAPABILITY = {
    EditorialRevision.TargetType.WORK: Capability.EDIT_METADATA,
    EditorialRevision.TargetType.EDITION: Capability.EDIT_METADATA,
    EditorialRevision.TargetType.KNOWLEDGE_NODE: Capability.EDIT_DRAFT_AUTHORITY,
    EditorialRevision.TargetType.SCHOLAR_PROFILE: Capability.EDIT_DRAFT_AUTHORITY,
    EditorialRevision.TargetType.DISCIPLINE: Capability.EDIT_DRAFT_AUTHORITY,
    EditorialRevision.TargetType.SUBDISCIPLINE: Capability.EDIT_DRAFT_AUTHORITY,
    EditorialRevision.TargetType.TOPIC: Capability.EDIT_DRAFT_AUTHORITY,
    EditorialRevision.TargetType.PUBLISHER: Capability.EDIT_DRAFT_AUTHORITY,
    EditorialRevision.TargetType.READING_PATH: Capability.EDIT_DRAFT_AUTHORITY,
}

PUBLISH_CAPABILITY = {
    EditorialRevision.TargetType.WORK: Capability.PUBLISH_WORK,
    EditorialRevision.TargetType.EDITION: Capability.PUBLISH_WORK,
    EditorialRevision.TargetType.KNOWLEDGE_NODE: Capability.PUBLISH_AUTHORITY,
    EditorialRevision.TargetType.SCHOLAR_PROFILE: Capability.PUBLISH_AUTHORITY,
    EditorialRevision.TargetType.DISCIPLINE: Capability.PUBLISH_AUTHORITY,
    EditorialRevision.TargetType.SUBDISCIPLINE: Capability.PUBLISH_AUTHORITY,
    EditorialRevision.TargetType.TOPIC: Capability.PUBLISH_AUTHORITY,
    EditorialRevision.TargetType.PUBLISHER: Capability.PUBLISH_AUTHORITY,
    EditorialRevision.TargetType.READING_PATH: Capability.PUBLISH_AUTHORITY,
}


def _permission_response(request, target_type: str, *, publish: bool = False):
    capability = (PUBLISH_CAPABILITY if publish else EDIT_CAPABILITY).get(target_type)
    if capability is None:
        return Response({"detail": "该对象类型尚不支持编辑草稿。"}, status=400)
    if not has_capability(request.user, capability):
        detail = "当前账户不能发布该编辑草稿。" if publish else "当前账户不能编辑该对象。"
        return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)
    return None


def _error_response(error: EditorialRevisionError):
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


class AdminEditorialRevisionListCreateView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    def get(self, request):
        queryset = EditorialRevision.objects.select_related("created_by", "published_by")
        target_type = str(request.query_params.get("target_type") or "").strip()
        target_id = str(request.query_params.get("target_id") or "").strip()
        status_value = str(request.query_params.get("status") or "").strip()
        if target_type:
            queryset = queryset.filter(target_type=target_type)
        if target_id:
            queryset = queryset.filter(target_id=target_id)
        if status_value:
            queryset = queryset.filter(status=status_value)
        try:
            limit = min(100, max(1, int(request.query_params.get("limit", 30))))
        except (TypeError, ValueError):
            limit = 30
        rows = list(queryset.order_by("-created_at")[:limit])
        return Response(
            {
                "count": queryset.count(),
                "results": [serialize_editorial_revision(row) for row in rows],
            }
        )

    def post(self, request):
        target_type = str(request.data.get("target_type") or "").strip()
        denied = _permission_response(request, target_type)
        if denied:
            return denied
        target_id = request.data.get("target_id")
        patch = request.data.get("patch")
        if not target_id:
            return Response({"target_id": ["请选择编辑对象。"]}, status=400)
        if not isinstance(patch, dict):
            return Response({"patch": ["patch 必须是 JSON 对象。"]}, status=400)
        policy = TARGET_POLICIES[target_type]
        target = policy.model.objects.filter(pk=target_id).first()
        if target is None:
            return Response({"detail": "目标对象不存在。"}, status=404)
        try:
            clean_patch = changed_editorial_patch(
                target_type=target_type,
                target=target,
                patch=patch,
            )
            current_revision = (
                CanonicalObjectRevision.objects.filter(
                    object_type=target_type,
                    object_id=target.pk,
                )
                .values_list("current_revision", flat=True)
                .first()
                or 0
            )
            request_key = str(
                request.headers.get("Idempotency-Key")
                or request.data.get("idempotency_key")
                or ""
            ).strip()
            revision = create_editorial_revision(
                target_type=target_type,
                target_id=target.pk,
                patch=clean_patch,
                actor=request.user,
                idempotency_key=request_key
                or editorial_idempotency_key(
                    target_type=target_type,
                    target_id=target.pk,
                    base_revision=current_revision,
                    patch=clean_patch,
                ),
                change_note=str(request.data.get("change_note") or ""),
            )
        except EditorialRevisionError as error:
            return _error_response(error)
        return Response(serialize_editorial_revision(revision), status=status.HTTP_201_CREATED)


class AdminEditorialRevisionDetailView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    def get(self, request, pk):
        revision = get_object_or_404(
            EditorialRevision.objects.select_related("created_by", "published_by"),
            pk=pk,
        )
        return Response(serialize_editorial_revision(revision))


class AdminEditorialRevisionPublishView(APIView):
    permission_classes = [CanAccessBackOffice]

    def post(self, request, pk):
        revision = get_object_or_404(EditorialRevision, pk=pk)
        denied = _permission_response(request, revision.target_type, publish=True)
        if denied:
            return denied
        try:
            published = publish_editorial_revision(revision.id, actor=request.user)
        except EditorialRevisionError as error:
            return _error_response(error)
        return Response(serialize_editorial_revision(published))
