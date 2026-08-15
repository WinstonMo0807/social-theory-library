from pathlib import Path
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

import fitz
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image

from catalog.models import (
    Asset,
    Concept,
    Contribution,
    CoverCandidate,
    DocumentType,
    Edition,
    Page,
    Passage,
    Person,
    PublicationState,
    SiteSetting,
    TheorySchool,
    Topic,
    Work,
    cover_candidate_upload_path,
)
from catalog.services.covers import generate_cover_candidates, select_cover_candidate
from catalog.services.semantic_chunks import build_semantic_chunks
from catalog.services.semantic_search import _rrf, current_semantic_runtime
from ingestion.models import AuditEvent, UploadBatch, UploadItem
from ingestion.services.ocr_provider import parse_pdf_with_ocr
from ingestion.services.publication import publication_preflight, publication_readiness, publish_edition
from ingestion.views import _locked_upload_items


def create_public_asset(title, sha256, *, document_type=DocumentType.BOOK):
    work = Work.objects.create(
        document_type=document_type,
        title=title,
        language="en",
    )
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        public_slug=f"slug-{sha256[:8]}",
        publication_year=2026,
    )
    Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.ORIGINAL,
        file=SimpleUploadedFile(
            f"original-{sha256}.pdf",
            b"%PDF-1.4\n%%EOF",
            content_type="application/pdf",
        ),
        sha256=sha256,
        status=Asset.Status.READY,
        page_count=1,
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=SimpleUploadedFile(
            f"normalized-{sha256}.pdf",
            b"%PDF-1.4\n%%EOF",
            content_type="application/pdf",
        ),
        sha256=sha256,
        status=Asset.Status.READY,
        page_count=1,
    )
    page = Page.objects.create(
        asset=asset,
        index=1,
        text_source=Page.TextSource.EMBEDDED,
        width=595,
        height=842,
        text="Class position shapes leisure consumption and visible status distinctions.",
        normalized_text="class position shapes leisure consumption and visible status distinctions.",
    )
    passage = Passage.objects.create(
        page=page,
        order=0,
        text=page.text,
        normalized_text=page.normalized_text,
        bbox_union=[70, 120, 510, 220],
    )
    return work, edition, asset, page, passage


@pytest.mark.django_db
def test_admin_recommendation_image_override_is_public_and_removable(
    api_client,
    admin_user,
    tmp_path,
    settings,
):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.PUBLIC_API_URL = "http://testserver"
    work, _edition, _asset, _page, _passage = create_public_asset(
        "人工推荐图例测试",
        "a" * 64,
        document_type=DocumentType.REPORT,
    )
    output = BytesIO()
    Image.new("RGB", (320, 180), color=(35, 35, 35)).save(output, format="PNG")
    upload = SimpleUploadedFile(
        "curated-visual.png",
        output.getvalue(),
        content_type="image/png",
    )

    api_client.force_authenticate(admin_user)
    missing_metadata = api_client.get(
        f"/api/catalog/admin/works/{work.id}/recommendation-image/?metadata=1",
    )
    assert missing_metadata.status_code == 200
    assert missing_metadata.data["available"] is False

    response = api_client.post(
        f"/api/catalog/admin/works/{work.id}/recommendation-image/",
        {"image": upload},
        format="multipart",
    )
    assert response.status_code == 200
    assert response.data["available"] is True
    assert response.data["source"] == "manual_or_generated"
    work.refresh_from_db()
    assert work.recommendation_image.name.startswith("public/recommendations/")
    stored_name = work.recommendation_image.name
    assert work.recommendation_image.storage.exists(stored_name)

    api_client.force_authenticate(None)
    works_response = api_client.get("/api/catalog/works/")
    serialized_work = next(
        item for item in works_response.data["results"] if item["id"] == str(work.id)
    )
    assert serialized_work["recommendation_image"] == (
        f"/api/catalog/works/{work.id}/recommendation-image/"
    )

    api_client.force_authenticate(admin_user)
    preview = api_client.get(
        f"/api/catalog/admin/works/{work.id}/recommendation-image/",
    )
    assert preview.status_code == 200
    assert preview["Cache-Control"] == "private, no-store"
    preview.close()

    api_client.force_authenticate(None)
    public = api_client.get(f"/api/catalog/works/{work.id}/recommendation-image/")
    assert public.status_code == 200
    public.close()

    api_client.force_authenticate(admin_user)
    removed = api_client.delete(
        f"/api/catalog/admin/works/{work.id}/recommendation-image/",
    )
    assert removed.status_code == 200
    assert removed.data["available"] is False
    assert not work.recommendation_image.storage.exists(stored_name)


@pytest.mark.django_db
def test_reader_note_groups_are_owned_grouped_and_limited_to_three(
    api_client,
    reader_user,
    admin_user,
):
    _work_a, _edition_a, asset_a, page_a, _passage_a = create_public_asset(
        "第一本笔记书",
        "1" * 64,
    )
    _work_b, _edition_b, asset_b, page_b, _passage_b = create_public_asset(
        "第二本笔记书",
        "2" * 64,
    )
    api_client.force_authenticate(reader_user)
    created_ids = []
    for index in range(4):
        response = api_client.post(
            "/api/reading/annotations/",
            {
                "asset": str(asset_a.id),
                "page": str(page_a.id),
                "kind": "note",
                "selector": {
                    "page_index": 1,
                    "exact": f"原文 {index}",
                    "bboxes": [[70, 120, 200, 140]],
                },
                "quote": f"原文 {index}",
                "body": f"笔记 {index}",
                "color": "yellow",
            },
            format="json",
        )
        assert response.status_code == 201
        created_ids.append(response.data["id"])
    response = api_client.post(
        "/api/reading/annotations/",
        {
            "asset": str(asset_b.id),
            "page": str(page_b.id),
            "kind": "note",
            "selector": {"page_index": 1, "bboxes": [[70, 120, 200, 140]]},
            "quote": "第二本原文",
            "body": "第二本笔记",
            "color": "yellow",
        },
        format="json",
    )
    assert response.status_code == 201

    grouped = api_client.get("/api/reading/annotations/note-groups/")
    assert grouped.status_code == 200
    assert grouped.data["count"] == 2
    first_book = next(
        item for item in grouped.data["results"] if item["asset"] == str(asset_a.id)
    )
    assert first_book["note_count"] == 4
    assert len(first_book["previews"]) == 3
    assert all(item["body_text"].startswith("笔记") for item in first_book["previews"])
    paged = api_client.get(
        "/api/reading/annotations/",
        {"asset": str(asset_a.id), "kind": "note", "p": 1},
    )
    assert paged.status_code == 200
    assert paged.data["count"] == 4
    page_filtered = api_client.get(
        "/api/reading/annotations/",
        {"asset": str(asset_a.id), "page": str(page_a.id), "kind": "note"},
    )
    assert page_filtered.status_code == 200
    assert page_filtered.data["count"] == 4

    deleted = api_client.delete(f"/api/reading/annotations/{created_ids[0]}/")
    assert deleted.status_code == 204
    api_client.force_authenticate(admin_user)
    assert api_client.get("/api/reading/annotations/note-groups/").data["results"] == []


@pytest.mark.django_db
def test_semantic_search_returns_public_passage_and_exact_focus(api_client):
    _work, edition, asset, _page, passage = create_public_asset(
        "The Theory of Visible Leisure",
        "3" * 64,
    )
    chunk = build_semantic_chunks(asset)[0]
    response = api_client.get(
        "/api/catalog/semantic-search/",
        {"q": "leisure class consumption and status"},
    )
    assert response.status_code == 200
    assert response.data["engine"] == "keyword_fallback"
    assert response.data["results"][0]["id"] == str(chunk.id)
    assert response.data["results"][0]["relevance"] == "高度相关"
    assert response.data["results"][0]["page_index"] == 1

    focus = api_client.get(f"/api/catalog/passages/{passage.id}/focus/")
    assert focus.status_code == 200
    assert focus.data["asset_id"] == str(asset.id)
    assert focus.data["bbox"] == [70, 120, 510, 220]

    semantic_focus = api_client.get(f"/api/catalog/passages/{chunk.id}/focus/")
    assert semantic_focus.status_code == 200
    assert semantic_focus.data["asset_id"] == str(asset.id)

    edition.state = PublicationState.WITHDRAWN
    edition.save(update_fields=["state", "updated_at"])
    assert api_client.get(f"/api/catalog/passages/{passage.id}/focus/").status_code == 404
    hidden = api_client.get(
        "/api/catalog/semantic-search/",
        {"q": "leisure class consumption and status"},
    )
    assert hidden.status_code == 200
    assert hidden.data["results"] == []


@pytest.mark.django_db
def test_admin_semantic_settings_do_not_expose_secret(
    api_client,
    admin_user,
    reader_user,
    settings,
):
    settings.SEMANTIC_EMBEDDING_API_KEY = "never-return-this-secret"
    payload = {
        "engine": "lightweight",
        "provider": "openAi",
        "embedder_name": "social-science-test",
        "model": "text-embedding-3-small",
        "service_url": "",
        "semantic_ratio": 0.72,
    }
    api_client.force_authenticate(reader_user)
    assert api_client.put(
        "/api/catalog/admin/semantic-runtime/",
        payload,
        format="json",
    ).status_code == 403

    api_client.force_authenticate(admin_user)
    response = api_client.put(
        "/api/catalog/admin/semantic-runtime/",
        payload,
        format="json",
    )
    assert response.status_code == 200
    assert response.data["engine"] == "lightweight"
    assert response.data["semantic_ratio"] == pytest.approx(0.72)
    assert current_semantic_runtime()["semantic_ratio"] == pytest.approx(0.72)
    assert response.data["api_key_configured"] is True
    assert "never-return-this-secret" not in str(response.data)

    unsupported = api_client.put(
        "/api/catalog/admin/semantic-runtime/",
        {**payload, "reranker": "qwen-name-without-consumer"},
        format="json",
    )
    assert unsupported.status_code == 400
    assert "只支持已接入并可验证" in str(unsupported.data)


def test_semantic_ratio_changes_keyword_and_vector_fusion_weights():
    keyword_first = SimpleNamespace(id="keyword-first")
    vector_first = SimpleNamespace(id="vector-first")
    keyword_rows = [(keyword_first, 1.0), (vector_first, 0.8)]
    vector_rows = [("vector-first", 0.95), ("keyword-first", 0.7)]

    semantic_heavy = {
        str(row["chunk"].id): row["rrf"]
        for row in _rrf(keyword_rows, vector_rows, semantic_ratio=0.72)
    }
    keyword_heavy = {
        str(row["chunk"].id): row["rrf"]
        for row in _rrf(keyword_rows, vector_rows, semantic_ratio=0.28)
    }

    assert semantic_heavy["vector-first"] > semantic_heavy["keyword-first"]
    assert keyword_heavy["keyword-first"] > keyword_heavy["vector-first"]


@pytest.mark.django_db
def test_ocr_prefers_nas_and_can_fall_back_to_remote(tmp_path, settings):
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-1.4")
    settings.PADDLEOCR_SERVICE_URL = "http://paddleocr:8010"
    settings.OCR_REMOTE_API_URL = "https://ocr.example.org"
    settings.OCR_REMOTE_API_KEY = "secret"
    settings.OCR_REMOTE_MODEL = "remote-layout-model"

    with patch(
        "ingestion.services.ocr_provider._request_document_gateway",
        return_value={"pages": [{"index": 1, "text": "NAS"}]},
    ) as requested:
        payload, provider = parse_pdf_with_ocr(source)
    assert provider == "paddleocr_nas"
    assert payload["pages"][0]["text"] == "NAS"
    assert requested.call_count == 1
    assert requested.call_args.kwargs["base_url"] == "http://paddleocr:8010"

    calls = []

    def fail_then_succeed(_path, **kwargs):
        calls.append(kwargs["base_url"])
        if len(calls) == 1:
            raise ValueError("local unavailable")
        return {"pages": [{"index": 1, "text": "REMOTE"}]}

    with patch(
        "ingestion.services.ocr_provider._request_document_gateway",
        side_effect=fail_then_succeed,
    ):
        payload, provider = parse_pdf_with_ocr(source)
    assert provider == "remote_ocr"
    assert payload["pages"][0]["text"] == "REMOTE"
    assert calls == ["http://paddleocr:8010", "https://ocr.example.org"]


def build_cover_pdf():
    document = fitz.open()
    copyright_page = document.new_page(width=595, height=842)
    copyright_page.insert_textbox(
        fitz.Rect(70, 90, 520, 700),
        "Copyright\nReferences\nISBN\nAll rights reserved",
        fontsize=11,
    )
    cover_page = document.new_page(width=595, height=842)
    cover_page.insert_textbox(
        fitz.Rect(65, 170, 530, 620),
        "THE SOCIAL TEST BOOK\n\nTest Scholar",
        fontsize=28,
        align=1,
    )
    contents_page = document.new_page(width=595, height=842)
    contents_page.insert_textbox(
        fitz.Rect(65, 80, 530, 750),
        "Contents\nChapter One\nChapter Two\nBibliography",
        fontsize=12,
    )
    payload = document.tobytes()
    document.close()
    return payload


@pytest.mark.django_db
def test_cover_candidates_only_run_for_books_and_allow_manual_selection(
    api_client,
    tmp_path,
    settings,
):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.COVER_AUTO_SELECT_THRESHOLD = 1.1
    work = Work.objects.create(
        document_type=DocumentType.BOOK,
        title="The Social Test Book",
        language="en",
    )
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        public_slug="social-test-cover",
    )
    person = Person.objects.create(preferred_name="Test Scholar")
    Contribution.objects.create(
        edition=edition,
        person=person,
        role=Contribution.Role.AUTHOR,
        approved=True,
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=SimpleUploadedFile(
            "book.pdf",
            build_cover_pdf(),
            content_type="application/pdf",
        ),
        sha256="4" * 64,
        status=Asset.Status.READY,
        page_count=3,
    )
    candidates = generate_cover_candidates(asset)
    assert len(candidates) == 3
    assert candidates[0].page_index == 2
    assert candidates[0].metrics["title_similarity"] >= 0.7
    assert candidates[0].thumbnail.name.startswith("incoming/cover-candidates/")
    selected = select_cover_candidate(candidates[0])["candidate"]
    work.refresh_from_db()
    assert selected.selected is True
    assert work.cover.name.startswith("public/covers/")
    assert work.cover.name.endswith("-cover.jpg")
    works_response = api_client.get("/api/catalog/works/")
    assert works_response.status_code == 200
    serialized_work = next(
        item for item in works_response.data["results"] if item["id"] == str(work.id)
    )
    assert serialized_work["cover"] == f"/api/catalog/works/{work.id}/cover/"
    assert "localhost:8000" not in serialized_work["cover"]
    public_cover = api_client.get(f"/api/catalog/works/{work.id}/cover/")
    assert public_cover.status_code == 200
    assert public_cover["Cache-Control"] == "public, max-age=86400"
    assert b"".join(public_cover.streaming_content)
    public_cover.close()

    article, _edition, article_asset, _page, _passage = create_public_asset(
        "Article without cover detection",
        "5" * 64,
        document_type=DocumentType.JOURNAL_ARTICLE,
    )
    assert generate_cover_candidates(article_asset) == []
    assert not CoverCandidate.objects.filter(work=article).exists()


@pytest.mark.django_db
def test_cover_candidate_preview_is_staff_only_and_missing_file_is_recoverable(
    api_client,
    admin_user,
    reader_user,
    tmp_path,
    settings,
):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.COVER_AUTO_SELECT_THRESHOLD = 1.1
    work = Work.objects.create(
        document_type=DocumentType.BOOK,
        title="The Shared Cover Test Book",
        language="en",
    )
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.READY,
        public_slug="shared-cover-test",
    )
    person = Person.objects.create(preferred_name="Shared Cover Scholar")
    Contribution.objects.create(
        edition=edition,
        person=person,
        role=Contribution.Role.AUTHOR,
        approved=True,
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=SimpleUploadedFile(
            "shared-cover-book.pdf",
            build_cover_pdf(),
            content_type="application/pdf",
        ),
        sha256="7" * 64,
        status=Asset.Status.READY,
        page_count=3,
    )
    candidate = generate_cover_candidates(asset)[0]
    preview_url = (
        f"/api/catalog/admin/works/{work.id}/cover-candidates/"
        f"{candidate.id}/thumbnail/"
    )

    api_client.force_authenticate(reader_user)
    assert api_client.get(preview_url).status_code == 403

    api_client.force_authenticate(admin_user)
    preview = api_client.get(preview_url)
    assert preview.status_code == 200
    assert preview["Content-Type"] == "image/jpeg"
    assert b"".join(preview.streaming_content)
    preview.close()

    Path(candidate.thumbnail.path).unlink()
    api_client.raise_request_exception = False
    selected = api_client.post(
        f"/api/catalog/admin/works/{work.id}/cover-candidates/{candidate.id}/select/"
    )
    assert selected.status_code == 409
    assert "重新分析" in selected.data["detail"]
    candidate.refresh_from_db()
    work.refresh_from_db()
    assert candidate.selected is False
    assert not work.cover


def test_generated_media_uses_existing_shared_storage_roots():
    assert Work._meta.get_field("cover").upload_to == "public/covers/%Y/%m/"
    assert Person._meta.get_field("portrait").upload_to == "public/people/%Y/%m/"
    assert (
        TheorySchool._meta.get_field("hero_image").upload_to
        == "public/knowledge/%Y/%m/"
    )
    assert Topic._meta.get_field("hero_image").upload_to == "public/knowledge/%Y/%m/"
    assert Concept._meta.get_field("hero_image").upload_to == "public/knowledge/%Y/%m/"
    target = type(
        "CandidatePath",
        (),
        {"work_id": "work-id", "asset_id": "asset-id"},
    )()
    assert cover_candidate_upload_path(target, "page-2.jpg") == (
        "incoming/cover-candidates/work-id/asset-id/page-2.jpg"
    )


def test_upload_item_row_lock_targets_only_the_primary_table():
    query = _locked_upload_items("edition__work", "batch").query
    assert query.select_for_update is True
    assert query.select_for_update_of == ("self",)


@pytest.mark.django_db
def test_publication_allows_empty_authors_theory_schools_and_topics(settings):
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = False
    work, edition, _asset, _page, _passage = create_public_asset(
        "A Work Without Assigned School",
        "8" * 64,
    )
    edition.state = PublicationState.READY
    edition.publisher = "Independent Press"
    edition.metadata_confidence = 1
    edition.canonical_filename = "佚名_2026_A Work Without Assigned School.pdf"
    edition.citation_data = {
        "type": "book",
        "title": work.title,
        "author": [],
        "issued": {"date-parts": [[2026]]},
        "publisher": edition.publisher,
    }
    edition.search_indexed_at = timezone.now()
    edition.save()

    assert not edition.contributions.exists()
    assert not work.knowledge_relations.exists()
    assert publication_readiness(edition) == []

    publish_edition(edition, confirm_warnings=True)
    edition.refresh_from_db()
    assert edition.state == PublicationState.PUBLISHED


@pytest.mark.django_db
def test_manual_publication_can_accept_low_metadata_confidence(settings):
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = False
    settings.AUTO_PUBLISH_MIN_CONFIDENCE = 0.85
    work, edition, _asset, _page, _passage = create_public_asset(
        "A Manually Reviewed Work",
        "9" * 64,
    )
    edition.state = PublicationState.READY
    edition.publisher = "Independent Press"
    edition.metadata_confidence = 0.42
    edition.canonical_filename = "A Manually Reviewed Work.pdf"
    edition.citation_data = {
        "type": "book",
        "title": work.title,
        "issued": {"date-parts": [[2026]]},
        "publisher": edition.publisher,
    }
    edition.search_indexed_at = timezone.now()
    edition.save()

    assert publication_readiness(edition) == []
    assert "元数据置信度低于自动处理阈值" in publication_preflight(edition)["warnings"]

    publish_edition(edition, allow_low_confidence=True, confirm_warnings=True)
    edition.refresh_from_db()
    assert edition.state == PublicationState.PUBLISHED


@pytest.mark.django_db(transaction=True)
def test_published_metadata_edit_stays_published_and_reindexes(
    api_client,
    admin_user,
    django_capture_on_commit_callbacks,
):
    work, edition, asset, _page, _passage = create_public_asset(
        "Published title before edit",
        "6" * 64,
    )
    batch = UploadBatch.objects.create(
        created_by=admin_user,
        status=UploadBatch.Status.COMPLETED,
        expected_count=1,
        completed_count=1,
    )
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="published.pdf",
        status=UploadItem.Status.PUBLISHED,
        stage_progress=100,
        edition=edition,
        asset=asset,
    )
    api_client.force_authenticate(admin_user)
    with patch("ingestion.views.index_asset") as reindex, patch(
        "ingestion.views.generate_cover_candidates",
    ):
        with django_capture_on_commit_callbacks(execute=True):
            response = api_client.put(
                f"/api/ingestion/items/{item.id}/review/",
                {
                    "title": "Published title after edit",
                    "subtitle": "",
                    "document_type": "book",
                    "language": "en",
                    "publication_year": 2026,
                    "publisher": "Test Press",
                    "publication_place": "London",
                    "journal_title": "",
                    "volume": "",
                    "issue": "",
                    "page_range": "",
                    "degree_institution": "",
                    "degree_type": "",
                    "report_institution": "",
                    "isbn": "",
                    "doi": "",
                    "abstract": "Updated without taking the item offline.",
                    "authors": [],
                    "author_ids": [],
                    "theory_schools": [],
                    "theory_school_ids": [],
                    "topics": [],
                    "topic_ids": [],
                    "lock_fields": ["title"],
                    "retry_publication": True,
                },
                format="json",
            )
    assert response.status_code == 200
    item.refresh_from_db()
    edition.refresh_from_db()
    work.refresh_from_db()
    assert item.status == UploadItem.Status.PUBLISHED
    assert edition.state == PublicationState.PUBLISHED
    assert work.title == "Published title after edit"
    assert edition.citation_data["author"] == []
    assert edition.canonical_filename.startswith("佚名_")
    assert not edition.contributions.exists()
    assert not work.knowledge_relations.exists()
    reindex.assert_called_once()
    assert reindex.call_args.kwargs["is_public"] is True
    assert AuditEvent.objects.filter(action="published_metadata_edit").exists()
