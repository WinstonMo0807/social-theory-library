import hashlib
import json
import uuid

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _stable_document_id(chunk, occurrence):
    locators = chunk.locators or []
    first_locator = locators[0] if locators and isinstance(locators[0], dict) else {}
    bbox_key = json.dumps(
        first_locator.get("bbox") or [],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest_source = "\n".join(
        [
            str(chunk.asset_id),
            chunk.parser_version,
            chunk.chunk_version,
            str(chunk.page_start),
            str(chunk.page_end),
            str(first_locator.get("page_index", chunk.page_start)),
            bbox_key,
            str(occurrence),
        ]
    )
    return hashlib.sha256(digest_source.encode("utf-8")).hexdigest()


def backfill_semantic_document_ids(apps, schema_editor):
    SemanticChunk = apps.get_model("catalog", "SemanticChunk")
    SemanticSearchFeedback = apps.get_model("catalog", "SemanticSearchFeedback")
    database = schema_editor.connection.alias
    occurrences = {}
    pending = []

    chunks = SemanticChunk.objects.using(database).order_by(
        "asset_id",
        "parser_version",
        "chunk_version",
        "page_start",
        "page_end",
        "order",
        "id",
    )
    for chunk in chunks.iterator(chunk_size=1000):
        locators = chunk.locators or []
        first_locator = locators[0] if locators and isinstance(locators[0], dict) else {}
        bbox_key = json.dumps(
            first_locator.get("bbox") or [],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        locator_slot = (
            chunk.asset_id,
            chunk.parser_version,
            chunk.chunk_version,
            chunk.page_start,
            chunk.page_end,
            first_locator.get("page_index", chunk.page_start),
            bbox_key,
        )
        occurrence = occurrences.get(locator_slot, 0)
        occurrences[locator_slot] = occurrence + 1
        chunk.document_id = _stable_document_id(chunk, occurrence)
        pending.append(chunk)
        if len(pending) >= 1000:
            SemanticChunk.objects.using(database).bulk_update(pending, ["document_id"])
            pending.clear()
    if pending:
        SemanticChunk.objects.using(database).bulk_update(pending, ["document_id"])

    feedback_rows = SemanticSearchFeedback.objects.using(database).filter(
        chunk_id__isnull=False,
    ).select_related("chunk")
    pending_feedback = []
    for feedback in feedback_rows.iterator(chunk_size=1000):
        feedback.chunk_document_id = feedback.chunk.document_id
        pending_feedback.append(feedback)
        if len(pending_feedback) >= 1000:
            SemanticSearchFeedback.objects.using(database).bulk_update(
                pending_feedback,
                ["chunk_document_id"],
            )
            pending_feedback.clear()
    if pending_feedback:
        SemanticSearchFeedback.objects.using(database).bulk_update(
            pending_feedback,
            ["chunk_document_id"],
        )


def clear_semantic_document_ids(apps, schema_editor):
    SemanticChunk = apps.get_model("catalog", "SemanticChunk")
    SemanticSearchFeedback = apps.get_model("catalog", "SemanticSearchFeedback")
    database = schema_editor.connection.alias
    SemanticSearchFeedback.objects.using(database).update(chunk_document_id="")
    SemanticChunk.objects.using(database).update(document_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0019_authority_bibliographic_foundation"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="semanticchunk",
            name="document_id",
            field=models.CharField(blank=True, editable=False, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="semanticsearchfeedback",
            name="chunk_document_id",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.RunPython(
            backfill_semantic_document_ids,
            clear_semantic_document_ids,
        ),
        migrations.AlterField(
            model_name="semanticchunk",
            name="document_id",
            field=models.CharField(editable=False, max_length=64, unique=True),
        ),
        migrations.CreateModel(
            name="SearchEvaluationSet",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=240, unique=True)),
                ("description", models.TextField(blank=True)),
                ("language", models.CharField(blank=True, max_length=32)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_search_evaluation_sets",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="SearchEvaluationQuery",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("query_text", models.TextField()),
                ("normalized_query", models.TextField(blank=True)),
                ("filters", models.JSONField(blank=True, default=dict)),
                ("order", models.PositiveIntegerField(default=0)),
                ("notes", models.TextField(blank=True)),
                (
                    "evaluation_set",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="queries",
                        to="catalog.searchevaluationset",
                    ),
                ),
            ],
            options={
                "ordering": ["order", "created_at"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("evaluation_set", "order"),
                        name="unique_search_eval_query_order",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="SearchEvaluationJudgment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("chunk_document_id", models.CharField(db_index=True, max_length=64)),
                (
                    "relevance",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (0, "不相关"),
                            (1, "弱相关"),
                            (2, "相关"),
                            (3, "高度相关"),
                        ],
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(3),
                        ],
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                (
                    "chunk",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="evaluation_judgments",
                        to="catalog.semanticchunk",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_search_evaluation_judgments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "query",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="judgments",
                        to="catalog.searchevaluationquery",
                    ),
                ),
            ],
            options={
                "ordering": ["query__order", "-relevance"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("query", "chunk_document_id"),
                        name="unique_search_eval_judgment",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="SearchEvaluationRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "等待运行"),
                            ("running", "运行中"),
                            ("completed", "已完成"),
                            ("failed", "失败"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("engine", models.CharField(blank=True, max_length=80)),
                (
                    "semantic_ratio",
                    models.FloatField(
                        default=0.72,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(1),
                        ],
                    ),
                ),
                ("config_snapshot", models.JSONField(blank=True, default=dict)),
                ("metrics", models.JSONField(blank=True, default=dict)),
                ("query_count", models.PositiveIntegerField(default=0)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_search_evaluation_runs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "evaluation_set",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="runs",
                        to="catalog.searchevaluationset",
                    ),
                ),
                (
                    "index_version",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="evaluation_runs",
                        to="catalog.semanticindexversion",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["evaluation_set", "status", "created_at"],
                        name="catalog_sea_evaluat_32ef0d_idx",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="SearchEvaluationResult",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("retrieved_document_id", models.CharField(blank=True, db_index=True, max_length=64)),
                (
                    "rank",
                    models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)]),
                ),
                ("keyword_score", models.FloatField(blank=True, null=True)),
                ("semantic_score", models.FloatField(blank=True, null=True)),
                ("final_score", models.FloatField(blank=True, null=True)),
                (
                    "relevance_grade",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(3),
                        ],
                    ),
                ),
                ("latency_ms", models.PositiveIntegerField(default=0)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "query",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="results",
                        to="catalog.searchevaluationquery",
                    ),
                ),
                (
                    "retrieved_chunk",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="evaluation_results",
                        to="catalog.semanticchunk",
                    ),
                ),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="results",
                        to="catalog.searchevaluationrun",
                    ),
                ),
            ],
            options={
                "ordering": ["query__order", "rank"],
                "indexes": [
                    models.Index(
                        fields=["run", "query", "rank"],
                        name="catalog_sea_run_id_1371d4_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("run", "query", "rank"),
                        name="unique_search_eval_result_rank",
                    ),
                ],
            },
        ),
    ]
