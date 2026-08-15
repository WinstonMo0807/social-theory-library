from __future__ import annotations

from django.db import transaction
from rest_framework import serializers

from catalog.models import (
    SearchEvaluationJudgment,
    SearchEvaluationQuery,
    SearchEvaluationResult,
    SearchEvaluationRun,
    SearchEvaluationSet,
    SemanticChunk,
    SemanticIndexVersion,
)
from catalog.services.text import normalize_search_text


class SearchEvaluationJudgmentInputSerializer(serializers.Serializer):
    chunk_id = serializers.UUIDField(required=False)
    chunk_document_id = serializers.CharField(required=False, max_length=64)
    relevance = serializers.ChoiceField(choices=SearchEvaluationJudgment.Relevance.choices)
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        chunk = None
        chunk_id = attrs.get("chunk_id")
        document_id = str(attrs.get("chunk_document_id") or "").strip()
        if chunk_id:
            chunk = SemanticChunk.objects.filter(pk=chunk_id).first()
            if chunk is None:
                raise serializers.ValidationError({"chunk_id": ["语义段落不存在。"]})
            if document_id and document_id != chunk.document_id:
                raise serializers.ValidationError(
                    {"chunk_document_id": ["稳定段落标识与所选语义段落不一致。"]}
                )
            document_id = chunk.document_id
        elif document_id:
            chunk = SemanticChunk.objects.filter(document_id=document_id).first()
        else:
            raise serializers.ValidationError(
                {"chunk_document_id": ["请提供语义段落或稳定段落标识。"]}
            )
        attrs["chunk"] = chunk
        attrs["chunk_document_id"] = document_id
        attrs.pop("chunk_id", None)
        return attrs


class SearchEvaluationQueryInputSerializer(serializers.Serializer):
    query_text = serializers.CharField(max_length=1200)
    normalized_query = serializers.CharField(required=False, allow_blank=True, max_length=1200)
    filters = serializers.JSONField(required=False, default=dict)
    order = serializers.IntegerField(required=False, min_value=0)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    judgments = SearchEvaluationJudgmentInputSerializer(many=True)

    def validate_filters(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("查询过滤条件必须是对象。")
        return value

    def validate_judgments(self, value):
        document_ids = [row["chunk_document_id"] for row in value]
        if len(document_ids) != len(set(document_ids)):
            raise serializers.ValidationError("同一查询不能重复标注同一稳定段落。")
        return value


class SearchEvaluationSetCreateSerializer(serializers.ModelSerializer):
    queries = SearchEvaluationQueryInputSerializer(many=True)

    class Meta:
        model = SearchEvaluationSet
        fields = ["id", "name", "description", "language", "is_active", "metadata", "queries"]
        read_only_fields = ["id"]

    def validate_queries(self, value):
        resolved_orders = [row.get("order", position) for position, row in enumerate(value)]
        if len(resolved_orders) != len(set(resolved_orders)):
            raise serializers.ValidationError("评估查询的顺序不能重复。")
        return value

    @transaction.atomic
    def create(self, validated_data):
        query_rows = validated_data.pop("queries")
        actor = self.context["request"].user
        evaluation_set = SearchEvaluationSet.objects.create(
            created_by=actor,
            **validated_data,
        )
        for position, query_data in enumerate(query_rows):
            judgment_rows = query_data.pop("judgments")
            query = SearchEvaluationQuery.objects.create(
                evaluation_set=evaluation_set,
                normalized_query=(
                    query_data.pop("normalized_query", "")
                    or normalize_search_text(query_data["query_text"])
                ),
                order=query_data.pop("order", position),
                **query_data,
            )
            SearchEvaluationJudgment.objects.bulk_create(
                [
                    SearchEvaluationJudgment(
                        query=query,
                        created_by=actor,
                        **judgment_data,
                    )
                    for judgment_data in judgment_rows
                ]
            )
        return evaluation_set


class SearchEvaluationJudgmentSerializer(serializers.ModelSerializer):
    chunk_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = SearchEvaluationJudgment
        fields = ["id", "chunk_id", "chunk_document_id", "relevance", "notes"]


class SearchEvaluationQuerySerializer(serializers.ModelSerializer):
    judgments = SearchEvaluationJudgmentSerializer(many=True, read_only=True)

    class Meta:
        model = SearchEvaluationQuery
        fields = [
            "id",
            "query_text",
            "normalized_query",
            "filters",
            "order",
            "notes",
            "judgments",
        ]


class SearchEvaluationSetSerializer(serializers.ModelSerializer):
    queries = SearchEvaluationQuerySerializer(many=True, read_only=True)
    query_count = serializers.IntegerField(read_only=True)
    judgment_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = SearchEvaluationSet
        fields = [
            "id",
            "name",
            "description",
            "language",
            "is_active",
            "metadata",
            "query_count",
            "judgment_count",
            "queries",
            "created_at",
            "updated_at",
        ]


class SearchEvaluationSetSummarySerializer(serializers.ModelSerializer):
    query_count = serializers.IntegerField(read_only=True)
    judgment_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = SearchEvaluationSet
        fields = [
            "id",
            "name",
            "description",
            "language",
            "is_active",
            "metadata",
            "query_count",
            "judgment_count",
            "created_at",
            "updated_at",
        ]


class SearchEvaluationRunRequestSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=["dry_run", "enqueue", "execute"], default="dry_run")
    evaluation_set = serializers.PrimaryKeyRelatedField(
        queryset=SearchEvaluationSet.objects.all()
    )
    index_version = serializers.PrimaryKeyRelatedField(
        queryset=SemanticIndexVersion.objects.all()
    )
    semantic_ratio = serializers.FloatField(min_value=0, max_value=1, default=0.72)


class SearchEvaluationResultSerializer(serializers.ModelSerializer):
    query_id = serializers.UUIDField(read_only=True)
    retrieved_chunk_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = SearchEvaluationResult
        fields = [
            "id",
            "query_id",
            "retrieved_chunk_id",
            "retrieved_document_id",
            "rank",
            "keyword_score",
            "semantic_score",
            "final_score",
            "relevance_grade",
            "latency_ms",
            "metadata",
        ]


class SearchEvaluationRunSerializer(serializers.ModelSerializer):
    evaluation_set_name = serializers.CharField(source="evaluation_set.name", read_only=True)
    index_uid = serializers.CharField(source="index_version.uid", read_only=True, default="")
    results = SearchEvaluationResultSerializer(many=True, read_only=True)

    class Meta:
        model = SearchEvaluationRun
        fields = [
            "id",
            "evaluation_set",
            "evaluation_set_name",
            "index_version",
            "index_uid",
            "status",
            "engine",
            "semantic_ratio",
            "config_snapshot",
            "metrics",
            "query_count",
            "completed_query_count",
            "task_id",
            "started_at",
            "finished_at",
            "error_message",
            "results",
            "created_at",
        ]


class SearchEvaluationRunSummarySerializer(serializers.ModelSerializer):
    evaluation_set_name = serializers.CharField(source="evaluation_set.name", read_only=True)
    index_uid = serializers.CharField(source="index_version.uid", read_only=True, default="")

    class Meta:
        model = SearchEvaluationRun
        fields = [
            "id",
            "evaluation_set",
            "evaluation_set_name",
            "index_version",
            "index_uid",
            "status",
            "engine",
            "semantic_ratio",
            "metrics",
            "query_count",
            "completed_query_count",
            "task_id",
            "started_at",
            "finished_at",
            "error_message",
            "created_at",
        ]
