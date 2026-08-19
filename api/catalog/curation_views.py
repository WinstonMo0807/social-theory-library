from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import CanAccessBackOffice, CanPublishWork, IsKnowledgeEditor

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


class WorkReadingPathPlacementListView(APIView):
    permission_classes = [IsKnowledgeEditor]

    def post(self, request, work_id):
        serializer = ReadingPathPlacementCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
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
