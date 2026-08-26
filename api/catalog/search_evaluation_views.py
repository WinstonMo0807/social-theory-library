from django.db import transaction
from django.db.models import Count, Max
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsLibraryAdmin

from .models import (
    ClaimBenchmarkJudgment,
    DocumentRevision,
    EvidenceSpan,
    SearchEvaluationJudgment,
    SearchEvaluationQuery,
    SearchEvaluationRun,
    SearchEvaluationSet,
)
from .services.claim_benchmark import claim_benchmark_gold_summary
from .search_evaluation_serializers import (
    SearchEvaluationRunRequestSerializer,
    SearchEvaluationRunSerializer,
    SearchEvaluationRunSummarySerializer,
    SearchEvaluationQueryInputSerializer,
    SearchEvaluationQuerySerializer,
    SearchEvaluationSetCreateSerializer,
    SearchEvaluationSetSerializer,
    SearchEvaluationSetSummarySerializer,
)
from .services.search_evaluation import (
    SearchEvaluationExecutionError,
    SearchEvaluationValidationError,
    build_evaluation_plan,
    execute_evaluation,
    prepare_evaluation_run,
)


def evaluation_sets():
    return SearchEvaluationSet.objects.annotate(
        query_count=Count("queries", distinct=True),
        judgment_count=Count("queries__judgments", distinct=True),
    ).order_by("name")


class ClaimBenchmarkJudgmentWriteSerializer(serializers.Serializer):
    query_id = serializers.UUIDField()
    evidence_span_id = serializers.UUIDField()
    expected_relation = serializers.ChoiceField(
        choices=ClaimBenchmarkJudgment.Relation.choices,
    )
    expected_attribution = serializers.ChoiceField(
        choices=ClaimBenchmarkJudgment.Attribution.choices,
        default=ClaimBenchmarkJudgment.Attribution.UNCERTAIN,
    )
    relevance = serializers.IntegerField(min_value=0, max_value=3, default=2)
    locator_verified = serializers.BooleanField(default=False)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=5000)

    def validate(self, attrs):
        query = get_object_or_404(SearchEvaluationQuery, pk=attrs.pop("query_id"))
        evidence_span = get_object_or_404(
            EvidenceSpan.objects.select_related(
                "document_revision",
                "document_revision__asset__edition__work",
                "page",
            ),
            pk=attrs.pop("evidence_span_id"),
        )
        _validate_current_gold_evidence(evidence_span)
        attrs["query"] = query
        attrs["evidence_span"] = evidence_span
        return attrs


class ClaimBenchmarkJudgmentFilterSerializer(serializers.Serializer):
    evaluation_set = serializers.UUIDField(required=False, allow_null=True)
    query = serializers.UUIDField(required=False, allow_null=True)


def _validate_current_gold_evidence(evidence_span: EvidenceSpan) -> None:
    if evidence_span.is_stale:
        raise serializers.ValidationError(
            {"evidence_span_id": "已失效的 EvidenceSpan 不能作为人工 Gold judgment。"}
        )
    if not evidence_span.document_revision.is_active:
        raise serializers.ValidationError(
            {"evidence_span_id": "已 superseded 的 DocumentRevision 不能作为人工 Gold judgment。"}
        )


def _claim_judgment_payload(row: ClaimBenchmarkJudgment) -> dict:
    span = row.evidence_span
    text = span.original_text or ""
    return {
        "id": str(row.id),
        "query": {
            "id": str(row.query_id),
            "evaluation_set_id": str(row.query.evaluation_set_id),
            "text": row.query.query_text,
        },
        "evidence": {
            "id": str(span.id),
            "text": text[:1200],
            "text_truncated": len(text) > 1200,
            "locator": {
                "page": span.page_number,
                "printed_page_label": span.printed_page_label,
            },
            "quality": span.quality,
            "document_revision_id": str(row.document_revision_id),
            "work": {
                "id": str(row.work_id),
                "title": row.work.title,
            },
        },
        "expected_relation": row.expected_relation,
        "expected_attribution": row.expected_attribution,
        "relevance": row.relevance,
        "locator_verified": row.locator_verified,
        "notes": row.notes,
        "created_by": str(row.created_by_id or ""),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _claim_judgments():
    return ClaimBenchmarkJudgment.objects.select_related(
        "query",
        "query__evaluation_set",
        "evidence_span",
        "work",
        "document_revision",
    )


class ClaimBenchmarkJudgmentListCreateView(APIView):
    permission_classes = [IsLibraryAdmin]

    def get(self, request):
        rows = _claim_judgments()
        query_params = ClaimBenchmarkJudgmentFilterSerializer(
            data={
                "evaluation_set": request.query_params.get("evaluation_set") or None,
                "query": request.query_params.get("query") or None,
            }
        )
        query_params.is_valid(raise_exception=True)
        evaluation_set_id = query_params.validated_data.get("evaluation_set")
        query_id = query_params.validated_data.get("query")
        if evaluation_set_id:
            rows = rows.filter(query__evaluation_set_id=evaluation_set_id)
        if query_id:
            rows = rows.filter(query_id=query_id)
        total_count = rows.count()
        rows = list(rows[:200])
        return Response(
            {
                "summary": claim_benchmark_gold_summary(
                    evaluation_set_id=evaluation_set_id or None,
                ),
                "count": total_count,
                "returned_count": len(rows),
                "truncated": total_count > len(rows),
                "results": [_claim_judgment_payload(row) for row in rows],
            }
        )

    def post(self, request):
        serializer = ClaimBenchmarkJudgmentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        query = values.pop("query")
        evidence_span = values.pop("evidence_span")
        with transaction.atomic():
            document_revision = (
                DocumentRevision.objects.select_for_update()
                .select_related("asset__edition__work")
                .get(pk=evidence_span.document_revision_id)
            )
            evidence_span = EvidenceSpan.objects.select_for_update().get(pk=evidence_span.pk)
            evidence_span.document_revision = document_revision
            _validate_current_gold_evidence(evidence_span)
            row, created = ClaimBenchmarkJudgment.objects.get_or_create(
                query=query,
                evidence_span=evidence_span,
                defaults={**values, "created_by": request.user},
            )
            if not created:
                for field, value in values.items():
                    setattr(row, field, value)
                row.save(update_fields=[*values.keys(), "updated_at"])
        row = get_object_or_404(_claim_judgments(), pk=row.pk)
        return Response(
            {
                "created": created,
                "judgment": _claim_judgment_payload(row),
                "summary": claim_benchmark_gold_summary(
                    evaluation_set_id=row.query.evaluation_set_id,
                ),
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ClaimBenchmarkJudgmentDetailView(APIView):
    permission_classes = [IsLibraryAdmin]

    def delete(self, request, pk):
        row = get_object_or_404(ClaimBenchmarkJudgment, pk=pk)
        row.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SearchEvaluationSetListCreateView(APIView):
    permission_classes = [IsLibraryAdmin]

    def get(self, request):
        return Response(SearchEvaluationSetSummarySerializer(evaluation_sets(), many=True).data)

    def post(self, request):
        serializer = SearchEvaluationSetCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        evaluation_set = serializer.save()
        evaluation_set = get_object_or_404(evaluation_sets(), pk=evaluation_set.pk)
        return Response(SearchEvaluationSetSerializer(evaluation_set).data, status=201)


class SearchEvaluationSetDetailView(APIView):
    permission_classes = [IsLibraryAdmin]

    def get(self, request, pk):
        evaluation_set = get_object_or_404(
            evaluation_sets().prefetch_related("queries__judgments"),
            pk=pk,
        )
        return Response(SearchEvaluationSetSerializer(evaluation_set).data)

    def patch(self, request, pk):
        evaluation_set = get_object_or_404(SearchEvaluationSet, pk=pk)
        allowed = {key: request.data[key] for key in ("name", "description", "language", "is_active") if key in request.data}
        serializer = SearchEvaluationSetCreateSerializer(
            evaluation_set,
            data={**allowed, "queries": []},
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        validated = {
            field: value
            for field, value in serializer.validated_data.items()
            if field != "queries"
        }
        for field, value in validated.items():
            setattr(evaluation_set, field, value)
        evaluation_set.save(update_fields=[*validated.keys(), "updated_at"])
        refreshed = get_object_or_404(
            evaluation_sets().prefetch_related("queries__judgments"),
            pk=evaluation_set.pk,
        )
        return Response(SearchEvaluationSetSerializer(refreshed).data)


class SearchEvaluationQueryListCreateView(APIView):
    permission_classes = [IsLibraryAdmin]

    def post(self, request, set_id):
        evaluation_set = get_object_or_404(SearchEvaluationSet, pk=set_id)
        serializer = SearchEvaluationQueryInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        judgments = values.pop("judgments")
        next_order = (
            evaluation_set.queries.aggregate(maximum=Max("order"))["maximum"]
        )
        if "order" not in values:
            values["order"] = 0 if next_order is None else next_order + 1
        normalized_query = values.pop("normalized_query", "")
        from catalog.services.text import normalize_search_text

        with transaction.atomic():
            query = SearchEvaluationQuery.objects.create(
                evaluation_set=evaluation_set,
                normalized_query=normalized_query or normalize_search_text(values["query_text"]),
                **values,
            )
            SearchEvaluationJudgment.objects.bulk_create(
                [
                    SearchEvaluationJudgment(
                        query=query,
                        created_by=request.user,
                        **judgment,
                    )
                    for judgment in judgments
                ]
            )
        return Response(SearchEvaluationQuerySerializer(query).data, status=201)


class SearchEvaluationRunListCreateView(APIView):
    permission_classes = [IsLibraryAdmin]

    def get(self, request):
        rows = SearchEvaluationRun.objects.select_related(
            "evaluation_set",
            "index_version",
        )
        evaluation_set_id = str(request.query_params.get("evaluation_set") or "").strip()
        if evaluation_set_id:
            rows = rows.filter(evaluation_set_id=evaluation_set_id)
        return Response(SearchEvaluationRunSummarySerializer(rows[:200], many=True).data)

    def post(self, request):
        serializer = SearchEvaluationRunRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        if values["mode"] == "dry_run":
            plan = build_evaluation_plan(
                values["evaluation_set"],
                values["index_version"],
                semantic_ratio=values["semantic_ratio"],
                verify_index=True,
            )
            return Response(plan, status=200 if plan["can_execute"] else 409)
        if values["mode"] == "enqueue":
            try:
                run = prepare_evaluation_run(
                    values["evaluation_set"],
                    values["index_version"],
                    semantic_ratio=values["semantic_ratio"],
                    actor=request.user,
                )
            except SearchEvaluationValidationError as exc:
                return Response(exc.plan, status=409)
            from catalog.tasks import run_search_evaluation

            result = run_search_evaluation.apply_async(args=[str(run.id)])
            run.task_id = str(result.id or "")
            run.save(update_fields=["task_id", "updated_at"])
            run.refresh_from_db()
            return Response(SearchEvaluationRunSerializer(run).data, status=202)
        try:
            run = execute_evaluation(
                values["evaluation_set"],
                values["index_version"],
                semantic_ratio=values["semantic_ratio"],
                actor=request.user,
            )
        except SearchEvaluationValidationError as exc:
            return Response(exc.plan, status=409)
        except SearchEvaluationExecutionError as exc:
            return Response(
                {
                    "detail": str(exc),
                    "run": SearchEvaluationRunSerializer(exc.run).data,
                },
                status=502,
            )
        return Response(SearchEvaluationRunSerializer(run).data, status=201)


class SearchEvaluationRunDetailView(APIView):
    permission_classes = [IsLibraryAdmin]

    def get(self, request, pk):
        run = get_object_or_404(
            SearchEvaluationRun.objects.select_related(
                "evaluation_set",
                "index_version",
            ).prefetch_related("results"),
            pk=pk,
        )
        return Response(SearchEvaluationRunSerializer(run).data)
