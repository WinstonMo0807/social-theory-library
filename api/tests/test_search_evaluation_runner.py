from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from io import StringIO
import json
from types import SimpleNamespace
from uuid import uuid4
import pytest

from catalog.models import (
    Asset,
    DocumentType,
    Edition,
    SearchEvaluationJudgment,
    SearchEvaluationQuery,
    SearchEvaluationResult,
    SearchEvaluationRun,
    SearchEvaluationSet,
    SemanticChunk,
    SemanticIndexVersion,
    Work,
)
from catalog.services.search_evaluation import (
    build_evaluation_plan,
    execute_evaluation,
    prepare_evaluation_run,
    score_query,
)


pytestmark = pytest.mark.django_db


def make_search_fixture(admin_user):
    work = Work.objects.create(document_type=DocumentType.BOOK, title="检索评估样本")
    edition = Edition.objects.create(work=work)
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=SimpleUploadedFile("evaluation.pdf", b"%PDF-1.4\n%%EOF"),
        sha256="f" * 64,
        status=Asset.Status.READY,
    )
    chunks = []
    for order, document_id in enumerate(("a" * 64, "b" * 64)):
        chunks.append(
            SemanticChunk.objects.create(
                asset=asset,
                work=work,
                order=order,
                page_start=order + 1,
                page_end=order + 1,
                paragraph_index=order,
                original_text=f"评估段落 {order}",
                normalized_text=f"评估段落 {order}",
                document_type=DocumentType.BOOK,
                parser_version="test-parser",
                chunk_version="test-chunk",
                embedding_model="test-model",
                embedding_version="test-revision",
                document_id=document_id,
                content_hash=str(order + 1) * 64,
                index_status=SemanticChunk.IndexStatus.READY,
            )
        )
    version = SemanticIndexVersion.objects.create(
        uid="semantic_evaluation_candidate",
        provider="huggingFace",
        model_repo_id="local/test-model",
        model_revision="revision-1",
        dimensions=384,
        pooling="useModel",
        document_count=2,
        expected_document_count=2,
        status=SemanticIndexVersion.Status.READY,
    )
    evaluation_set = SearchEvaluationSet.objects.create(
        name="社会理论检索基线",
        created_by=admin_user,
    )
    query = SearchEvaluationQuery.objects.create(
        evaluation_set=evaluation_set,
        query_text="国家如何看见社会",
        normalized_query="国家如何看见社会",
        order=0,
    )
    SearchEvaluationJudgment.objects.create(
        query=query,
        chunk=chunks[0],
        chunk_document_id=chunks[0].document_id,
        relevance=SearchEvaluationJudgment.Relevance.HIGHLY_RELEVANT,
        created_by=admin_user,
    )
    SearchEvaluationJudgment.objects.create(
        query=query,
        chunk=chunks[1],
        chunk_document_id=chunks[1].document_id,
        relevance=SearchEvaluationJudgment.Relevance.NOT_RELEVANT,
        created_by=admin_user,
    )
    return evaluation_set, version, chunks


def runtime_config():
    return {
        "enabled": True,
        "engine": "meilisearch_hybrid",
        "provider": "huggingFace",
        "model_repo_id": "local/test-model",
        "model_revision": "revision-1",
        "dimensions": 384,
        "pooling": "useModel",
        "embedder_name": "test-embedder",
    }


def test_score_query_calculates_required_metrics():
    result = score_query(
        judgments={"a": 3, "b": 0, "c": 2},
        retrieved_document_ids=["b", "a", "x"],
        latency_ms=35,
    )
    assert result.recall_at_20 == pytest.approx(0.5)
    assert result.reciprocal_rank == pytest.approx(0.5)
    assert 0 < result.ndcg_at_10 < 1
    assert result.precision_at_5 == pytest.approx(0.2)
    assert result.top5_useful_passage_rate == 1
    assert result.top3_direct_response_rate == 1
    assert result.result_count == 3
    assert result.latency_ms == 35


def test_topic_only_grade_is_a_hard_negative():
    result = score_query(
        judgments={"topic": 1, "useful": 2, "direct": 3},
        retrieved_document_ids=["topic", "useful", "direct"],
        latency_ms=1,
    )

    assert result.recall_at_20 == 1
    assert result.reciprocal_rank == pytest.approx(0.5)
    assert result.precision_at_5 == pytest.approx(0.4)
    assert result.top5_useful_passage_rate == 1
    assert result.top3_direct_response_rate == 1


def test_preflight_rejects_query_with_only_topic_level_judgment(
    monkeypatch,
    admin_user,
):
    evaluation_set, version, chunks = make_search_fixture(admin_user)
    query = evaluation_set.queries.get()
    query.judgments.all().delete()
    SearchEvaluationJudgment.objects.create(
        query=query,
        chunk=chunks[0],
        chunk_document_id=chunks[0].document_id,
        relevance=SearchEvaluationJudgment.Relevance.TOPIC_ONLY,
        created_by=admin_user,
    )
    from catalog.services import search_evaluation as service

    monkeypatch.setattr(service, "current_semantic_runtime", runtime_config)
    monkeypatch.setattr(service, "semantic_index_document_count", lambda uid: 2)
    plan = build_evaluation_plan(
        evaluation_set,
        version,
        semantic_ratio=0.72,
    )

    assert plan["can_execute"] is False
    assert plan["relevant_threshold"] == 2
    assert {row["code"] for row in plan["blockers"]} == {
        "missing_relevant_judgments"
    }


def test_execute_evaluation_reads_named_candidate_without_switching_index(
    monkeypatch,
    admin_user,
):
    evaluation_set, version, chunks = make_search_fixture(admin_user)
    from catalog.services import search_evaluation as service

    monkeypatch.setattr(service, "current_semantic_runtime", runtime_config)
    monkeypatch.setattr(service, "semantic_index_document_count", lambda uid: 2)
    monkeypatch.setattr(
        service,
        "semantic_search",
        lambda *args, **kwargs: {
            "fallback_used": False,
            "timing_ms": 42,
            "results": [
                {"id": str(chunks[0].id), "title": "检索评估样本", "debug": {"keyword_score": 0.7, "vector_score": 0.8, "rrf_score": 0.9}},
                {"id": str(chunks[1].id), "title": "检索评估样本", "debug": {"rrf_score": 0.4}},
            ],
        },
    )

    run = execute_evaluation(
        evaluation_set,
        version,
        semantic_ratio=0.72,
        actor=admin_user,
    )

    assert run.status == SearchEvaluationRun.Status.COMPLETED
    assert run.metrics == {
        "recall_at_20": 1.0,
        "ndcg_at_10": 1.0,
        "mrr": 1.0,
        "precision_at_5": 0.2,
        "top5_useful_passage_rate": 1.0,
        "top3_direct_response_rate": 1.0,
        "zero_result_rate": 0,
        "p50_latency_ms": 42,
        "p95_latency_ms": 42,
        "query_count": 1,
        "rerank_fallback_rate": 0,
        "reranker_applied_rate": 0,
    }
    assert run.config_snapshot["active_index_changed"] is False
    assert len(run.config_snapshot["evaluation_snapshot_hash"]) == 64
    assert run.config_snapshot["evaluation_snapshot"][0]["query_text"] == "国家如何看见社会"
    assert run.config_snapshot["evaluation_snapshot"][0]["judgments"][0]["chunk_document_id"]
    assert SearchEvaluationResult.objects.filter(run=run).count() == 2
    first_result = SearchEvaluationResult.objects.get(run=run, rank=1)
    assert first_result.keyword_score == pytest.approx(0.7)
    assert first_result.semantic_score == pytest.approx(0.8)
    assert first_result.final_score == pytest.approx(0.9)
    version.refresh_from_db()
    assert version.status == SemanticIndexVersion.Status.READY


def test_admin_api_creates_set_and_executes_explicit_run(
    monkeypatch,
    api_client,
    admin_user,
):
    _evaluation_set, version, chunks = make_search_fixture(admin_user)
    api_client.force_authenticate(admin_user)
    create_response = api_client.post(
        "/api/catalog/admin/search-evaluations/sets/",
        {
            "name": "第二组检索题",
            "description": "用于 API 验证",
            "language": "zh-CN",
            "queries": [
                {
                    "query_text": "社会结构与行动",
                    "judgments": [
                        {
                            "chunk_document_id": chunks[0].document_id,
                            "relevance": 3,
                        }
                    ],
                }
            ],
        },
        format="json",
    )
    assert create_response.status_code == 201
    assert create_response.data["query_count"] == 1
    assert create_response.data["judgment_count"] == 1

    from catalog.services import search_evaluation as service

    monkeypatch.setattr(service, "current_semantic_runtime", runtime_config)
    monkeypatch.setattr(service, "semantic_index_document_count", lambda uid: 2)
    monkeypatch.setattr(
        service,
        "semantic_search",
        lambda *args, **kwargs: {
            "fallback_used": False,
            "timing_ms": 18,
            "results": [{"id": str(chunks[0].id), "debug": {"rrf_score": 1.0}}],
        },
    )
    execute_response = api_client.post(
        "/api/catalog/admin/search-evaluations/runs/",
        {
            "mode": "execute",
            "evaluation_set": create_response.data["id"],
            "index_version": str(version.id),
            "semantic_ratio": 0.72,
        },
        format="json",
    )
    assert execute_response.status_code == 201
    assert execute_response.data["status"] == SearchEvaluationRun.Status.COMPLETED
    assert execute_response.data["metrics"]["recall_at_20"] == 1.0


def test_reader_cannot_access_search_evaluation_admin_api(
    api_client,
    reader_user,
):
    api_client.force_authenticate(reader_user)
    response = api_client.get("/api/catalog/admin/search-evaluations/sets/")
    assert response.status_code == 403


def test_admin_can_append_query_and_disable_set_without_deleting_history(
    api_client,
    admin_user,
):
    evaluation_set, _version, chunks = make_search_fixture(admin_user)
    api_client.force_authenticate(admin_user)

    appended = api_client.post(
        f"/api/catalog/admin/search-evaluations/sets/{evaluation_set.id}/queries/",
        {
            "query_text": "社会行动如何形成",
            "judgments": [
                {"chunk_document_id": chunks[1].document_id, "relevance": 2},
            ],
        },
        format="json",
    )
    disabled = api_client.patch(
        f"/api/catalog/admin/search-evaluations/sets/{evaluation_set.id}/",
        {"is_active": False},
        format="json",
    )

    assert appended.status_code == 201
    assert appended.data["order"] == 1
    assert appended.data["judgments"][0]["chunk_document_id"] == chunks[1].document_id
    assert disabled.status_code == 200
    assert disabled.data["is_active"] is False
    assert disabled.data["query_count"] == 2
    assert evaluation_set.queries.count() == 2


def test_admin_api_enqueues_evaluation_without_searching_in_http_request(
    monkeypatch,
    api_client,
    admin_user,
):
    evaluation_set, version, _chunks = make_search_fixture(admin_user)
    api_client.force_authenticate(admin_user)
    from catalog.services import search_evaluation as service

    monkeypatch.setattr(service, "current_semantic_runtime", runtime_config)
    monkeypatch.setattr(service, "semantic_index_document_count", lambda uid: 2)
    search_mock = lambda *args, **kwargs: pytest.fail("HTTP 请求中不应执行语义检索")
    monkeypatch.setattr(service, "semantic_search", search_mock)
    queued = type("Queued", (), {"id": "evaluation-task-1"})()
    monkeypatch.setattr(
        "catalog.tasks.run_search_evaluation.apply_async",
        lambda **kwargs: queued,
    )

    response = api_client.post(
        "/api/catalog/admin/search-evaluations/runs/",
        {
            "mode": "enqueue",
            "evaluation_set": str(evaluation_set.id),
            "index_version": str(version.id),
            "semantic_ratio": 0.72,
        },
        format="json",
    )

    assert response.status_code == 202
    assert response.data["status"] == SearchEvaluationRun.Status.PENDING
    assert response.data["task_id"] == "evaluation-task-1"
    assert response.data["completed_query_count"] == 0


def test_background_task_completes_prepared_evaluation(
    monkeypatch,
    admin_user,
):
    evaluation_set, version, chunks = make_search_fixture(admin_user)
    from catalog.services import search_evaluation as service

    monkeypatch.setattr(service, "current_semantic_runtime", runtime_config)
    monkeypatch.setattr(service, "semantic_index_document_count", lambda uid: 2)
    captured = {}

    def background_search(*args, **kwargs):
        captured.update(kwargs)
        return {
            "fallback_used": False,
            "timing_ms": 12,
            "search_version": "v2",
            "search_profile": "precision",
            "reranker": {"provider": "local_http", "model": "test", "applied": True},
            "rerank_fallback": False,
            "results": [{"id": str(chunks[0].id), "debug": {"rrf_score": 1.0}}],
        }

    monkeypatch.setattr(
        service,
        "semantic_search",
        background_search,
    )
    run = prepare_evaluation_run(
        evaluation_set,
        version,
        semantic_ratio=0.72,
        actor=admin_user,
        search_version="v2",
        search_profile="precision",
        rerank_top_k=12,
    )
    from catalog.tasks import run_search_evaluation

    payload = run_search_evaluation.run(str(run.id))
    run.refresh_from_db()

    assert payload["status"] == SearchEvaluationRun.Status.COMPLETED
    assert run.completed_query_count == run.query_count == 1
    assert run.results.count() == 1
    assert captured["search_version"] == "v2"
    assert captured["search_profile"] == "precision"
    assert captured["rerank_top_k_override"] == 12


def test_execute_evaluation_forwards_explicit_v2_configuration(
    monkeypatch,
    admin_user,
):
    evaluation_set, version, chunks = make_search_fixture(admin_user)
    from catalog.services import search_evaluation as service

    monkeypatch.setattr(service, "current_semantic_runtime", runtime_config)
    monkeypatch.setattr(service, "semantic_index_document_count", lambda uid: 2)
    captured = {}

    def fake_search(*args, **kwargs):
        captured.update(kwargs)
        return {
            "fallback_used": False,
            "timing_ms": 9,
            "search_version": "v2",
            "search_profile": "precision",
            "reranker": {"provider": "local_http", "model": "test", "applied": True},
            "rerank_fallback": False,
            "results": [{"id": str(chunks[0].id), "debug": {"reranker_score": 0.8}}],
        }

    monkeypatch.setattr(service, "semantic_search", fake_search)
    run = execute_evaluation(
        evaluation_set,
        version,
        semantic_ratio=0.72,
        actor=admin_user,
        search_version="v2",
        search_profile="precision",
        rerank_top_k=24,
    )

    assert captured["search_version"] == "v2"
    assert captured["search_profile"] == "precision"
    assert captured["rerank_top_k_override"] == 24
    assert captured["runtime_config_override"] == runtime_config()
    assert run.config_snapshot["search_version"] == "v2"
    assert run.config_snapshot["search_profile"] == "precision"
    assert run.config_snapshot["rerank_top_k"] == 24
    assert run.metrics["rerank_fallback_rate"] == 0
    assert run.metrics["reranker_applied_rate"] == 1


def test_benchmark_command_dry_run_does_not_create_fake_metrics(
    monkeypatch,
    admin_user,
):
    evaluation_set, version, _chunks = make_search_fixture(admin_user)
    from catalog.services import search_evaluation as service

    monkeypatch.setattr(service, "current_semantic_runtime", runtime_config)
    monkeypatch.setattr(service, "semantic_index_document_count", lambda uid: 2)
    stdout = StringIO()
    call_command(
        "benchmark_opinion_search",
        evaluation_set=str(evaluation_set.id),
        index_version=str(version.id),
        dry_run=True,
        stdout=stdout,
    )
    payload = json.loads(stdout.getvalue())

    assert payload["mode"] == "dry_run"
    assert payload["preflight"]["can_execute"] is True
    assert {row["name"] for row in payload["variants"]} >= {
        "V1",
        "V2-A",
        "V2-B",
        "V2-C",
        "V2-C-rerank-8",
        "V2-C-rerank-32",
    }
    assert all(row["status"] == "待核实" for row in payload["variants"])
    assert all("metrics" not in row for row in payload["variants"])


def test_benchmark_command_executes_each_declared_variant(
    monkeypatch,
    admin_user,
):
    evaluation_set, version, _chunks = make_search_fixture(admin_user)
    from catalog.management.commands import benchmark_opinion_search as command

    monkeypatch.setattr(
        command,
        "build_evaluation_plan",
        lambda *args, **kwargs: {"can_execute": True, "blockers": []},
    )
    captured = []

    def fake_execute(*args, **kwargs):
        captured.append(
            (
                kwargs.get("search_version"),
                kwargs.get("search_profile"),
                kwargs.get("rerank_top_k"),
            )
        )
        return SimpleNamespace(
            id=uuid4(),
            metrics={
                "precision_at_5": 0.4,
                "top5_useful_passage_rate": 1.0,
                "top3_direct_response_rate": 1.0,
                "rerank_fallback_rate": 0,
                "reranker_applied_rate": 1.0,
            },
        )

    monkeypatch.setattr(command, "execute_evaluation", fake_execute)
    stdout = StringIO()
    call_command(
        "benchmark_opinion_search",
        evaluation_set=evaluation_set.name,
        index_version=version.uid,
        stdout=stdout,
    )
    payload = json.loads(stdout.getvalue())

    assert len(captured) == len(payload["variants"]) == 9
    assert ("v1", None, None) in captured
    assert ("v2", "fast", None) in captured
    assert ("v2", "balanced", None) in captured
    assert ("v2", "precision", None) in captured
    assert {
        rerank_top_k
        for version_name, profile, rerank_top_k in captured
        if version_name == "v2" and profile == "precision" and rerank_top_k
    } == {8, 12, 16, 24, 32}
    assert all(row["status"] == "completed" for row in payload["variants"])
