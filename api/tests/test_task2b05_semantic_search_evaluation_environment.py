from __future__ import annotations

from datetime import datetime, timezone as datetime_timezone
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.test import override_settings

from catalog.models import (
    Asset,
    Edition,
    Page,
    QueryLexiconEntry,
    QueryLexiconGeneration,
    QueryLexiconState,
    SemanticChunk,
    SemanticIndexVersion,
    Work,
)
from catalog.services.semantic_chunks import CHUNK_VERSION, PARSER_VERSION
from catalog.services.semantic_search_evaluation_environment import (
    EVALUATION_BUNDLE_SCHEMA,
    EXPORT_SPECS,
    EvaluationEnvironmentError,
    _assert_fresh_evaluation_database,
    _index_evaluation_asset_in_batches,
    _migration_state,
    _secret_free_index_snapshot,
    _serialize_instance,
    _snapshot_querysets,
    _write_queryset,
    build_evaluation_meilisearch_index,
    evaluation_index_uid,
    evaluation_write_guard,
    file_sha256,
    import_evaluation_bundle,
    load_bundle_manifest,
    prepare_pilot_query_candidates,
    validate_snapshot_id,
)


pytestmark = pytest.mark.django_db


def _work_asset(*, title: str = "评测文献"):
    work = Work.objects.create(document_type="book", title=title, language="zh-CN")
    edition = Edition.objects.create(
        work=work,
        state="published",
        is_primary=True,
        public_slug=f"evaluation-{uuid4().hex[:12]}",
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=f"evaluation/{uuid4()}.pdf",
        sha256=uuid4().hex + uuid4().hex,
        status=Asset.Status.READY,
        access_status=Asset.AccessStatus.PUBLIC,
        is_current=True,
    )
    return work, edition, asset


def _chunk(asset, *, order: int, text: str, language: str):
    return SemanticChunk.objects.create(
        asset=asset,
        work=asset.edition.work,
        order=order,
        page_start=order,
        page_end=order,
        original_text=text,
        normalized_text=text.casefold(),
        language=language,
        document_type=asset.edition.work.document_type,
        parser_version=PARSER_VERSION,
        chunk_version=CHUNK_VERSION,
        embedding_model="evaluation-model",
        embedding_version="rev-1",
        document_id=f"evaluation-document-{uuid4().hex}",
        content_hash=uuid4().hex + uuid4().hex,
        index_status=SemanticChunk.IndexStatus.READY,
    )


def test_snapshot_id_and_index_uid_are_bounded_and_deterministic():
    assert validate_snapshot_id("pilot-2026_08") == "pilot-2026_08"
    assert evaluation_index_uid("pilot-2026_08") == "semantic_passages_eval_pilot_2026_08"
    with pytest.raises(EvaluationEnvironmentError):
        validate_snapshot_id("Production Index")


@override_settings(
    SEMANTIC_SEARCH_EVALUATION_MODE=True,
    SEMANTIC_SEARCH_EVALUATION_DATABASE_NAME="library_evaluation",
    SEMANTIC_SEARCH_EVALUATION_MEILISEARCH_URL="http://127.0.0.1:57700",
    MEILISEARCH_URL="http://127.0.0.1:57700",
    SEMANTIC_SEARCH_V2_ENABLED=False,
)
def test_evaluation_write_guard_rejects_sqlite_even_with_evaluation_names():
    with pytest.raises(EvaluationEnvironmentError, match="PostgreSQL"):
        evaluation_write_guard("pilot-2026")


def test_secret_free_index_snapshot_drops_secrets_and_url_credentials():
    version = SimpleNamespace(
        id=uuid4(),
        uid="semantic_passages",
        status="active",
        created_at=datetime.now(datetime_timezone.utc),
        provider="huggingFace",
        model_repo_id="model/repo",
        model_revision="fixed-revision",
        dimensions=384,
        pooling="useModel",
        document_template="{{doc.original_text}}",
        document_count=12,
        expected_document_count=12,
        config_snapshot={
            "engine": "meilisearch_hybrid",
            "provider": "huggingFace",
            "model": "model/repo",
            "service_url": "https://user:password@example.test/embed?token=secret",
            "api_key": "must-not-leak",
            "password": "must-not-leak",
            "viewpoint_v2": {
                "profile": "precision",
                "rerank_api_key": "must-not-leak",
            },
            "parser_version": PARSER_VERSION,
            "chunk_version": CHUNK_VERSION,
        },
    )
    snapshot = _secret_free_index_snapshot(version)
    serialized = json.dumps(snapshot, sort_keys=True)
    assert "must-not-leak" not in serialized
    assert "password" not in serialized
    assert snapshot["config_snapshot"]["service_url"] == "https://example.test/embed"
    assert snapshot["config_snapshot"]["viewpoint_v2"] == {"profile": "precision"}


def test_bundle_manifest_verifies_each_checksum(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    data = bundle / "catalog.work.jsonl"
    data.write_text('{"model":"catalog.work"}\n', encoding="utf-8")
    manifest = {
        "schema": EVALUATION_BUNDLE_SCHEMA,
        "snapshot_id": "pilot-2026",
        "files": [
            {
                "path": data.name,
                "sha256": file_sha256(data),
                "rows": 1,
            }
        ],
    }
    (bundle / "bundle-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    _root, loaded = load_bundle_manifest(bundle)
    assert loaded["snapshot_id"] == "pilot-2026"

    data.write_text("changed\n", encoding="utf-8")
    with pytest.raises(EvaluationEnvironmentError, match="checksum"):
        load_bundle_manifest(bundle)


def test_search_only_asset_export_replaces_file_identity_and_internal_notes():
    _work, _edition, asset = _work_asset()
    asset.original_filename = "private-source-name.pdf"
    asset.rights_note = "internal-only note"
    asset.validation_details = {"local_path": "C:/sensitive/path"}
    record = _serialize_instance(
        asset,
        {"work_ids": set(), "asset_ids": {str(asset.id)}},
    )
    fields = record["fields"]
    assert fields["file"] == f"evaluation/assets/{asset.id}.pdf"
    assert fields["original_filename"] == ""
    assert fields["rights_note"] == ""
    assert fields["validation_details"] == {}
    assert fields["byte_size"] == 0
    assert fields["sha256"] != asset.sha256


def test_fresh_database_accepts_only_migration_seeded_empty_lexicon():
    state = QueryLexiconState.objects.select_related("active_generation").get(
        key="default"
    )
    assert state.revision == 0
    assert QueryLexiconGeneration.objects.count() == 1
    _assert_fresh_evaluation_database()

    Work.objects.create(document_type="book", title="占用记录")
    with pytest.raises(EvaluationEnvironmentError, match="不是空的"):
        _assert_fresh_evaluation_database()


def test_pilot_candidates_are_data_backed_but_never_contain_gold_or_passage_ids(
    tmp_path,
    monkeypatch,
):
    work, _edition, asset = _work_asset()
    Page.objects.create(
        asset=asset,
        index=1,
        text="惯习会在日常实践中形成。",
        normalized_text="惯习会在日常实践中形成。",
        text_source="ocr",
    )
    Page.objects.create(
        asset=asset,
        index=2,
        text="Habitus is durable and embodied.",
        normalized_text="habitus is durable and embodied.",
        text_source="embedded",
    )
    _chunk(asset, order=1, text="惯习会在日常实践中形成。", language="zh")
    _chunk(asset, order=2, text="Habitus is durable and embodied.", language="en")
    _chunk(asset, order=3, text="惯习 habitus in one passage.", language="mixed")

    state = QueryLexiconState.objects.select_related("active_generation").get(
        key="default"
    )
    entity_id = uuid4()
    QueryLexiconEntry.objects.create(
        generation=state.active_generation,
        entity_type=QueryLexiconEntry.EntityType.KNOWLEDGE_NODE,
        entity_id=entity_id,
        term="惯习",
        normalized_term="惯习",
        language="zh-Hans",
        term_type=QueryLexiconEntry.TermType.CANONICAL,
        source_kind=QueryLexiconEntry.SourceKind.AUTHORITY_FIELD,
        trust_level=QueryLexiconEntry.TrustLevel.AUTHORITATIVE,
        source_ref="test:zh",
        source_fingerprint=uuid4().hex + uuid4().hex,
        displayable=True,
        public_active=True,
        admin_resolvable=True,
    )
    QueryLexiconEntry.objects.create(
        generation=state.active_generation,
        entity_type=QueryLexiconEntry.EntityType.KNOWLEDGE_NODE,
        entity_id=entity_id,
        term="habitus",
        normalized_term="habitus",
        language="en",
        term_type=QueryLexiconEntry.TermType.TRANSLATION,
        source_kind=QueryLexiconEntry.SourceKind.KNOWLEDGE_NODE_ALIAS,
        trust_level=QueryLexiconEntry.TrustLevel.VERIFIED,
        source_ref="test:en",
        source_fingerprint=uuid4().hex + uuid4().hex,
        displayable=True,
        public_active=True,
        admin_resolvable=True,
    )
    state.active_generation.entry_count = 2
    state.active_generation.save(update_fields=["entry_count", "updated_at"])
    snapshot_id = "pilot-2026"
    uid = evaluation_index_uid(snapshot_id)
    SemanticIndexVersion.objects.create(
        uid=uid,
        provider="huggingFace",
        model_repo_id="evaluation-model",
        model_revision="rev-1",
        dimensions=384,
        pooling="useModel",
        config_snapshot={"engine": "meilisearch_hybrid", "model": "evaluation-model"},
        document_count=3,
        expected_document_count=3,
        status=SemanticIndexVersion.Status.READY,
    )
    monkeypatch.setattr(
        "catalog.services.semantic_search_evaluation_environment.evaluation_write_guard",
        lambda value: {
            "snapshot_id": value,
            "evaluation_index_uid": uid,
        },
    )
    output = tmp_path / "pilot-query-candidates.jsonl"
    report = prepare_pilot_query_candidates(
        snapshot_id=snapshot_id,
        output_path=output,
        limit=20,
        per_direction_minimum=1,
    )
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert report["candidate_count"] >= 5
    assert {record["direction"] for record in records} == {
        "zh_to_zh",
        "zh_to_en",
        "en_to_zh",
        "en_to_en",
        "mixed",
    }
    assert all(record["automatic_gold"] is False for record in records)
    assert all("gold_judgments" not in record for record in records)
    assert all("passage" not in json.dumps(record).casefold() for record in records)
    assert work.id


def test_bundle_import_restores_search_rows_and_rebuilds_derived_lexicon(
    tmp_path,
    monkeypatch,
):
    work, edition, asset = _work_asset(title="可重复导入")
    Page.objects.create(
        asset=asset,
        index=1,
        text="可重复导入的真实片段。",
        normalized_text="可重复导入的真实片段。",
        text_source="ocr",
    )
    _chunk(asset, order=1, text="可重复导入的真实片段。", language="zh")
    source_version = SemanticIndexVersion.objects.create(
        uid=f"semantic_passages_source_{uuid4().hex[:8]}",
        provider="huggingFace",
        model_repo_id="evaluation-model",
        model_revision="rev-1",
        dimensions=384,
        pooling="useModel",
        config_snapshot={
            "engine": "meilisearch_hybrid",
            "provider": "huggingFace",
            "model": "evaluation-model",
            "model_repo_id": "evaluation-model",
            "model_revision": "rev-1",
            "parser_version": PARSER_VERSION,
            "chunk_version": CHUNK_VERSION,
        },
        document_count=1,
        expected_document_count=1,
        status=SemanticIndexVersion.Status.READY,
    )
    bundle = tmp_path / "bundle-import"
    bundle.mkdir()
    querysets, selected = _snapshot_querysets(source_version)
    counts = {}
    files = []
    for spec in EXPORT_SPECS:
        path = bundle / spec.filename
        counts[spec.label] = _write_queryset(
            path,
            querysets[spec.label],
            selected,
            batch_size=100,
        )
        files.append(
            {
                "path": spec.filename,
                "model": spec.label,
                "rows": counts[spec.label],
                "sha256": file_sha256(path),
            }
        )
    snapshot_id = "sqlite-import"
    uid = evaluation_index_uid(snapshot_id)
    manifest = {
        "schema": EVALUATION_BUNDLE_SCHEMA,
        "snapshot_id": snapshot_id,
        "evaluation_index_uid": uid,
        "migrations": _migration_state(),
        "counts": counts,
        "semantic_chunk_count": 1,
        "source_semantic_index_version": _secret_free_index_snapshot(
            source_version
        ),
        "files": files,
    }
    (bundle / "bundle-manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    SemanticChunk._base_manager.all().delete()
    Page._base_manager.all().delete()
    Asset._base_manager.all().delete()
    Edition._base_manager.all().delete()
    Work._base_manager.all().delete()
    SemanticIndexVersion._base_manager.all().delete()
    monkeypatch.setattr(
        "catalog.services.semantic_search_evaluation_environment.evaluation_write_guard",
        lambda value: {"snapshot_id": value, "evaluation_index_uid": uid},
    )
    result = import_evaluation_bundle(
        bundle_dir=bundle,
        snapshot_id=snapshot_id,
        batch_size=100,
    )
    assert result["imported"]["catalog.work"] == 1
    assert result["imported"]["catalog.semanticchunk"] == 1
    assert Work.objects.get().title == "可重复导入"
    assert SemanticChunk.objects.get().original_text == "可重复导入的真实片段。"
    assert SemanticIndexVersion.objects.get().uid == uid
    assert SemanticIndexVersion.objects.get().status == SemanticIndexVersion.Status.BUILDING
    assert QueryLexiconState.objects.get(key="default").revision >= 1


def test_evaluation_index_build_stays_ready_and_never_becomes_active(monkeypatch):
    _work, _edition, asset = _work_asset(title="隔离索引")
    _chunk(asset, order=1, text="isolated evaluation document", language="en")
    snapshot_id = "index-build"
    uid = evaluation_index_uid(snapshot_id)
    version = SemanticIndexVersion.objects.create(
        uid=uid,
        provider="huggingFace",
        model_repo_id="evaluation-model",
        model_revision="rev-1",
        dimensions=384,
        pooling="useModel",
        config_snapshot={
            "engine": "meilisearch_hybrid",
            "provider": "huggingFace",
            "model": "evaluation-model",
            "model_repo_id": "evaluation-model",
            "parser_version": PARSER_VERSION,
            "chunk_version": CHUNK_VERSION,
        },
        document_count=0,
        expected_document_count=1,
        status=SemanticIndexVersion.Status.BUILDING,
    )
    monkeypatch.setattr(
        "catalog.services.semantic_search_evaluation_environment.evaluation_write_guard",
        lambda value: {"snapshot_id": value, "evaluation_index_uid": uid},
    )
    monkeypatch.setattr(
        "catalog.services.semantic_search_evaluation_environment._meili_index_stats",
        lambda _uid: None,
    )
    monkeypatch.setattr(
        "catalog.services.semantic_search_evaluation_environment.ensure_semantic_index",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "catalog.services.semantic_search_evaluation_environment._index_evaluation_asset_in_batches",
        lambda *_args, **_kwargs: {
            "backend": "meilisearch",
            "documents": 1,
            "batches": 1,
        },
    )
    monkeypatch.setattr(
        "catalog.services.semantic_search_evaluation_environment.semantic_index_document_count",
        lambda _uid: 1,
    )
    result = build_evaluation_meilisearch_index(snapshot_id=snapshot_id)
    version.refresh_from_db()
    assert result["reembedding_performed"] is True
    assert result["batch_count"] == 1
    assert result["document_batch_size"] == 128
    assert result["semantic_index_activated"] is False
    assert version.status == SemanticIndexVersion.Status.READY
    assert version.document_count == 1
    assert not SemanticIndexVersion.objects.filter(
        status=SemanticIndexVersion.Status.ACTIVE
    ).exists()


def test_evaluation_index_batches_large_assets_without_touching_chunk_state(monkeypatch):
    submitted = []
    documents = [{"id": str(index)} for index in range(5)]
    monkeypatch.setattr(
        "catalog.services.semantic_search_evaluation_environment.semantic_documents",
        lambda *_args, **_kwargs: documents,
    )

    def fake_post(_url, *, headers, json, timeout):
        assert headers is not None
        assert timeout >= 30
        submitted.append([row["id"] for row in json])
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"taskUid": len(submitted)},
        )

    monkeypatch.setattr(
        "catalog.services.semantic_search_evaluation_environment.httpx.post",
        fake_post,
    )
    monkeypatch.setattr(
        "catalog.services.semantic_search_evaluation_environment._wait_task",
        lambda *_args, **_kwargs: {"status": "succeeded"},
    )
    result = _index_evaluation_asset_in_batches(
        SimpleNamespace(id="asset-1"),
        version=SimpleNamespace(uid="semantic_passages_eval_batching"),
        runtime={},
        document_batch_size=2,
    )
    assert submitted == [["0", "1"], ["2", "3"], ["4"]]
    assert result == {
        "backend": "meilisearch",
        "index_uid": "semantic_passages_eval_batching",
        "documents": 5,
        "batches": 3,
        "document_batch_size": 2,
    }
