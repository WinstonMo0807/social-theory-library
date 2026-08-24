from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import (
    CanAccessBackOffice,
    CanPublishWork,
    CanReviewCandidate,
    IsKnowledgeEditor,
)

from catalog.models import (
    CanonicalObjectRevision,
    DerivedClaim,
    EditorialRevision,
    ReadingPath,
    ReadingPathItem,
    Work,
)

from catalog.curation_serializers import (
    CurationWorkSerializer,
    ExpectedPathVersionSerializer,
    ReadingPathPlacementCreateSerializer,
    ReadingPathPlacementUpdateSerializer,
    WorkReadingPathPlacementSerializer,
    WorkRecommendationCurrentItemSerializer,
    WorkRecommendationOverrideInputSerializer,
    WorkRecommendationOverrideSerializer,
    WorkRecommendationPolicySerializer,
)
from catalog.services.work_curation import (
    CurationConflict,
    CurationNotFound,
    CurationValidationError,
    build_work_curation_summary,
    create_work_reading_path_placement,
    deactivate_work_recommendation_override,
    delete_work_reading_path_placement,
    update_work_reading_path_placement,
    upsert_work_recommendation_override,
)
from catalog.services.claims.curation import (
    decide_claim_curation_candidate,
    high_value_claim_candidates,
)
from catalog.services.evidence_envelope import evidence_span_envelope
from catalog.services.editorial_revision import (
    EditorialRevisionError,
    create_editorial_revision,
    editorial_idempotency_key,
    serialize_editorial_revision,
)
from catalog.services.reading_paths import (
    ReadingPathStructureError,
    stage_groups_with_created_work,
    stage_groups_with_updated_item,
    stage_groups_without_item,
)


def _curation_error_response(error: RuntimeError) -> Response:
    if isinstance(error, CurationNotFound):
        response_status = status.HTTP_404_NOT_FOUND
    elif isinstance(error, CurationConflict):
        response_status = status.HTTP_409_CONFLICT
    else:
        response_status = status.HTTP_400_BAD_REQUEST
    return Response(
        {"detail": str(error), "code": getattr(error, "code", "curation_error")},
        status=response_status,
    )


def _published_path_revision(
    request,
    *,
    path: ReadingPath,
    stage_groups,
    change_note: str,
):
    current_revision = (
        CanonicalObjectRevision.objects.filter(
            object_type=EditorialRevision.TargetType.READING_PATH,
            object_id=path.id,
        )
        .values_list("current_revision", flat=True)
        .first()
        or 0
    )
    patch = {"stage_groups": stage_groups}
    return create_editorial_revision(
        target_type=EditorialRevision.TargetType.READING_PATH,
        target_id=path.id,
        patch=patch,
        actor=request.user,
        idempotency_key=str(request.headers.get("Idempotency-Key") or "").strip()
        or editorial_idempotency_key(
            target_type=EditorialRevision.TargetType.READING_PATH,
            target_id=path.id,
            base_revision=current_revision,
            patch=patch,
        ),
        change_note=change_note,
    )


def _path_version_conflict(path: ReadingPath, expected) -> Response | None:
    if expected is None or path.updated_at == expected:
        return None
    return _curation_error_response(CurationConflict("阅读路径已被其他编辑更新，请刷新后重试。"))


class WorkCurationSummaryView(APIView):
    permission_classes = [CanAccessBackOffice]

    def get(self, request, work_id):
        try:
            summary = build_work_curation_summary(work_id)
        except CurationNotFound as error:
            return _curation_error_response(error)
        return Response(
            {
                "work": CurationWorkSerializer(summary.work).data,
                "reading_path_placements": WorkReadingPathPlacementSerializer(
                    summary.placements,
                    many=True,
                ).data,
                "recommendations": {
                    "current": WorkRecommendationCurrentItemSerializer(
                        summary.current_recommendations,
                        many=True,
                    ).data,
                    "overrides": WorkRecommendationOverrideSerializer(
                        summary.overrides,
                        many=True,
                    ).data,
                    "policies": WorkRecommendationPolicySerializer(
                        summary.policies,
                        many=True,
                    ).data,
                },
            }
        )


class WorkClaimCandidateDecisionView(APIView):
    """Record one bounded human Claim decision without publishing it."""

    permission_classes = [CanReviewCandidate]

    def post(self, request, work_id, claim_id):
        work = Work.objects.filter(pk=work_id).first()
        claim = DerivedClaim.objects.filter(pk=claim_id).first()
        if work is None or claim is None:
            return Response({"detail": "Claim 策展候选不存在。"}, status=404)
        action = str(request.data.get("action") or "").strip().casefold()
        if action not in {"accept", "accept_with_edit", "reject", "defer"}:
            return Response(
                {"action": ["请选择 accept、accept_with_edit、reject 或 defer。"]},
                status=400,
            )
        try:
            curated = decide_claim_curation_candidate(
                work=work,
                claim=claim,
                decision=action,
                actor=request.user,
                proposition=str(request.data.get("proposition") or ""),
                editorial_note=str(request.data.get("editorial_note") or ""),
                kind=str(request.data.get("kind") or ""),
            )
        except PermissionError as error:
            return Response({"detail": str(error)}, status=403)
        except (DerivedClaim.DoesNotExist, ValueError) as error:
            return Response({"detail": str(error)}, status=400)

        curated_payload = None
        if curated is not None:
            curated_payload = {
                "id": str(curated.id),
                "kind": curated.kind,
                "proposition": curated.proposition,
                "editorial_note": curated.editorial_note,
                "status": curated.status,
                "adopted_from": str(curated.adopted_from_id),
                "evidence": [
                    evidence_span_envelope(link.evidence_span).as_dict()
                    for link in curated.evidence_links.select_related(
                        "evidence_span__page",
                        "evidence_span__document_revision__asset__edition__work",
                    ).order_by("sort_order", "created_at")
                ],
            }
        return Response(
            {
                "decision": action,
                "curated_claim": curated_payload,
                "remaining_candidates": high_value_claim_candidates(
                    work,
                    reviewer=request.user,
                    limit=5,
                ),
            }
        )


class WorkReadingPathPlacementListView(APIView):
    permission_classes = [IsKnowledgeEditor]

    def post(self, request, work_id):
        serializer = ReadingPathPlacementCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        path = ReadingPath.objects.filter(pk=payload["reading_path_id"]).first()
        if path is not None and path.status == "published":
            conflict = _path_version_conflict(
                path,
                payload.get("expected_path_updated_at"),
            )
            if conflict is not None:
                return conflict
            if not Work.objects.filter(pk=work_id).exists():
                return _curation_error_response(CurationNotFound("作品不存在或已被删除。"))
            try:
                groups = stage_groups_with_created_work(
                    path,
                    stage_id=payload["stage_id"],
                    work_id=work_id,
                    recommendation_reason=payload.get("recommendation_reason", ""),
                    is_required=payload.get("is_required", False),
                    editorial_note=payload.get("editorial_note", ""),
                )
                revision = _published_path_revision(
                    request,
                    path=path,
                    stage_groups=groups,
                    change_note="已发布阅读路径新增作品草稿",
                )
            except (ReadingPathStructureError, EditorialRevisionError) as error:
                return _curation_error_response(CurationValidationError(str(error)))
            return Response(
                {
                    "reading_path_id": str(path.id),
                    "editorial_revision": serialize_editorial_revision(revision),
                },
                status=status.HTTP_202_ACCEPTED,
            )
        try:
            item = create_work_reading_path_placement(
                work_id=work_id,
                reading_path_id=payload["reading_path_id"],
                stage_id=payload["stage_id"],
                actor=request.user,
                recommendation_reason=payload.get("recommendation_reason", ""),
                is_required=payload.get("is_required", False),
                editorial_note=payload.get("editorial_note", ""),
                expected_path_updated_at=payload.get("expected_path_updated_at"),
            )
        except (CurationConflict, CurationNotFound, CurationValidationError) as error:
            return _curation_error_response(error)
        return Response(
            WorkReadingPathPlacementSerializer(item).data,
            status=status.HTTP_201_CREATED,
        )


class WorkReadingPathPlacementDetailView(APIView):
    permission_classes = [IsKnowledgeEditor]

    def patch(self, request, work_id, item_id):
        serializer = ReadingPathPlacementUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        payload = dict(serializer.validated_data)
        expected_path_updated_at = payload.pop("expected_path_updated_at", None)
        existing = (
            ReadingPathItem.objects.select_related("reading_path")
            .filter(pk=item_id, work_id=work_id)
            .first()
        )
        if existing is not None and existing.reading_path.status == "published":
            path = existing.reading_path
            conflict = _path_version_conflict(path, expected_path_updated_at)
            if conflict is not None:
                return conflict
            try:
                groups = stage_groups_with_updated_item(
                    path,
                    item_id=item_id,
                    changes=payload,
                )
                revision = _published_path_revision(
                    request,
                    path=path,
                    stage_groups=groups,
                    change_note="已发布阅读路径调整作品草稿",
                )
            except (ReadingPathStructureError, EditorialRevisionError) as error:
                return _curation_error_response(CurationValidationError(str(error)))
            return Response(
                {
                    "reading_path_id": str(path.id),
                    "editorial_revision": serialize_editorial_revision(revision),
                },
                status=status.HTTP_202_ACCEPTED,
            )
        try:
            item = update_work_reading_path_placement(
                work_id=work_id,
                item_id=item_id,
                actor=request.user,
                changes=payload,
                expected_path_updated_at=expected_path_updated_at,
            )
        except (CurationConflict, CurationNotFound, CurationValidationError) as error:
            return _curation_error_response(error)
        return Response(WorkReadingPathPlacementSerializer(item).data)

    def delete(self, request, work_id, item_id):
        serializer = ExpectedPathVersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        existing = (
            ReadingPathItem.objects.select_related("reading_path")
            .filter(pk=item_id, work_id=work_id)
            .first()
        )
        if existing is not None and existing.reading_path.status == "published":
            path = existing.reading_path
            conflict = _path_version_conflict(
                path,
                serializer.validated_data.get("expected_path_updated_at"),
            )
            if conflict is not None:
                return conflict
            try:
                groups = stage_groups_without_item(path, item_id=item_id)
                revision = _published_path_revision(
                    request,
                    path=path,
                    stage_groups=groups,
                    change_note="已发布阅读路径移除作品草稿",
                )
            except (ReadingPathStructureError, EditorialRevisionError) as error:
                return _curation_error_response(CurationValidationError(str(error)))
            return Response(
                {
                    "reading_path_id": str(path.id),
                    "editorial_revision": serialize_editorial_revision(revision),
                },
                status=status.HTTP_202_ACCEPTED,
            )
        try:
            result = delete_work_reading_path_placement(
                work_id=work_id,
                item_id=item_id,
                actor=request.user,
                expected_path_updated_at=serializer.validated_data.get(
                    "expected_path_updated_at"
                ),
            )
        except (CurationConflict, CurationNotFound, CurationValidationError) as error:
            return _curation_error_response(error)
        return Response(result)


class WorkRecommendationOverrideView(APIView):
    permission_classes = [CanPublishWork]

    def put(self, request, work_id, placement):
        serializer = WorkRecommendationOverrideInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        try:
            override = upsert_work_recommendation_override(
                work_id=work_id,
                placement=placement,
                actor=request.user,
                action=payload["action"],
                position=payload.get("position"),
                note=payload.get("note", ""),
            )
        except (CurationConflict, CurationNotFound, CurationValidationError) as error:
            return _curation_error_response(error)
        return Response(WorkRecommendationOverrideSerializer(override).data)

    def delete(self, request, work_id, placement):
        try:
            result = deactivate_work_recommendation_override(
                work_id=work_id,
                placement=placement,
                actor=request.user,
            )
        except (CurationConflict, CurationNotFound, CurationValidationError) as error:
            return _curation_error_response(error)
        return Response(result)
