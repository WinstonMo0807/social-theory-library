from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from catalog.models import (
    Asset,
    OcrStatus,
    Page,
    SemanticChunk,
    SemanticIndexJob,
    SemanticIndexVersion,
    SiteSetting,
)
from catalog.services.semantic_chunks import (
    CHUNK_VERSION,
    PARSER_VERSION,
    build_semantic_chunks,
)
from catalog.services.semantic_indexing import (
    DEFAULT_DOCUMENT_TEMPLATE,
    activate_semantic_index_version,
    dispatch_semantic_version_batch,
    ensure_semantic_index,
    index_semantic_asset,
    resume_semantic_job,
    run_semantic_index_job,
    semantic_documents,
    semantic_index_config_snapshot,
    set_semantic_index_paused,
    stage_semantic_index_version,
)

from .test_resilient_publication_v260 import create_item_with_files


def runtime_config(tmp_path):
    return {
        "enabled": True,
        "engine": "meilisearch_hybrid",
        "provider": "huggingFace",
        "embedder_name": "social-science-library-v2",
        "model": "example/chinese-social-theory-embedding",
        "model_repo_id": "example/chinese-social-theory-embedding",
        "model_local_path": str(tmp_path / "models"),
        "model_revision": "revision-v2",
        "dimensions": 768,
        "pooling": "useModel",
        "offline_mode": True,
        "semantic_ratio": 0.72,
        "reranker": "rules",
        "query_rewrite_enabled": False,
        "max_results_per_work": 4,
        "viewpoint_v2": {
            "enabled": True,
            "profile": "precision",
            "dense_top_k": 50,
            "sparse_top_k": 50,
            "fusion_top_k": 24,
            "rerank_top_k": 24,
            "final_top_k": 10,
            "query_expansion_enabled": True,
            "query_expansion_max": 3,
            "rerank_provider": "rules",
            "rerank_model": "",
            "rerank_service_configured": False,
            "api_key": "nested-secret",
        },
        "service_url": "https://user:secret@example.test/embed?api_key=hidden",
        "api_key": "must-not-be-persisted",
    }


@pytest.mark.django_db
def test_stage_records_secret_free_v2_runtime_snapshot(settings, tmp_path):
    _work, edition, _original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="V2 候选配置快照",
    )
    edition.ocr_status = OcrStatus.NOT_REQUIRED
    edition.save(update_fields=["ocr_status", "updated_at"])
    runtime = runtime_config(tmp_path)

    with patch("catalog.services.semantic_indexing.ensure_semantic_index") as ensure:
        version = stage_semantic_index_version(
            runtime,
            auto_dispatch=False,
            asset_queryset=Asset.objects.filter(pk=normalized.pk),
        )

    snapshot = version.config_snapshot
    assert snapshot["protocol_version"] == "v2"
    assert snapshot["parser_version"] == PARSER_VERSION
    assert snapshot["chunk_version"] == CHUNK_VERSION
    assert snapshot["document_template"] == DEFAULT_DOCUMENT_TEMPLATE
    assert snapshot["embedder_name"] == runtime["embedder_name"]
    assert snapshot["viewpoint_v2"]["profile"] == "precision"
    assert "api_key" not in snapshot["viewpoint_v2"]
    assert snapshot["service_url"] == "https://example.test/embed"
    assert "api_key" not in snapshot
    assert "must-not-be-persisted" not in str(snapshot)
    assert "user:secret" not in str(snapshot)
    assert "api_key=hidden" not in str(snapshot)
    ensure.assert_called_once_with(snapshot, index_uid=version.uid)


@pytest.mark.django_db
def test_explicit_runtime_builds_chunks_and_documents_without_global_runtime(
    settings,
    tmp_path,
):
    work, _edition, _original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="稳定段落索引字段",
    )
    normalized.access_status = Asset.AccessStatus.REGISTERED
    normalized.save(update_fields=["access_status", "updated_at"])
    Page.objects.create(
        asset=normalized,
        index=1,
        text="社会理论研究需要保留原文证据和页码定位。" * 12,
        normalized_text="社会理论研究需要保留原文证据和页码定位。" * 12,
        text_source=Page.TextSource.EMBEDDED,
    )
    runtime = runtime_config(tmp_path)

    with patch(
        "catalog.services.semantic_chunks._current_model_name",
        side_effect=AssertionError("不应读取全局运行配置"),
    ):
        chunks = build_semantic_chunks(normalized, runtime_config=runtime)

    assert chunks
    assert chunks[0].embedding_model == runtime["model_repo_id"]
    documents = semantic_documents(normalized, runtime_config=runtime)
    assert documents[0]["document_id"] == chunks[0].document_id
    assert documents[0]["access_status"] == Asset.AccessStatus.REGISTERED
    assert documents[0]["work_id"] == str(work.id)


@pytest.mark.django_db
def test_candidate_index_uses_its_saved_runtime_snapshot(settings, tmp_path):
    _work, _edition, _original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="候选索引独立运行配置",
    )
    snapshot = semantic_index_config_snapshot(runtime_config(tmp_path))
    version = SemanticIndexVersion.objects.create(
        uid="semantic_candidate_runtime_v2",
        provider=snapshot["provider"],
        model_repo_id=snapshot["model_repo_id"],
        config_snapshot=snapshot,
    )
    response = Mock()
    response.json.return_value = {"taskUid": 73}
    documents = [
        {
            "id": "chunk-1",
            "document_id": "d" * 64,
            "asset_id": str(normalized.id),
            "access_status": normalized.access_status,
        }
    ]

    with patch(
        "catalog.services.semantic_indexing.semantic_documents",
        return_value=documents,
    ) as document_builder, patch(
        "catalog.services.semantic_indexing.ensure_semantic_index"
    ) as ensure, patch(
        "catalog.services.semantic_indexing.httpx.post",
        return_value=response,
    ), patch(
        "catalog.services.semantic_indexing._wait_task",
        return_value={"status": "succeeded"},
    ), patch(
        "catalog.services.semantic_indexing._remove_stale_semantic_asset_documents",
        return_value=0,
    ):
        result = index_semantic_asset(normalized, index_version=version)

    assert result["index_uid"] == version.uid
    document_builder.assert_called_once_with(normalized, runtime_config=snapshot)
    ensure.assert_called_once_with(snapshot, index_uid=version.uid)


@pytest.mark.django_db
def test_model_change_stages_candidate_without_mutating_effective_runtime(
    api_client,
    admin_user,
    tmp_path,
):
    old_value = {
        "engine": "meilisearch_hybrid",
        "provider": "huggingFace",
        "embedder_name": "production-embedder",
        "model": "example/production-model",
        "model_repo_id": "example/production-model",
        "model_local_path": str(tmp_path / "models"),
        "model_revision": "production-revision",
        "dimensions": 384,
        "pooling": "useModel",
        "offline_mode": True,
        "service_url": "",
        "semantic_ratio": 0.72,
        "reranker": "rules",
        "query_rewrite_enabled": False,
        "max_results_per_work": 2,
    }
    SiteSetting.objects.create(
        key="semantic_search_runtime",
        value=old_value,
        public=False,
        updated_by=admin_user,
    )
    snapshot = semantic_index_config_snapshot(runtime_config(tmp_path))
    candidate = SemanticIndexVersion.objects.create(
        uid="semantic_pending_runtime_v2",
        provider=snapshot["provider"],
        model_repo_id=snapshot["model_repo_id"],
        model_revision=snapshot["model_revision"],
        dimensions=snapshot["dimensions"],
        pooling=snapshot["pooling"],
        config_snapshot=snapshot,
    )
    api_client.force_authenticate(admin_user)

    with patch(
        "catalog.views.stage_semantic_index_version",
        return_value=candidate,
    ), patch(
        "catalog.views.semantic_model_health",
        return_value={"available": True, "reason": "测试配置可用"},
    ):
        response = api_client.put(
            "/api/catalog/admin/semantic-runtime/",
            runtime_config(tmp_path),
            format="json",
        )

    assert response.status_code == 202
    assert response.data["task"]["version_id"] == str(candidate.id)
    assert response.data["effective"] is False
    assert response.data["pending_configuration"]["model_repo_id"] == snapshot["model_repo_id"]
    assert SiteSetting.objects.get(key="semantic_search_runtime").value == old_value


@pytest.mark.django_db(transaction=True)
def test_activation_atomically_promotes_saved_candidate_runtime(
    settings,
    tmp_path,
    admin_user,
):
    _work, _edition, _original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="候选配置切换",
    )
    snapshot = semantic_index_config_snapshot(runtime_config(tmp_path))
    version = SemanticIndexVersion.objects.create(
        uid="semantic_activation_runtime_v2",
        provider=snapshot["provider"],
        model_repo_id=snapshot["model_repo_id"],
        model_revision=snapshot["model_revision"],
        dimensions=snapshot["dimensions"],
        pooling=snapshot["pooling"],
        expected_document_count=1,
        status=SemanticIndexVersion.Status.READY,
        config_snapshot=snapshot,
    )
    SemanticIndexJob.objects.create(
        asset=normalized,
        index_version=version,
        operation=SemanticIndexJob.Operation.BUILD,
        status=SemanticIndexJob.Status.COMPLETED,
        stats={"documents": 1},
    )
    old_value = {"engine": "lightweight", "provider": "huggingFace"}
    SiteSetting.objects.create(
        key="semantic_search_runtime",
        value=old_value,
        public=False,
        updated_by=admin_user,
    )

    with patch(
        "catalog.services.semantic_search.semantic_model_health",
        return_value={"available": True, "reason": "候选模型可用"},
    ), patch(
        "catalog.services.semantic_indexing.semantic_index_document_count",
        return_value=1,
    ):
        activated = activate_semantic_index_version(version, actor=admin_user)

    assert activated.status == SemanticIndexVersion.Status.ACTIVE
    effective = SiteSetting.objects.get(key="semantic_search_runtime")
    assert effective.value["model_repo_id"] == snapshot["model_repo_id"]
    assert effective.value["model_revision"] == snapshot["model_revision"]
    assert effective.updated_by_id == admin_user.id


@pytest.mark.django_db
def test_index_settings_expose_stable_identity_and_access_status(settings):
    existing = Mock(status_code=200)
    updated = Mock()
    updated.json.return_value = {"taskUid": 82}
    config = {
        "engine": "lightweight",
        "provider": "huggingFace",
    }

    with patch(
        "catalog.services.semantic_indexing.httpx.get",
        return_value=existing,
    ), patch(
        "catalog.services.semantic_indexing.httpx.patch",
        return_value=updated,
    ) as patched, patch(
        "catalog.services.semantic_indexing._wait_task",
        return_value={"status": "succeeded"},
    ):
        ensure_semantic_index(config, index_uid="semantic_settings_v2")

    desired = patched.call_args.kwargs["json"]
    assert "document_id" in desired["filterableAttributes"]
    assert "document_id" in desired["displayedAttributes"]
    assert "access_status" in desired["filterableAttributes"]
    assert "access_status" in desired["displayedAttributes"]


@pytest.mark.django_db(transaction=True)
def test_running_semantic_job_pauses_after_chunk_stage_and_resumes_same_job(
    settings,
    tmp_path,
    admin_user,
):
    _work, _edition, _original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="语义任务协作暂停",
    )
    snapshot = semantic_index_config_snapshot(runtime_config(tmp_path))
    version = SemanticIndexVersion.objects.create(
        uid="semantic_pause_v2",
        provider=snapshot["provider"],
        model_repo_id=snapshot["model_repo_id"],
        config_snapshot=snapshot,
    )
    job = SemanticIndexJob.objects.create(
        asset=normalized,
        index_version=version,
        operation=SemanticIndexJob.Operation.REBUILD,
        status=SemanticIndexJob.Status.QUEUED,
        task_id="semantic-pause-task",
    )

    def build_and_request_pause(*_args, **_kwargs):
        SemanticIndexJob.objects.filter(pk=job.pk).update(
            pause_requested_at=job.created_at,
        )
        return [SimpleNamespace(embedding_model=snapshot["model_repo_id"])]

    with patch(
        "catalog.services.semantic_indexing.build_semantic_chunks",
        side_effect=build_and_request_pause,
    ), patch(
        "catalog.services.semantic_indexing.index_semantic_asset"
    ) as indexer:
        paused = run_semantic_index_job(
            str(job.id),
            task_id="semantic-pause-task",
        )

    paused.refresh_from_db()
    assert paused.id == job.id
    assert paused.status == SemanticIndexJob.Status.PAUSED
    assert paused.stats["paused_at_stage"] == "chunks_persisted"
    indexer.assert_not_called()

    with patch(
        "catalog.services.semantic_indexing.dispatch_semantic_job",
        return_value=True,
    ) as dispatch:
        resumed = resume_semantic_job(paused, actor=admin_user)

    resumed.refresh_from_db()
    assert resumed.id == job.id
    assert resumed.status == SemanticIndexJob.Status.QUEUED
    assert resumed.pause_requested_at is None
    assert resumed.task_id and resumed.task_id != "semantic-pause-task"
    dispatch.assert_called_once_with(str(job.id), resumed.task_id)


@pytest.mark.django_db(transaction=True)
def test_paused_workload_does_not_dispatch_next_candidate_batch(
    settings,
    tmp_path,
    admin_user,
):
    _work, _edition, _original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="暂停时不派发候选批次",
    )
    version = SemanticIndexVersion.objects.create(
        uid="semantic_paused_batch_v2",
        provider="huggingFace",
    )
    job = SemanticIndexJob.objects.create(
        asset=normalized,
        index_version=version,
        operation=SemanticIndexJob.Operation.BUILD,
        status=SemanticIndexJob.Status.PAUSED,
    )
    set_semantic_index_paused(True, actor=admin_user)

    with patch(
        "catalog.services.semantic_indexing.dispatch_semantic_job"
    ) as dispatch:
        result = dispatch_semantic_version_batch(version, batch_size=1)

    job.refresh_from_db()
    assert result["queued"] == 0
    assert result["paused"] == 1
    assert job.status == SemanticIndexJob.Status.PAUSED
    dispatch.assert_not_called()
