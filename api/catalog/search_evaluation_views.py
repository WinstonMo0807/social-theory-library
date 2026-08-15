from django.db import transaction
from django.db.models import Count, Max
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsLibraryAdmin

from .models import (
    SearchEvaluationJudgment,
    SearchEvaluationQuery,
    SearchEvaluationRun,
    SearchEvaluationSet,
)
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
