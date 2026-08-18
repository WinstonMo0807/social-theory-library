from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor

from catalog.models import (
    Asset,
    DocumentType,
    Edition,
    Page,
    SearchEvaluationJudgment,
    SearchEvaluationQuery,
    SearchEvaluationResult,
    SearchEvaluationRun,
    SearchEvaluationSet,
    SemanticIndexVersion,
    SemanticSearchFeedback,
    Work,
)
from catalog.services.semantic_chunks import build_semantic_chunks
from catalog.services.semantic_search import record_feedback


def _create_asset(marker="stable"):
    work = Work.objects.create(
        document_type=DocumentType.BOOK,
        title=f"稳定分块测试 {marker}",
        language="zh-CN",
    )
    edition = Edition.objects.create(work=work, publication_year=2026)
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=f"public/{marker}.pdf",
        sha256=(marker.encode("utf-8").hex() + "0" * 64)[:64],
        status=Asset.Status.READY,
        page_count=2,
    )
    pages = [
        Page.objects.create(
            asset=asset,
            index=index,
            text=(f"第{index}页的社会理论检索测试正文。" * 24),
            normalized_text=(f"第{index}页的社会理论检索测试正文。" * 24),
            text_source=Page.TextSource.EMBEDDED,
            confidence=1,
        )
        for index in (1, 2)
    ]
    return asset, pages


@pytest.mark.django_db(transaction=True)
def test_migration_backfills_chunk_and_feedback_document_ids():
    executor = MigrationExecutor(transaction.get_connection())
    executor.migrate([("catalog", "0019_authority_bibliographic_foundation")])
    old_apps = executor.loader.project_state(
        [("catalog", "0019_authority_bibliographic_foundation")]
    ).apps
    WorkBefore = old_apps.get_model("catalog", "Work")
    EditionBefore = old_apps.get_model("catalog", "Edition")
    AssetBefore = old_apps.get_model("catalog", "Asset")
    SemanticChunkBefore = old_apps.get_model("catalog", "SemanticChunk")
    FeedbackBefore = old_apps.get_model("catalog", "SemanticSearchFeedback")
    work = WorkBefore.objects.create(
        document_type="book",
        title="迁移回填测试",
        language="zh-CN",
    )
    edition = EditionBefore.objects.create(work=work)
    asset = AssetBefore.objects.create(
        edition=edition,
        kind="normalized",
        file="public/migration.pdf",
        sha256="f" * 64,
    )
    chunk = SemanticChunkBefore.objects.create(
        asset=asset,
        work=work,
        order=0,
        page_start=1,
        page_end=1,
        original_text="迁移前段落",
        normalized_text="迁移前段落",
        language="zh-CN",
        document_type="book",
        parser_version="page-blocks-v2",
        chunk_version="natural-paragraph-v1",
        content_hash="e" * 64,
        locators=[{"page_index": 1, "bbox": [10, 20, 30, 40]}],
    )
    feedback = FeedbackBefore.objects.create(
        chunk=chunk,
        query_hash="d" * 64,
        relevant=True,
    )

    executor = MigrationExecutor(transaction.get_connection())
    executor.migrate([("catalog", "0020_semantic_chunk_stability_and_search_evaluation")])
    new_apps = executor.loader.project_state(
        [("catalog", "0020_semantic_chunk_stability_and_search_evaluation")]
    ).apps
    ChunkAfter = new_apps.get_model("catalog", "SemanticChunk")
    FeedbackAfter = new_apps.get_model("catalog", "SemanticSearchFeedback")
    migrated_chunk = ChunkAfter.objects.get(pk=chunk.pk)
    migrated_feedback = FeedbackAfter.objects.get(pk=feedback.pk)

    assert len(migrated_chunk.document_id) == 64
    assert migrated_feedback.chunk_id == migrated_chunk.id
    assert migrated_feedback.chunk_document_id == migrated_chunk.document_id

    # Migration tests change the shared test database schema. Restore every
    # app to its current leaf so later regression files see the current models
    # instead of the historical 0020 schema.
    executor = MigrationExecutor(transaction.get_connection())
    executor.migrate(executor.loader.graph.leaf_nodes())


@pytest.mark.django_db
def test_force_rebuild_upserts_stable_chunk_ids_and_preserves_feedback():
    asset, pages = _create_asset("force-upsert")
    with patch("catalog.services.semantic_chunks._current_model_name", return_value="test-model"):
        original = build_semantic_chunks(asset)
    original_ids = [chunk.id for chunk in original]
    original_document_ids = [chunk.document_id for chunk in original]
    original_hash = original[0].content_hash
    feedback = record_feedback(
        query="社会理论检索",
        chunk=original[0],
        relevant=True,
        rank=1,
    )

    pages[0].text = "修订后的社会理论检索测试正文。" * 24
    pages[0].normalized_text = pages[0].text
    pages[0].save(update_fields=["text", "normalized_text", "updated_at"])
    with patch("catalog.services.semantic_chunks._current_model_name", return_value="test-model"):
        rebuilt = build_semantic_chunks(asset, force=True)

    assert [chunk.id for chunk in rebuilt] == original_ids
    assert [chunk.document_id for chunk in rebuilt] == original_document_ids
    assert rebuilt[0].content_hash != original_hash
    feedback.refresh_from_db()
    assert feedback.chunk_id == original_ids[0]
    assert feedback.chunk_document_id == original_document_ids[0]


@pytest.mark.django_db
def test_failed_chunk_recovery_is_idempotent_and_clears_only_derived_failure_state():
    asset, pages = _create_asset("failed-recovery")
    with patch("catalog.services.semantic_chunks._current_model_name", return_value="test-model"):
        original = build_semantic_chunks(asset)
    original_ids = [chunk.id for chunk in original]
    original_document_ids = [chunk.document_id for chunk in original]
    original_page_text = [page.text for page in pages]
    asset.semantic_chunks.update(
        index_status="failed",
        index_error="temporary embedding transport failure",
    )

    with patch("catalog.services.semantic_chunks._current_model_name", return_value="test-model"):
        first = build_semantic_chunks(asset, force=True)
        second = build_semantic_chunks(asset, force=True)

    assert [chunk.id for chunk in first] == original_ids
    assert [chunk.id for chunk in second] == original_ids
    assert [chunk.document_id for chunk in second] == original_document_ids
    assert all(chunk.index_status == "pending" for chunk in second)
    assert all(chunk.index_error == "" for chunk in second)
    assert list(asset.pages.order_by("index").values_list("text", flat=True)) == original_page_text


@pytest.mark.django_db
def test_removed_locator_keeps_feedback_document_reference():
    asset, pages = _create_asset("removed-locator")
    with patch("catalog.services.semantic_chunks._current_model_name", return_value="test-model"):
        chunks = build_semantic_chunks(asset)
    feedback = record_feedback(
        query="第二页观点",
        chunk=chunks[1],
        relevant=False,
        rank=2,
    )
    removed_document_id = chunks[1].document_id

    pages[1].delete()
    with patch("catalog.services.semantic_chunks._current_model_name", return_value="test-model"):
        rebuilt = build_semantic_chunks(asset, force=True)

    assert len(rebuilt) == 1
    feedback.refresh_from_db()
    assert feedback.chunk_id is None
    assert feedback.chunk_document_id == removed_document_id


@pytest.mark.django_db
def test_force_rebuild_replaces_changed_locator_without_order_collision():
    asset, pages = _create_asset("changed-locator")
    with patch("catalog.services.semantic_chunks._current_model_name", return_value="test-model"):
        original = build_semantic_chunks(asset)
    retained_id = original[0].id

    pages[1].delete()
    Page.objects.create(
        asset=asset,
        index=3,
        text="第三页替换了原来的第二页。" * 24,
        normalized_text="第三页替换了原来的第二页。" * 24,
        text_source=Page.TextSource.EMBEDDED,
        confidence=1,
    )
    with patch("catalog.services.semantic_chunks._current_model_name", return_value="test-model"):
        rebuilt = build_semantic_chunks(asset, force=True)

    assert [chunk.order for chunk in rebuilt] == [0, 1]
    assert rebuilt[0].id == retained_id
    assert rebuilt[1].page_start == 3


@pytest.mark.django_db
def test_search_evaluation_models_reuse_index_version_and_stable_document_ids(admin_user):
    asset, _pages = _create_asset("evaluation")
    with patch("catalog.services.semantic_chunks._current_model_name", return_value="test-model"):
        chunk = build_semantic_chunks(asset)[0]
    evaluation_set = SearchEvaluationSet.objects.create(
        name="社会理论中英文基线",
        language="zh-CN",
        created_by=admin_user,
    )
    query = SearchEvaluationQuery.objects.create(
        evaluation_set=evaluation_set,
        query_text="权力如何参与主体形成",
        normalized_query="权力如何参与主体形成",
        filters={"document_types": ["book"]},
        order=1,
    )
    judgment = SearchEvaluationJudgment.objects.create(
        query=query,
        chunk=chunk,
        relevance=SearchEvaluationJudgment.Relevance.HIGHLY_RELEVANT,
        created_by=admin_user,
    )
    index_version = SemanticIndexVersion.objects.create(
        uid="semantic_eval_candidate_v1",
        provider="local",
        status=SemanticIndexVersion.Status.READY,
    )
    run = SearchEvaluationRun.objects.create(
        evaluation_set=evaluation_set,
        index_version=index_version,
        status=SearchEvaluationRun.Status.COMPLETED,
        engine="meilisearch_hybrid",
        semantic_ratio=0.72,
        config_snapshot={"index_uid": index_version.uid},
        metrics={"recall_at_20": 1.0, "ndcg_at_10": 1.0, "mrr": 1.0},
        query_count=1,
        created_by=admin_user,
    )
    result = SearchEvaluationResult.objects.create(
        run=run,
        query=query,
        retrieved_chunk=chunk,
        rank=1,
        final_score=0.91,
        relevance_grade=judgment.relevance,
        latency_ms=18,
    )

    assert run.index_version_id == index_version.id
    assert result.retrieved_document_id == judgment.chunk_document_id
    assert evaluation_set.queries.count() == 1
    assert run.results.count() == 1

    chunk.delete()
    judgment.refresh_from_db()
    result.refresh_from_db()
    assert judgment.chunk_id is None
    assert result.retrieved_chunk_id is None
    assert judgment.chunk_document_id == result.retrieved_document_id


@pytest.mark.django_db
def test_search_evaluation_constraints_and_ratio_validation():
    evaluation_set = SearchEvaluationSet.objects.create(name="约束测试")
    query = SearchEvaluationQuery.objects.create(
        evaluation_set=evaluation_set,
        query_text="国家自主性",
        order=1,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        SearchEvaluationQuery.objects.create(
            evaluation_set=evaluation_set,
            query_text="重复顺序",
            order=1,
        )

    run = SearchEvaluationRun(
        evaluation_set=evaluation_set,
        semantic_ratio=1.2,
    )
    with pytest.raises(ValidationError):
        run.full_clean()

    judgment = SearchEvaluationJudgment(
        query=query,
        chunk_document_id="a" * 64,
        relevance=4,
    )
    with pytest.raises(ValidationError):
        judgment.full_clean()

    assert SemanticSearchFeedback.objects.count() == 0
