from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.models import (
    Asset,
    DocumentType,
    Edition,
    PublicationState,
    SemanticChunk,
    SemanticSearchFeedback,
    Work,
)
from catalog.services.semantic_reranker import rerank_candidates
from catalog.services.semantic_search import (
    _meili_filters,
    _vector_candidates,
    semantic_search,
    viewer_access_statuses,
)
from catalog.services.semantic_search_v2 import analyze_query


def _chunk(
    title: str,
    text: str,
    *,
    order: int,
    access_status: str = Asset.AccessStatus.PUBLIC,
) -> SemanticChunk:
    work = Work.objects.create(
        document_type=DocumentType.BOOK,
        title=title,
        language="zh-CN",
    )
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        is_primary=True,
        public_slug=f"v2-{order}",
        publication_year=2020 + order,
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=SimpleUploadedFile(f"v2-{order}.pdf", b"%PDF-1.4\n%%EOF"),
        sha256=f"{order:064x}",
        status=Asset.Status.READY,
        is_current=True,
        access_status=access_status,
    )
    return SemanticChunk.objects.create(
        asset=asset,
        work=work,
        order=0,
        page_start=order,
        page_end=order,
        chapter_title="农业组织的发展",
        section_title="制度安排",
        original_text=text,
        normalized_text=text,
        context_before="前文讨论小农户进入市场的困难。",
        context_after="后文进一步比较合作组织的条件。",
        language="zh-CN",
        document_type=DocumentType.BOOK,
        parser_version="test",
        chunk_version="test",
        document_id=sha256(f"locator-{order}".encode()).hexdigest(),
        content_hash=sha256(text.encode()).hexdigest(),
        locators=[{"page": order, "printed_label": str(order - 2), "bbox": []}],
        quality_flags=[],
        index_status=SemanticChunk.IndexStatus.READY,
    )


@pytest.mark.django_db
def test_v2_query_analysis_keeps_original_and_identifies_path_question():
    result = analyze_query("农业化组织的出路是什么？", expansion_limit=3)

    assert result["intent"] == "path_solution"
    assert result["rewrites"][0] == "农业化组织的出路是什么？"
    assert len(result["rewrites"]) <= 4
    assert any("发展路径" in value for value in result["rewrites"][1:])


def test_local_reranker_uses_bounded_candidate_contract(settings):
    settings.SEMANTIC_SEARCH_V2_RERANK_PROVIDER = "local_http"
    settings.SEMANTIC_SEARCH_V2_RERANK_URL = "http://reranker:8080/rerank"
    settings.SEMANTIC_SEARCH_V2_RERANK_ALLOWED_HOSTS = "reranker"
    settings.SEMANTIC_SEARCH_V2_RERANK_MODEL = "local-test-reranker"
    rows = [
        {
            "chunk": SimpleNamespace(
                asset=SimpleNamespace(
                    edition=SimpleNamespace(work=SimpleNamespace(title=f"书 {index}"))
                ),
                chapter_title="章",
                section_title="节",
                context_before="前文",
                original_text=f"候选 {index}",
                context_after="后文",
            )
        }
        for index in range(3)
    ]
    response = SimpleNamespace(
        status_code=200,
        content=b"{}",
        raise_for_status=lambda: None,
        json=lambda: {
            "results": [
                {"index": 2, "relevance_score": 0.8},
                {"index": 0, "relevance_score": 0.5},
            ]
        },
    )

    with patch("catalog.services.semantic_reranker.httpx.post", return_value=response) as called:
        result = rerank_candidates("哪个候选回应问题", rows, top_k=3)

    assert result["applied"] is True
    assert result["rows"][0] is rows[2]
    request = called.call_args.kwargs
    assert request["json"]["query"] == "哪个候选回应问题"
    assert request["json"]["model"] == "local-test-reranker"
    assert len(request["json"]["documents"]) == 3
    assert "Authorization" not in request["headers"]


@pytest.mark.django_db
def test_v2_fuses_candidates_and_returns_non_probability_labels(settings):
    first = _chunk(
        "合作组织研究",
        "农业组织发展的关键在于建立农户利益联结机制，并形成稳定的制度安排。",
        order=3,
    )
    second = _chunk(
        "农业史",
        "农业合作组织在二十世纪经历了快速发展。",
        order=4,
    )
    Work.objects.filter(pk__in=[first.work_id, second.work_id]).update(
        cover="public/covers/opinion-search-test.jpg"
    )
    settings.SEMANTIC_SEARCH_PROVIDER = "openAi"
    settings.SEMANTIC_SEARCH_V2_RERANK_PROVIDER = "rules"

    with (
        patch(
            "catalog.services.semantic_search_v2._meili_sparse_candidates",
            return_value=[(str(first.id), 0.9), (str(second.id), 0.8)],
        ),
        patch(
            "catalog.services.semantic_search_v2._meili_dense_candidates",
            return_value=[(str(second.id), 0.95), (str(first.id), 0.9)],
        ),
    ):
        result = semantic_search(
            "农业组织的出路是什么？",
            search_version="v2",
            search_profile="precision",
            filters={"_allowed_access_statuses": viewer_access_statuses()},
            debug=True,
        )

    assert result["search_version"] == "v2"
    assert result["engine"] == "v2_hybrid"
    assert result["results"][0]["response_label"] in {
        "可能回应",
        "相关论述",
        "语义近似",
        "背景材料",
    }
    assert "%" not in result["results"][0]["response_label"]
    assert result["stage_timings_ms"]["rrf_ms"] >= 0
    assert result["candidate_counts"]["fusion_candidate_count"] == 2
    assert result["results"][0]["printed_label"] in {"1", "2"}
    assert all(
        item["cover_url"] == f"/api/catalog/works/{item['work_id']}/cover/"
        for item in result["results"]
    )


@pytest.mark.django_db
def test_v2_never_serializes_registered_text_for_anonymous_reader(settings):
    public = _chunk("公开馆藏", "农业组织需要稳定制度。", order=5)
    registered = _chunk(
        "登录馆藏",
        "农业组织的关键在于利益联结。",
        order=6,
        access_status=Asset.AccessStatus.REGISTERED,
    )
    settings.SEMANTIC_SEARCH_PROVIDER = "openAi"

    with (
        patch(
            "catalog.services.semantic_search_v2._meili_sparse_candidates",
            return_value=[(str(registered.id), 0.99), (str(public.id), 0.6)],
        ),
        patch(
            "catalog.services.semantic_search_v2._meili_dense_candidates",
            return_value=[(str(registered.id), 0.99), (str(public.id), 0.6)],
        ),
    ):
        result = semantic_search(
            "农业组织如何发展",
            search_version="v2",
            filters={"_allowed_access_statuses": viewer_access_statuses()},
        )

    assert [item["id"] for item in result["results"]] == [str(public.id)]


def test_meilisearch_filter_applies_reader_access_before_top_k():
    anonymous = " AND ".join(
        _meili_filters({"_allowed_access_statuses": viewer_access_statuses()})
    )
    reader = " AND ".join(
        _meili_filters(
            {
                "_allowed_access_statuses": viewer_access_statuses(
                    authenticated=True,
                )
            }
        )
    )

    assert 'access_status IN ["inherit", "public"]' in anonymous
    assert '"registered"' not in anonymous
    assert '"registered"' in reader


def test_v1_retries_public_only_filter_for_legacy_active_index(settings):
    settings.MEILISEARCH_URL = "http://meilisearch:7700"
    request = httpx.Request(
        "POST",
        "http://meilisearch:7700/indexes/legacy-index/search",
    )
    missing_filter = httpx.Response(
        400,
        request=request,
        json={
            "code": "invalid_search_filter",
            "message": "Attribute `access_status` is not filterable.",
        },
    )
    success = httpx.Response(
        200,
        request=request,
        json={"hits": [{"id": "chunk-1", "_rankingScore": 0.83}]},
    )

    with patch(
        "catalog.services.semantic_search.httpx.post",
        side_effect=[missing_filter, success],
    ) as called:
        rows = _vector_candidates(
            "国家",
            {"embedder_name": "social-science-library"},
            {"_allowed_access_statuses": viewer_access_statuses()},
            index_uid="legacy-index",
        )

    assert rows == [("chunk-1", 0.83)]
    assert called.call_count == 2
    first_filter = called.call_args_list[0].kwargs["json"]["filter"]
    retry_filter = called.call_args_list[1].kwargs["json"]["filter"]
    assert "access_status" in first_filter
    assert retry_filter == "is_public = true"


def test_v1_does_not_hide_unrelated_meilisearch_filter_errors(settings):
    settings.MEILISEARCH_URL = "http://meilisearch:7700"
    request = httpx.Request(
        "POST",
        "http://meilisearch:7700/indexes/legacy-index/search",
    )
    unrelated_error = httpx.Response(
        400,
        request=request,
        json={
            "code": "invalid_search_filter",
            "message": "Attribute `topic_slugs` is not filterable.",
        },
    )

    with patch(
        "catalog.services.semantic_search.httpx.post",
        return_value=unrelated_error,
    ) as called:
        with pytest.raises(httpx.HTTPStatusError):
            _vector_candidates(
                "国家",
                {"embedder_name": "social-science-library"},
                {},
                index_uid="legacy-index",
            )

    assert called.call_count == 1


@pytest.mark.django_db
def test_v2_reranker_failure_keeps_rrf_results(settings):
    chunk = _chunk("路径研究", "农业组织应当建立利益联结机制。", order=7)
    settings.SEMANTIC_SEARCH_PROVIDER = "openAi"
    settings.SEMANTIC_SEARCH_V2_RERANK_PROVIDER = "local_http"
    settings.SEMANTIC_SEARCH_V2_RERANK_URL = "http://reranker:8080/rerank"
    settings.SEMANTIC_SEARCH_V2_RERANK_ALLOWED_HOSTS = "reranker"

    with (
        patch(
            "catalog.services.semantic_search_v2._meili_sparse_candidates",
            return_value=[(str(chunk.id), 0.9)],
        ),
        patch(
            "catalog.services.semantic_search_v2._meili_dense_candidates",
            return_value=[(str(chunk.id), 0.9)],
        ),
        patch(
            "catalog.services.semantic_search_v2.rerank_candidates",
            side_effect=Exception("must be wrapped by test"),
        ),
    ):
        with pytest.raises(Exception, match="must be wrapped"):
            semantic_search("农业组织的出路", search_version="v2")

    from catalog.services.semantic_reranker import SemanticRerankerError

    with (
        patch(
            "catalog.services.semantic_search_v2._meili_sparse_candidates",
            return_value=[(str(chunk.id), 0.9)],
        ),
        patch(
            "catalog.services.semantic_search_v2._meili_dense_candidates",
            return_value=[(str(chunk.id), 0.9)],
        ),
        patch(
            "catalog.services.semantic_search_v2.rerank_candidates",
            side_effect=SemanticRerankerError("down"),
        ),
    ):
        result = semantic_search("农业组织的出路", search_version="v2")

    assert result["reranker_fallback"] is True
    assert result["results"][0]["id"] == str(chunk.id)


@pytest.mark.django_db
def test_v2_reports_empty_result_without_claiming_hybrid_success(settings):
    settings.SEMANTIC_SEARCH_PROVIDER = "openAi"
    with (
        patch(
            "catalog.services.semantic_search_v2._meili_sparse_candidates",
            return_value=[],
        ),
        patch(
            "catalog.services.semantic_search_v2._meili_dense_candidates",
            return_value=[],
        ),
        patch(
            "catalog.services.semantic_search_v2._passage_keyword_candidates",
            return_value=[],
        ),
    ):
        result = semantic_search("农业组织的出路", search_version="v2")

    assert result["engine"] == "v2_empty"
    assert result["results"] == []
    assert result["notice"] == "当前限定下没有找到可核对的馆藏原文。"


@pytest.mark.django_db
def test_v1_remains_default_when_v2_flag_is_disabled(settings):
    _chunk("原检索", "农业组织发展需要制度安排。", order=8)
    settings.SEMANTIC_SEARCH_V2_ENABLED = False
    settings.SEMANTIC_SEARCH_ENABLED = False

    result = semantic_search("农业组织发展")

    assert result["search_version"] == "v1"


@pytest.mark.django_db
def test_anonymous_feedback_replaces_same_session_vote(api_client):
    chunk = _chunk("反馈去重", "农业组织应当建立稳定的利益联结机制。", order=9)
    endpoint = "/api/catalog/semantic-search/feedback/"
    first = api_client.post(
        endpoint,
        {
            "query": "农业组织的出路是什么",
            "chunk_id": str(chunk.id),
            "relevant": True,
            "rank": 1,
        },
        format="json",
    )
    second = api_client.post(
        endpoint,
        {
            "query": "农业组织的出路是什么",
            "chunk_id": str(chunk.id),
            "relevant": False,
            "rank": 2,
        },
        format="json",
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.data["id"] == second.data["id"]
    assert SemanticSearchFeedback.objects.count() == 1
    saved = SemanticSearchFeedback.objects.get()
    assert saved.relevant is False
    assert saved.result_rank == 2
    assert saved.user_id is None
    assert saved.feedback_key


@pytest.mark.django_db
def test_authenticated_feedback_is_unique_per_reader(api_client, reader_user):
    chunk = _chunk("实名反馈去重", "合作组织需要兼顾市场效率与农户主体性。", order=10)
    api_client.force_authenticate(reader_user)
    endpoint = "/api/catalog/semantic-search/feedback/"
    for relevant in (False, True):
        response = api_client.post(
            endpoint,
            {
                "query": "合作组织如何发展",
                "chunk_id": str(chunk.id),
                "relevant": relevant,
                "rank": 1,
            },
            format="json",
        )
        assert response.status_code == 201

    assert SemanticSearchFeedback.objects.count() == 1
    saved = SemanticSearchFeedback.objects.get()
    assert saved.user_id == reader_user.id
    assert saved.relevant is True
