from __future__ import annotations

from uuid import uuid4

import pytest
from django.db import connection

from catalog.models import (
    Asset,
    Edition,
    Page,
    QueryLexiconState,
    SemanticChunk,
    SemanticIndexVersion,
    Work,
)
from catalog.services.semantic_chunks import CHUNK_VERSION, PARSER_VERSION
from catalog.services.semantic_search_evaluation_environment import (
    export_evaluation_bundle,
    evaluation_index_uid,
    import_evaluation_bundle,
    load_bundle_manifest,
)


pytestmark = [
    pytest.mark.postgres_integration,
    pytest.mark.django_db(transaction=True),
]


@pytest.fixture(autouse=True)
def require_postgresql():
    if connection.vendor != "postgresql":
        pytest.skip("requires PostgreSQL")


def test_postgres_search_only_export_uses_a_coherent_read_only_snapshot(tmp_path):
    work = Work.objects.create(document_type="book", title="PostgreSQL evaluation export")
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
    Page.objects.create(
        asset=asset,
        index=1,
        text="真实 PostgreSQL 只读快照。",
        normalized_text="真实 postgresql 只读快照。",
        text_source="ocr",
    )
    SemanticChunk.objects.create(
        asset=asset,
        work=work,
        order=1,
        page_start=1,
        page_end=1,
        original_text="真实 PostgreSQL 只读快照。",
        normalized_text="真实 postgresql 只读快照。",
        language="zh",
        document_type=work.document_type,
        parser_version=PARSER_VERSION,
        chunk_version=CHUNK_VERSION,
        embedding_model="evaluation-model",
        embedding_version="fixed-revision",
        document_id=f"evaluation-{uuid4().hex}",
        content_hash=uuid4().hex + uuid4().hex,
        index_status=SemanticChunk.IndexStatus.READY,
    )
    version = SemanticIndexVersion.objects.create(
        uid=f"semantic_passages_source_{uuid4().hex[:8]}",
        provider="huggingFace",
        model_repo_id="evaluation-model",
        model_revision="fixed-revision",
        dimensions=384,
        pooling="useModel",
        config_snapshot={
            "engine": "meilisearch_hybrid",
            "provider": "huggingFace",
            "model": "evaluation-model",
            "model_repo_id": "evaluation-model",
            "model_revision": "fixed-revision",
            "parser_version": PARSER_VERSION,
            "chunk_version": CHUNK_VERSION,
        },
        document_count=1,
        expected_document_count=1,
        status=SemanticIndexVersion.Status.READY,
    )
    output = tmp_path / "postgres-export"
    manifest = export_evaluation_bundle(
        output_dir=output,
        snapshot_id="postgres-pilot",
        index_version_value=version.uid,
        source_kind="backup_restore",
    )
    assert manifest["source"]["transaction_read_only"] is True
    assert manifest["source"]["transaction_isolation"].casefold() == "repeatable read"
    assert manifest["semantic_chunk_count"] == 1
    assert manifest["contains_authentication_data"] is False
    assert all(not row["model"].startswith("accounts.") for row in manifest["files"])
    _root, verified = load_bundle_manifest(output)
    assert verified["config_hash"] == manifest["config_hash"]


def test_postgres_bundle_import_rebuilds_lexicon_and_clones_only_evaluation_version(
    tmp_path,
    monkeypatch,
):
    work = Work.objects.create(document_type="book", title="Evaluation import source")
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
    Page.objects.create(
        asset=asset,
        index=1,
        text="Bundle import keeps passage text.",
        normalized_text="bundle import keeps passage text.",
        text_source="embedded",
    )
    SemanticChunk.objects.create(
        asset=asset,
        work=work,
        order=1,
        page_start=1,
        page_end=1,
        original_text="Bundle import keeps passage text.",
        normalized_text="bundle import keeps passage text.",
        language="en",
        document_type=work.document_type,
        parser_version=PARSER_VERSION,
        chunk_version=CHUNK_VERSION,
        embedding_model="evaluation-model",
        embedding_version="fixed-revision",
        document_id=f"evaluation-{uuid4().hex}",
        content_hash=uuid4().hex + uuid4().hex,
        index_status=SemanticChunk.IndexStatus.READY,
    )
    source_version = SemanticIndexVersion.objects.create(
        uid=f"semantic_passages_source_{uuid4().hex[:8]}",
        provider="huggingFace",
        model_repo_id="evaluation-model",
        model_revision="fixed-revision",
        dimensions=384,
        pooling="useModel",
        config_snapshot={
            "engine": "meilisearch_hybrid",
            "provider": "huggingFace",
            "model": "evaluation-model",
            "model_repo_id": "evaluation-model",
            "model_revision": "fixed-revision",
            "parser_version": PARSER_VERSION,
            "chunk_version": CHUNK_VERSION,
        },
        document_count=1,
        expected_document_count=1,
        status=SemanticIndexVersion.Status.READY,
    )
    snapshot_id = "postgres-import"
    output = tmp_path / "postgres-import-bundle"
    export_evaluation_bundle(
        output_dir=output,
        snapshot_id=snapshot_id,
        index_version_value=source_version.uid,
        source_kind="backup_restore",
    )

    SemanticChunk._base_manager.all().delete()
    Page._base_manager.all().delete()
    Asset._base_manager.all().delete()
    Edition._base_manager.all().delete()
    Work._base_manager.all().delete()
    SemanticIndexVersion._base_manager.all().delete()
    uid = evaluation_index_uid(snapshot_id)
    monkeypatch.setattr(
        "catalog.services.semantic_search_evaluation_environment.evaluation_write_guard",
        lambda value: {
            "snapshot_id": value,
            "evaluation_index_uid": uid,
        },
    )
    result = import_evaluation_bundle(
        bundle_dir=output,
        snapshot_id=snapshot_id,
    )
    assert result["imported"]["catalog.semanticchunk"] == 1
    assert SemanticChunk.objects.count() == 1
    assert SemanticIndexVersion.objects.get().uid == uid
    assert SemanticIndexVersion.objects.get().status == SemanticIndexVersion.Status.BUILDING
    state = QueryLexiconState.objects.select_related("active_generation").get(key="default")
    assert state.revision >= 0
