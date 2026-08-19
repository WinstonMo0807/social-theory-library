from unittest.mock import patch

import httpx
import pytest

from catalog.models import (
    Asset,
    DocumentType,
    Edition,
    Page,
    Passage,
    Person,
    PublicationPlaceEvidence,
    PublicationState,
    PublisherAuthority,
    ScholarProfile,
    SemanticChunk,
    SemanticIndexJob,
    SemanticIndexVersion,
    SemanticSearchFeedback,
    TheorySchool,
    Topic,
    Work,
)
from catalog.services.citations import format_gbt_7714_2025
from catalog.services.publication_places import (
    confirmed_publication_places,
    detect_publication_places,
    record_manual_publication_places,
)
from catalog.services.semantic_chunks import build_semantic_chunks
from catalog.services.semantic_indexing import create_semantic_job, run_semantic_index_job
from catalog.services.semantic_search import semantic_search
from catalog.services.search_backend import ExternalPassageSearch
from ingestion.models import MetadataCandidate, UploadBatch, UploadItem


def active_semantic_version(marker: str) -> SemanticIndexVersion:
    return SemanticIndexVersion.objects.create(
        uid=f"test-active-{marker}",
        provider="huggingFace",
        model_repo_id="example/model",
        status=SemanticIndexVersion.Status.ACTIVE,
    )


def create_asset(
    title: str,
    marker: str,
    *,
    document_type=DocumentType.BOOK,
    language="zh-CN",
    year=2026,
    publisher="",
    page_texts=None,
):
    work = Work.objects.create(document_type=document_type, title=title, language=language)
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        public_slug=f"v223-{marker}",
        publication_year=year,
        publisher=publisher,
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=f"public/{marker}.pdf",
        sha256=(marker * 64)[:64],
        status=Asset.Status.READY,
        page_count=len(page_texts or ["观点检索测试正文"]),
        extraction_method="embedded",
    )
    pages = []
    for index, text in enumerate(page_texts or ["观点检索测试正文"], start=1):
        page = Page.objects.create(
            asset=asset,
            index=index,
            printed_label=str(index),
            text_source=Page.TextSource.EMBEDDED,
            width=595,
            height=842,
            text=text,
            normalized_text=text.casefold(),
        )
        Passage.objects.create(
            page=page,
            order=0,
            text=text,
            normalized_text=text.casefold(),
            bbox_union=[60, 100, 530, 180],
        )
        pages.append(page)
    return work, edition, asset, pages


@pytest.mark.django_db
def test_document_search_returns_ranked_page_candidates(api_client):
    _work, _edition, asset, _pages = create_asset(
        "候选页测试",
        "a",
        page_texts=["组织依赖首先出现", "没有命中", "组织依赖再次出现"],
    )
    with patch("catalog.views.external_passage_ids", return_value=None):
        response = api_client.get(
            f"/api/catalog/assets/{asset.id}/search/",
            {"q": "组织依赖"},
        )
    assert response.status_code == 200
    assert [item["page_index"] for item in response.data["matches"]] == [1, 3]
    assert [item["rank"] for item in response.data["matches"]] == [1, 2]
    assert all(item["occurrence_count"] >= 1 for item in response.data["matches"])


@pytest.mark.django_db
def test_document_search_falls_back_when_external_index_is_empty(api_client):
    _work, _edition, asset, _pages = create_asset(
        "空外部索引回退测试",
        "aa",
        page_texts=["第一页没有命中", "industrial organization appears here"],
    )
    empty_external = ExternalPassageSearch(ids=[], estimated_total=0)
    with patch("catalog.views.external_passage_ids", return_value=empty_external):
        response = api_client.get(
            f"/api/catalog/assets/{asset.id}/search/",
            {"q": "industrial"},
        )
    assert response.status_code == 200
    assert [item["page_index"] for item in response.data["matches"]] == [2]
    assert response.data["matches"][0]["rank"] == 1


@pytest.mark.django_db
def test_semantic_search_filters_and_vector_failure_fallback(settings):
    _book, _book_edition, book_asset, _ = create_asset(
        "中文图书",
        "b",
        language="zh-CN",
        year=1998,
        page_texts=["农业现代化使农民更依赖合作组织和社会化服务。"],
    )
    _article, _article_edition, article_asset, _ = create_asset(
        "English article",
        "c",
        document_type=DocumentType.JOURNAL_ARTICLE,
        language="en",
        year=2024,
        page_texts=["Agricultural modernization can increase organizational dependence."],
    )
    build_semantic_chunks(book_asset)
    build_semantic_chunks(article_asset)
    settings.SEMANTIC_SEARCH_ENABLED = True
    request = httpx.Request("POST", "http://meilisearch:7700")
    with patch(
        "catalog.services.semantic_search._vector_candidates",
        side_effect=httpx.ConnectError("offline", request=request),
    ):
        result = semantic_search(
            "agricultural modernization organizational dependence",
            filters={
                "document_types": ["journal_article"],
                "languages": ["en"],
                "years": ["2020-now"],
            },
        )
    assert result["engine"] == "keyword_fallback"
    assert result["fallback_used"] is True
    assert {item["asset_id"] for item in result["results"]} == {str(article_asset.id)}


@pytest.mark.django_db
def test_semantic_search_uses_page_index_when_chunks_are_missing(settings, api_client):
    _work, _edition, asset, _ = create_asset(
        "旧馆藏页码回退",
        "old-page-fallback",
        page_texts=["农业现代化使农民更依赖合作组织和社会化服务。"],
    )
    settings.SEMANTIC_SEARCH_ENABLED = True
    request = httpx.Request("POST", "http://meilisearch:7700")
    with patch(
        "catalog.services.semantic_search._vector_candidates",
        side_effect=httpx.ConnectError("offline", request=request),
    ):
        result = semantic_search("农业现代化 组织依赖")
    assert result["engine"] == "keyword_fallback"
    assert result["fallback_used"] is True
    assert result["page_fallback_used"] is True
    assert result["results"][0]["asset_id"] == str(asset.id)
    assert result["results"][0]["page_index"] == 1
    assert result["results"][0]["id"].startswith("passage:")
    assert "page=1" in result["results"][0]["reader_url"]

    feedback = api_client.post(
        "/api/catalog/semantic-search/feedback/",
        {
            "query": "农业现代化 组织依赖",
            "chunk_id": result["results"][0]["id"],
            "relevant": True,
            "rank": 1,
        },
        format="json",
    )
    assert feedback.status_code == 201
    saved = SemanticSearchFeedback.objects.get(pk=feedback.data["id"])
    assert saved.chunk_id is None
    assert saved.metadata["passage_id"]


@pytest.mark.django_db
def test_semantic_search_reranker_and_query_rewrite_fail_safely(settings):
    _work, _edition, asset, _ = create_asset(
        "回退测试",
        "d",
        page_texts=["规训权力不仅压制行动，也参与主体的形成。"],
    )
    build_semantic_chunks(asset)
    settings.SEMANTIC_SEARCH_ENABLED = False
    with (
        patch("catalog.services.semantic_search.understand_query", side_effect=RuntimeError("rewrite unavailable")),
        patch("catalog.services.semantic_search._rule_rerank", side_effect=RuntimeError("reranker unavailable")),
    ):
        result = semantic_search("权力如何生产主体")
    assert result["results"]
    assert result["query_rewrite_fallback"] is True
    assert result["reranker_fallback"] is True


@pytest.mark.django_db
def test_semantic_search_deduplicates_and_limits_same_work(settings):
    _work, _edition, asset, _ = create_asset(
        "同书限额",
        "e",
        page_texts=[
            "组织依赖与农业现代化之间存在复杂关系。" * 12,
            "农业服务体系改变了农民进入市场的方式。" * 12,
            "合作社也可能重新安排农户的资源获取。" * 12,
        ],
    )
    build_semantic_chunks(asset)
    settings.SEMANTIC_SEARCH_ENABLED = False
    result = semantic_search("农业现代化组织依赖合作社市场", max_per_work=1)
    assert len(result["results"]) == 1
    assert result["results"][0]["reader_url"].startswith(f"/reader/{asset.id}?page=")


@pytest.mark.django_db
def test_semantic_search_interleaves_multiple_works_and_keeps_three_passages(settings):
    assets = []
    for marker, title in (("multi-a", "合作组织研究"), ("multi-b", "农业制度研究"), ("multi-c", "乡村市场研究")):
        _work, _edition, asset, _pages = create_asset(
            title,
            marker,
            page_texts=[
                "农业现代化改变了农民对合作组织和社会化服务的依赖。" * 4,
                "组织依赖也受到市场进入方式和公共服务供给的影响。" * 4,
                "合作社能够重新安排农民获取资源和参与市场的方式。" * 4,
            ],
        )
        assets.append(asset)
    settings.SEMANTIC_SEARCH_ENABLED = False

    result = semantic_search("农业现代化 农民 组织依赖 合作社 市场", limit=9, max_per_work=3)

    assert result["work_count"] == 3
    assert len(result["results"]) == 9
    assert len({row["work_id"] for row in result["results"][:3]}) == 3
    for asset in assets:
        rows = [row for row in result["results"] if row["asset_id"] == str(asset.id)]
        assert len(rows) == 3
        assert all(row["reader_url"].startswith(f"/reader/{asset.id}?page=") for row in rows)


@pytest.mark.django_db
def test_semantic_index_job_is_partial_when_vector_backend_fails(settings):
    _work, _edition, asset, _ = create_asset(
        "异步索引",
        "f",
        page_texts=["自然段分块应当保留原页位置和前后文。" * 15],
    )
    settings.SEMANTIC_SEARCH_ENABLED = True
    active_semantic_version("partial")
    job = create_semantic_job(asset)
    with patch(
        "catalog.services.semantic_indexing.index_semantic_asset",
        return_value={"backend": "database-fallback", "documents": 1, "warning": "vector offline"},
    ):
        completed = run_semantic_index_job(str(job.id))
    assert completed.status == SemanticIndexJob.Status.PARTIAL
    assert completed.progress == 100
    assert completed.attempts == 1
    assert completed.stats["chunks"] >= 1


@pytest.mark.django_db
def test_site_stats_are_dynamic_and_include_version(api_client):
    create_asset("动态统计", "g")
    person = Person.objects.create(preferred_name="测试学者")
    ScholarProfile.objects.create(person=person, slug="test-scholar", editorial_status="published")
    TheorySchool.objects.create(name="测试流派", slug="test-theory", editorial_status="published")
    Topic.objects.create(name="测试专题", slug="test-topic", editorial_status="published")
    response = api_client.get("/api/catalog/site-stats/")
    assert response.status_code == 200
    assert response.data["documents"] == 1
    assert response.data["scholars"] == 1
    assert response.data["knowledge_objects"] == 2
    assert response.data["version"] == "2.7.1"
    assert "年" in response.data["last_updated_label"]


@pytest.mark.django_db
def test_publication_place_direct_evidence_and_location_types():
    _work, edition, asset, _ = create_asset(
        "出版地证据",
        "h",
        year=2019,
        publisher="社会科学文献出版社",
        page_texts=[
            "图书在版编目（CIP）数据\n北京：社会科学文献出版社，2019\n"
            "发行地：上海\n印刷地：石家庄\n地址：北京市西城区某路"
        ],
    )
    rows = detect_publication_places(asset, force=True)
    publication = next(row for row in rows if row.place_type == "publication_place")
    assert publication.normalized_value == "北京"
    assert publication.verification_status == PublicationPlaceEvidence.VerificationStatus.AUTO_CONFIRMED
    assert publication.evidence_page == 1
    assert "北京：社会科学文献出版社，2019" in publication.evidence_text
    assert {row.place_type for row in rows} >= {"publication_place", "distribution_place", "printing_place"}
    edition.refresh_from_db()
    assert edition.publication_place == "北京"


@pytest.mark.django_db
def test_publisher_authority_is_only_a_suggestion():
    PublisherAuthority.objects.create(
        canonical_name="测试出版社",
        aliases=["Test Press"],
        possible_places=["北京"],
        country="中国",
    )
    _work, edition, asset, _ = create_asset(
        "规范库候选",
        "i",
        publisher="测试出版社",
        page_texts=["本页没有出版城市的直接书目证据。"],
    )
    rows = detect_publication_places(asset, force=True)
    candidate = next(row for row in rows if row.source_type == "publisher_authority")
    assert candidate.confidence <= 0.6
    assert candidate.verification_status == PublicationPlaceEvidence.VerificationStatus.NEEDS_REVIEW
    edition.refresh_from_db()
    assert edition.publication_place == ""


@pytest.mark.django_db
def test_isbn_candidates_keep_multiple_places_and_manual_value_survives(admin_user):
    _work, edition, asset, _ = create_asset(
        "多出版地",
        "j",
        year=2020,
        publisher="Academic Press",
        page_texts=["No explicit place of publication appears on this page."],
    )
    edition.isbn = "9780000000001"
    edition.save(update_fields=["isbn", "updated_at"])
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(batch=batch, source_filename="random.pdf", edition=edition, asset=asset)
    MetadataCandidate.objects.create(
        upload_item=item,
        field_name="publication_place",
        value=["London", "New York"],
        source="openlibrary",
        confidence=0.95,
    )
    rows = detect_publication_places(asset, force=True)
    assert {row.normalized_value for row in rows if row.place_type == "publication_place"} == {"London", "New York"}
    assert confirmed_publication_places(edition)[0] == "London"

    record_manual_publication_places(edition, "Cambridge", actor=admin_user, reason="current edition")
    detect_publication_places(asset, force=True)
    edition.refresh_from_db()
    assert edition.publication_place == "Cambridge"
    assert confirmed_publication_places(edition)[0] == "Cambridge"


@pytest.mark.django_db
def test_unknown_publication_place_uses_gbt_brackets():
    _work, edition, asset, _ = create_asset(
        "未知出版地",
        "k",
        year=2018,
        publisher="未知城市出版社",
        page_texts=["正文没有任何出版地信息。"],
    )
    rows = detect_publication_places(asset, force=True)
    assert any(row.verification_status == PublicationPlaceEvidence.VerificationStatus.UNKNOWN for row in rows)
    assert "[出版地不详]：未知城市出版社，2018" in format_gbt_7714_2025(edition)


@pytest.mark.django_db
def test_marc_264_indicator_distinguishes_publication_and_printing(admin_user):
    _work, edition, asset, _ = create_asset(
        "MARC 地点类型",
        "m",
        year=2022,
        publisher="University Press",
        page_texts=["No direct place evidence."],
    )
    edition.isbn = "9780000000002"
    edition.save(update_fields=["isbn", "updated_at"])
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(batch=batch, source_filename="marc.pdf", edition=edition, asset=asset)
    MetadataCandidate.objects.create(
        upload_item=item,
        field_name="publication_place",
        value="London",
        source="marc21",
        confidence=0.96,
        evidence={"field": "264", "indicator2": "1", "record_id": "record-1", "raw_text": "264 #1 $a London"},
    )
    MetadataCandidate.objects.create(
        upload_item=item,
        field_name="publication_place",
        value="Cambridge",
        source="marc21",
        confidence=0.96,
        evidence={"field": "264", "indicator2": "3", "record_id": "record-1", "raw_text": "264 #3 $a Cambridge"},
    )
    rows = detect_publication_places(asset, force=True)
    assert next(row for row in rows if row.normalized_value == "London").place_type == "publication_place"
    assert next(row for row in rows if row.normalized_value == "Cambridge").place_type == "printing_place"
    edition.refresh_from_db()
    assert edition.publication_place == "London"


@pytest.mark.django_db
def test_marc_260_and_264_publication_conflict_requires_review(admin_user):
    _work, edition, asset, _ = create_asset(
        "MARC 冲突",
        "n",
        year=2022,
        publisher="University Press",
        page_texts=["No direct place evidence."],
    )
    edition.isbn = "9780000000003"
    edition.save(update_fields=["isbn", "updated_at"])
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(batch=batch, source_filename="marc-conflict.pdf", edition=edition, asset=asset)
    for field, indicator, place in (("260", "", "London"), ("264", "1", "New York")):
        MetadataCandidate.objects.create(
            upload_item=item,
            field_name="publication_place",
            value=place,
            source="marc21",
            confidence=0.96,
            evidence={"field": field, "indicator2": indicator, "record_id": "record-2"},
        )
    rows = detect_publication_places(asset, force=True)
    relevant = [row for row in rows if row.place_type == "publication_place"]
    assert {row.normalized_value for row in relevant} == {"London", "New York"}
    assert all(row.verification_status == PublicationPlaceEvidence.VerificationStatus.NEEDS_REVIEW for row in relevant)
    edition.refresh_from_db()
    assert edition.publication_place == ""


@pytest.mark.django_db
def test_withdrawal_requests_semantic_index_cleanup(api_client, admin_user):
    _work, edition, asset, _ = create_asset("下架清理", "l")
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="withdraw.pdf",
        edition=edition,
        asset=asset,
        status=UploadItem.Status.PUBLISHED,
    )
    api_client.force_authenticate(admin_user)
    with (
        patch("ingestion.views.remove_asset_from_index"),
        patch("ingestion.views.remove_semantic_asset") as remove_semantic,
    ):
        response = api_client.post(
            f"/api/ingestion/items/{item.id}/withdraw/",
            {"reason": "test"},
            format="json",
        )
    assert response.status_code == 200
    remove_semantic.assert_called_once_with(str(asset.id))
    edition.refresh_from_db()
    assert edition.state == PublicationState.WITHDRAWN


@pytest.mark.django_db
def test_semantic_index_admin_summary_includes_feedback(api_client, admin_user):
    SemanticSearchFeedback.objects.create(
        user=admin_user,
        query_hash="a" * 64,
        query_text="国家与社会",
        relevant=True,
        result_rank=1,
    )
    SemanticSearchFeedback.objects.create(
        user=admin_user,
        query_hash="b" * 64,
        query_text="制度变迁",
        relevant=False,
        result_rank=2,
    )
    api_client.force_authenticate(admin_user)

    response = api_client.get("/api/catalog/admin/semantic-index/")

    assert response.status_code == 200
    assert response.data["feedback"] == {
        "total": 2,
        "relevant": 1,
        "not_relevant": 1,
    }
    assert "runtime" in response.data
    assert "documents" in response.data
