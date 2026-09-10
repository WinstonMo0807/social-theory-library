from unittest.mock import Mock, call, patch
from types import SimpleNamespace

import pytest

from django.test import override_settings

from ingestion.services.indexing import (
    _indexed_asset_document_ids,
    _remove_stale_asset_documents,
    index_asset,
)


def _response(payload):
    response = Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


@override_settings(MEILISEARCH_URL="http://meilisearch:7700")
def test_indexed_asset_document_ids_reads_every_page():
    with patch(
        "ingestion.services.indexing.httpx.post",
        side_effect=[
            _response({"results": [{"id": "a"}, {"id": "b"}], "total": 3}),
            _response({"results": [{"id": "c"}], "total": 3}),
        ],
    ) as post:
        result = _indexed_asset_document_ids("asset-1")

    assert result == {"a", "b", "c"}
    assert post.call_args_list[0].kwargs["json"]["offset"] == 0
    assert post.call_args_list[1].kwargs["json"]["offset"] == 2


@override_settings(MEILISEARCH_URL="http://meilisearch:7700")
def test_remove_stale_asset_documents_deletes_only_the_difference_in_chunks():
    stale_ids = {f"stale-{index:04d}" for index in range(1001)}
    with (
        patch(
            "ingestion.services.indexing._indexed_asset_document_ids",
            return_value={"current-1", "current-2", *stale_ids},
        ),
        patch(
            "ingestion.services.indexing.httpx.post",
            side_effect=[_response({"taskUid": 1}), _response({"taskUid": 2})],
        ) as post,
        patch("ingestion.services.indexing._wait_task") as wait_task,
    ):
        removed = _remove_stale_asset_documents(
            "asset-1",
            {"current-1", "current-2"},
        )

    assert removed == 1001
    assert post.call_count == 2
    assert len(post.call_args_list[0].kwargs["json"]) == 1000
    assert len(post.call_args_list[1].kwargs["json"]) == 1
    assert all("delete-batch" in item.args[0] for item in post.call_args_list)
    assert wait_task.call_args_list == [
        call({"taskUid": 1}, timeout=60),
        call({"taskUid": 2}, timeout=60),
    ]


@override_settings(MEILISEARCH_URL="http://meilisearch:7700")
def test_remove_stale_asset_documents_skips_delete_when_index_matches():
    with (
        patch(
            "ingestion.services.indexing._indexed_asset_document_ids",
            return_value={"current-1"},
        ),
        patch("ingestion.services.indexing.httpx.post") as post,
    ):
        removed = _remove_stale_asset_documents("asset-1", {"current-1"})

    assert removed == 0
    post.assert_not_called()


def _asset_with_passages(*passages):
    asset = Mock()
    asset.id = "asset-1"
    asset.pk = asset.id
    asset.edition_id = "edition-1"
    asset.edition.state = "published"
    asset.edition.public_slug = "example"
    asset.edition.publication_year = 2026
    asset.edition.contributions.filter.return_value.order_by.return_value.values_list.return_value = []
    asset.edition.work.id = "work-1"
    asset.edition.work.title = "测试作品"
    asset.edition.work.document_type = "book"
    asset.edition.work.language = "zh-CN"
    asset.edition.work.knowledge_relations.filter.return_value.select_related.return_value = []
    asset.edition.active_catalog_revision = SimpleNamespace(
        pk="catalog-1", edition_id=asset.edition_id, reader_asset_id=asset.pk,
        status="active", metadata_ready=True, fulltext_ready=True, provenance={},
        snapshot={
            "work": {"id": "work-1", "title": "正式作品", "document_type": "book", "language": "zh-CN"},
            "edition": {"public_slug": "example", "publication_year": 2026},
            "contributions": [{"name": "正式作者"}],
        },
    )
    page = Mock()
    page.passages.all.return_value = list(passages)
    asset.pages.prefetch_related.return_value.all.return_value = [page] if passages else []
    return asset


@override_settings(MEILISEARCH_URL="http://meilisearch:7700")
def test_index_asset_removes_stale_documents_after_upsert():
    passage = Mock()
    passage.id = "passage-1"
    passage.page.index = 7
    passage.page.printed_label = "3"
    passage.text = "当前文字"
    passage.bbox_union = [0, 0, 1, 1]
    asset = _asset_with_passages(passage)

    with (
        patch("ingestion.services.indexing.ensure_passage_index"),
        patch(
            "ingestion.services.indexing.httpx.post",
            return_value=_response({"taskUid": 4}),
        ) as posted,
        patch(
            "ingestion.services.indexing._wait_task",
            return_value={"status": "succeeded"},
        ),
        patch(
            "ingestion.services.indexing._remove_stale_asset_documents",
            return_value=4,
        ) as remove_stale,
    ):
        result = index_asset(asset, is_public=True)

    assert result["backend"] == "meilisearch"
    assert result["documents"] == 1
    assert result["removed_stale_documents"] == 4
    remove_stale.assert_called_once_with("asset-1", {"catalog-1_passage-1"}, catalog_revision_id="catalog-1")
    document = posted.call_args.kwargs["json"][0]
    assert document["catalog_revision_id"] == "catalog-1"
    assert document["title"] == "正式作品"
    assert document["authors"] == ["正式作者"]


@override_settings(MEILISEARCH_URL="http://meilisearch:7700")
def test_index_asset_cleans_old_documents_when_source_has_no_passages():
    asset = _asset_with_passages()
    with (
        patch("ingestion.services.indexing.ensure_passage_index"),
        patch(
            "ingestion.services.indexing._remove_stale_asset_documents",
            return_value=3,
        ) as remove_stale,
    ):
        result = index_asset(asset, is_public=True)

    assert result == {
        "backend": "no-passages",
        "documents": 0,
        "removed_stale_documents": 3,
    }
    remove_stale.assert_called_once_with("asset-1", set(), catalog_revision_id="catalog-1")


@pytest.mark.parametrize("invalid", ["none", "cross_edition", "metadata_pending", "wrong_reader", "no_fulltext", "withdrawn"])
def test_index_asset_requires_owned_ready_publication_before_any_index_mutation(invalid):
    asset = _asset_with_passages()
    revision = asset.edition.active_catalog_revision
    if invalid == "none":
        asset.edition.active_catalog_revision = None
    elif invalid == "cross_edition":
        revision.edition_id = "different-edition"
    elif invalid == "metadata_pending":
        revision.metadata_ready = False
    elif invalid == "wrong_reader":
        revision.reader_asset_id = "different-asset"
    elif invalid == "no_fulltext":
        revision.fulltext_ready = False
    elif invalid == "withdrawn":
        asset.edition.state = "withdrawn"
    with (
        patch("ingestion.services.indexing.ensure_passage_index") as ensure,
        patch("ingestion.services.indexing._remove_stale_asset_documents") as remove_stale,
        patch("ingestion.services.indexing.httpx.post") as posted,
    ):
        result = index_asset(asset, is_public=True)
    assert result["backend"] == "staging-only"
    ensure.assert_not_called()
    remove_stale.assert_not_called()
    posted.assert_not_called()


def test_preparing_index_revision_only_updates_its_own_namespace():
    passage = SimpleNamespace(
        id="pending-passage", page=SimpleNamespace(index=1, printed_label="i"),
        text="新修订原文", bbox_union=[],
    )
    asset = _asset_with_passages(passage)
    active = asset.edition.active_catalog_revision
    pending = SimpleNamespace(**vars(active))
    pending.pk = "catalog-2"
    pending.status = "preparing"
    pending.fulltext_ready = False
    pending.provenance = {"requested_fulltext_ready": True}
    with (
        patch("ingestion.services.indexing.ensure_passage_index"),
        patch("ingestion.services.indexing.httpx.post", return_value=_response({"taskUid": 9})) as posted,
        patch("ingestion.services.indexing._wait_task", return_value={"status": "succeeded"}),
        patch("ingestion.services.indexing._remove_stale_asset_documents", return_value=0) as cleanup,
    ):
        result = index_asset(asset, catalog_revision=pending)
    assert result["backend"] == "meilisearch"
    assert posted.call_args.kwargs["json"][0]["id"] == "catalog-2_pending-passage"
    cleanup.assert_called_once_with("asset-1", {"catalog-2_pending-passage"}, catalog_revision_id="catalog-2")
    assert asset.edition.active_catalog_revision is active
