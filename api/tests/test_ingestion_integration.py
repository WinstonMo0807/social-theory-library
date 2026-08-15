from pathlib import Path
from unittest.mock import patch

import fitz
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.models import (
    Asset,
    Contribution,
    Discipline,
    Edition,
    OcrStatus,
    PublicationEvent,
    PublicationState,
    ScholarProfile,
    Subdiscipline,
    TheorySchool,
    Topic,
    WorkDisciplineRelation,
    WorkKnowledgeRelation,
    WorkSubdisciplineRelation,
)
from ingestion.models import UploadBatch, UploadItem
from ingestion.services.pipeline import resume_reviewed_item_publication, run_pipeline
from reading.models import Annotation


def build_test_pdf(path: Path, marker: str = "") -> bytes:
    document = fitz.open()
    for page_index in range(3):
        page = document.new_page(width=595, height=842)
        text = (
            "Test Sociology Work\n"
            "Test Scholar\n\n"
            + "Power identity surveillance discipline social theory and institutions. " * 18
            + f"\n{marker}"
            + f"\nPage {page_index + 1}"
        )
        page.insert_textbox(
            fitz.Rect(55, 55, 540, 780),
            text,
            fontsize=10,
            fontname="helv",
        )
    document.set_metadata(
        {
            "title": "Test Sociology Work",
            "author": "Test Scholar",
            "subject": "social theory",
        }
    )
    document.save(path)
    document.close()
    return path.read_bytes()


def build_scanned_test_pdf(path: Path) -> bytes:
    document = fitz.open()
    for _page_index in range(2):
        page = document.new_page(width=595, height=842)
        page.draw_rect(
            fitz.Rect(48, 48, 547, 794),
            color=(0.15, 0.15, 0.15),
            fill=(0.96, 0.96, 0.96),
            width=1,
        )
    document.save(path)
    document.close()
    return path.read_bytes()


def review_payload(**overrides):
    payload = {
        "title": "人工确认后的社会学著作",
        "subtitle": "",
        "document_type": "book",
        "language": "zh-CN",
        "publication_year": 2026,
        "publisher": "测试出版社",
        "publication_place": "北京",
        "journal_title": "",
        "volume": "",
        "issue": "",
        "page_range": "",
        "degree_institution": "",
        "degree_type": "",
        "report_institution": "",
        "isbn": "",
        "doi": "",
        "abstract": "人工复核内容必须独立于后台索引任务保存。",
        "authors": ["人工确认学者"],
        "theory_schools": ["人工确认流派"],
        "topics": ["人工确认主题"],
        "lock_fields": ["title", "authors", "theory_schools", "topics"],
        "retry_publication": True,
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db(transaction=True)
def test_manual_review_survives_queue_and_search_failures(
    api_client,
    admin_user,
    tmp_path,
    settings,
):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.NAS_ORIGINAL_ROOT = settings.MEDIA_ROOT / "originals"
    settings.NAS_PUBLIC_ROOT = settings.MEDIA_ROOT / "public"
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = False
    settings.ALLOW_LOCAL_PUBLIC_ASSET_ACCESS = True
    settings.REQUIRE_EXTERNAL_SEARCH = False
    source = tmp_path / "manual-review.pdf"
    payload = build_test_pdf(source, marker="manual review persistence")
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="unstructured-8293.pdf",
        file=SimpleUploadedFile(
            "unstructured-8293.pdf",
            payload,
            content_type="application/pdf",
        ),
    )
    run_pipeline(str(item.id))
    item.refresh_from_db()
    normalized = item.edition.assets.get(kind=Asset.Kind.NORMALIZED)
    item.edition.refresh_from_db()
    assert item.edition.ocr_status == OcrStatus.NOT_REQUIRED
    assert normalized.validation_details["ocr_required_page_indexes"] == []
    api_client.force_authenticate(admin_user)

    with patch("ingestion.services.dispatch._task_for_kind") as task_factory:
        task_factory.return_value.apply_async.side_effect = ConnectionError(
            "redis unavailable"
        )
        response = api_client.put(
            f"/api/ingestion/items/{item.id}/review/",
            review_payload(),
            format="json",
        )
    assert response.status_code == 200
    item.refresh_from_db()
    item.edition.refresh_from_db()
    item.edition.work.refresh_from_db()
    assert item.edition.work.title == "人工确认后的社会学著作"
    assert item.edition.metadata_confidence == 1
    assert item.edition.search_indexed_at is None
    assert item.error_code == "queue_unavailable"
    dispatch_attempt = item.attempts.get(stage="task_dispatch", status="failed")
    assert dispatch_attempt.output_summary["kind"] == UploadItem.DispatchKind.REVIEWED

    item.error_code = ""
    item.error_message = ""
    item.save(update_fields=["error_code", "error_message", "updated_at"])
    with patch(
        "ingestion.services.pipeline.index_asset",
        side_effect=ConnectionError("meilisearch unavailable"),
    ):
        with pytest.raises(ConnectionError):
            resume_reviewed_item_publication(str(item.id))
    item.refresh_from_db()
    item.edition.work.refresh_from_db()
    assert item.status == UploadItem.Status.FAILED
    assert item.error_code == "ConnectionError"
    assert item.edition.work.title == "人工确认后的社会学著作"
    assert item.edition.field_locks.filter(field_name="title").exists()


@pytest.mark.django_db(transaction=True)
def test_scanned_pdf_retry_reuses_immutable_assets_and_queues_background_ocr(
    admin_user,
    tmp_path,
    settings,
):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.NAS_ORIGINAL_ROOT = settings.MEDIA_ROOT / "originals"
    settings.NAS_PUBLIC_ROOT = settings.MEDIA_ROOT / "public"
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = False
    settings.REQUIRE_EXTERNAL_SEARCH = False
    source = tmp_path / "scanned-retry.pdf"
    payload = build_scanned_test_pdf(source)
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="scanned-retry.pdf",
        file=SimpleUploadedFile(
            "scanned-retry.pdf",
            payload,
            content_type="application/pdf",
        ),
    )

    with patch(
        "ingestion.services.pipeline.extract_native_pages",
        side_effect=RuntimeError("legacy OCR unavailable"),
    ):
        with pytest.raises(RuntimeError, match="legacy OCR unavailable"):
            run_pipeline(str(item.id))

    item.refresh_from_db()
    assert item.status == UploadItem.Status.FAILED
    original = item.edition.assets.get(kind=Asset.Kind.ORIGINAL)
    normalized = item.edition.assets.get(kind=Asset.Kind.NORMALIZED)
    assert original.status == Asset.Status.PROCESSING
    assert normalized.status == Asset.Status.PROCESSING
    immutable_asset_ids = set(item.edition.assets.values_list("id", flat=True))

    with patch("ingestion.services.pipeline.queue_ocr_job") as queued_ocr, patch(
        "ingestion.services.ocr_provider.parse_pdf_pages_with_ocr"
    ) as targeted_ocr:
        recovered = run_pipeline(str(item.id))

    recovered.edition.refresh_from_db()
    original.refresh_from_db()
    normalized.refresh_from_db()
    assert recovered.status == UploadItem.Status.READY
    assert set(recovered.edition.assets.values_list("id", flat=True)) == immutable_asset_ids
    assert original.status == Asset.Status.READY
    assert normalized.status == Asset.Status.READY
    assert normalized.page_count == 2
    assert normalized.pages.count() == 2
    assert normalized.extraction_method == "pending_ocr"
    assert normalized.validation_details["ocr_required_page_indexes"] == [1, 2]
    assert recovered.edition.ocr_status == OcrStatus.PENDING
    queued_ocr.assert_called_once()
    assert queued_ocr.call_args.args[0].id == normalized.id
    targeted_ocr.assert_not_called()
    publication_attempt = recovered.attempts.get(
        stage="publication_place_detection",
        status="completed",
    )
    assert publication_attempt.output_summary["targeted_ocr_deferred"] is True


@pytest.mark.django_db(transaction=True)
def test_single_pdf_links_catalog_search_reader_citation_and_withdrawal(
    api_client,
    admin_user,
    reader_user,
    tmp_path,
    settings,
):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.NAS_ORIGINAL_ROOT = settings.MEDIA_ROOT / "originals"
    settings.NAS_PUBLIC_ROOT = settings.MEDIA_ROOT / "public"
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = False
    settings.ALLOW_LOCAL_PUBLIC_ASSET_ACCESS = True
    settings.REQUIRE_EXTERNAL_SEARCH = False
    source = tmp_path / "test.pdf"
    payload = build_test_pdf(source)

    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="random-file-name-001.pdf",
        file=SimpleUploadedFile("random-file-name-001.pdf", payload, content_type="application/pdf"),
    )

    first_pass = run_pipeline(str(item.id))
    assert first_pass.status == UploadItem.Status.READY
    assert first_pass.edition_id
    assert first_pass.asset_id
    assert first_pass.edition.assets.filter(kind=Asset.Kind.NORMALIZED, page_count=3).exists()
    assert first_pass.edition.assets.get(kind=Asset.Kind.NORMALIZED).pages.count() == 3
    assert first_pass.attempts.filter(stage="text_extraction", status="completed").exists()

    api_client.force_authenticate(admin_user)
    preview = api_client.get(f"/api/ingestion/items/{item.id}/preview/")
    assert preview.status_code == 200
    assert preview["Content-Type"] == "application/pdf"
    # Transactional tests flush rows created by data migrations. Re-create the
    # stable core discipline here so this integration test is order independent.
    discipline, _ = Discipline.objects.get_or_create(
        code="sociology",
        defaults={
            "name": "社会学",
            "slug": "sociology",
            "foreign_name": "Sociology",
            "editorial_status": "published",
        },
    )
    subdiscipline = Subdiscipline.objects.create(
        discipline=discipline,
        name="测试子学科",
        slug="test-subdiscipline",
        editorial_status="published",
    )
    theory = TheorySchool.objects.create(
        name="测试理论",
        slug="test-theory",
        editorial_status="published",
    )
    topic = Topic.objects.create(
        name="测试主题",
        slug="test-topic",
        editorial_status="published",
    )
    review_response = api_client.put(
        f"/api/ingestion/items/{item.id}/review/",
        {
            "title": "测试社会学著作",
            "subtitle": "",
            "document_type": "book",
            "publication_year": 2026,
            "publisher": "测试出版社",
            "publication_place": "北京",
            "journal_title": "",
            "volume": "",
            "issue": "",
            "page_range": "",
            "degree_institution": "",
            "degree_type": "",
            "report_institution": "",
            "isbn": "",
            "doi": "",
            "abstract": "用于联动验收的测试文献。",
            "authors": ["测试学者"],
            "theory_schools": ["测试理论"],
            "theory_assignments": [{
                "id": str(theory.id),
                "role": "foundational",
                "strength": "high",
                "is_primary": True,
                "evidence_page": 2,
                "evidence_printed_label": "1",
                "evidence_text": "前言明确说明本书的理论贡献。",
            }],
            "topics": ["测试主题"],
            "topic_assignments": [{
                "id": str(topic.id),
                "is_primary": True,
                "evidence_page": 2,
                "evidence_text": "目录与前言显示该问题贯穿全书。",
            }],
            "discipline_assignments": [{
                "id": str(discipline.id),
                "is_primary": True,
                "evidence_page": 2,
                "evidence_text": "题名页和前言共同支持社会学归类。",
            }],
            "subdiscipline_assignments": [{
                "id": str(subdiscipline.id),
                "strength": "high",
                "is_primary": True,
                "evidence_page": 2,
                "evidence_text": "章节结构与该子学科的研究对象一致。",
            }],
            "lock_fields": [
                "title",
                "publication_year",
                "publisher",
                "publication_place",
            ],
            "retry_publication": False,
        },
        format="json",
    )
    assert review_response.status_code == 200
    assert review_response.data["review_data"]["language"] == "zh-CN"
    assert review_response.data["review_data"]["public_slug"] != "test-sociology-work"
    assert TheorySchool.objects.get(name="测试理论").editorial_status == "published"
    assert Topic.objects.get(name="测试主题").editorial_status == "published"
    item.refresh_from_db()
    work = item.edition.work
    theory_relation = WorkKnowledgeRelation.objects.get(
        work=work,
        theory_school=theory,
    )
    assert theory_relation.role == "foundational"
    assert theory_relation.strength == "high"
    assert theory_relation.evidence_page == 2
    assert theory_relation.review_status == "approved"
    assert WorkKnowledgeRelation.objects.get(work=work, topic=topic).evidence_page == 2
    assert WorkDisciplineRelation.objects.get(
        work=work,
        discipline=discipline,
    ).is_primary is True
    assert WorkSubdisciplineRelation.objects.get(
        work=work,
        subdiscipline=subdiscipline,
    ).strength == "high"
    assert not TheorySchool.objects.filter(
        editorial_status="published",
        workknowledgerelation__approved=False,
        workknowledgerelation__work=review_response.data["edition"],
    ).exists()

    scholar_profile = ScholarProfile.objects.get(person__preferred_name="测试学者")
    assert scholar_profile.editorial_status == "draft"
    # Simulate the existing, separate authority-publication decision. Metadata
    # review alone must not make a new scholar public.
    scholar_profile.editorial_status = "published"
    scholar_profile.save(update_fields=["editorial_status", "updated_at"])

    preflight_response = api_client.get(f"/api/ingestion/items/{item.id}/publish/")
    assert preflight_response.status_code == 200
    assert preflight_response.data["blockers"] == []
    publish_response = api_client.post(
        f"/api/ingestion/items/{item.id}/publish/",
        {"confirm_warnings": True},
        format="json",
    )
    assert publish_response.status_code == 200
    item.refresh_from_db()
    edition = Edition.objects.select_related("work").get(pk=item.edition_id)
    assert item.status == UploadItem.Status.PUBLISHED
    assert edition.state == PublicationState.PUBLISHED
    assert edition.work.title == "测试社会学著作"
    assert "测试学者_2026_测试社会学著作.pdf" == edition.canonical_filename

    title_search = api_client.get("/api/catalog/search/", {"q": "测试社会学著作"})
    assert title_search.status_code == 200
    assert title_search.data["counts"]["works"] == 1
    pinyin_title_search = api_client.get("/api/catalog/search/", {"q": "ceshishehuixuezhuzuo"})
    assert pinyin_title_search.data["counts"]["works"] == 1

    author_search = api_client.get("/api/catalog/search/", {"q": "测试学者"})
    assert author_search.data["counts"]["works"] == 1
    assert author_search.data["counts"]["scholars"] == 1
    pinyin_author_search = api_client.get("/api/catalog/search/", {"q": "ceshixuezhe"})
    assert pinyin_author_search.data["counts"]["scholars"] == 1

    fulltext_search = api_client.get("/api/catalog/search/", {"q": "power"})
    assert fulltext_search.data["counts"]["passages"] >= 1
    hit = fulltext_search.data["passages"][0]
    assert hit["page_index"] >= 1
    assert hit["asset_id"] == str(edition.assets.get(kind=Asset.Kind.NORMALIZED).id)
    author_id = str(
        edition.contributions.get(
            role=Contribution.Role.AUTHOR,
            approved=True,
        ).person_id
    )
    for field, value in (
        ("document_type", "book"),
        ("author", author_id),
        ("year", "2020-now"),
        ("language", edition.work.language),
        ("access", "online"),
    ):
        single_filter = api_client.get(
            "/api/catalog/search/",
            {"q": "power", "scope": "fulltext", field: value},
        )
        assert single_filter.data["counts"]["passages"] >= 1, field
    filtered_fulltext = api_client.get(
        "/api/catalog/search/",
        {
            "q": "power",
            "scope": "fulltext",
            "document_type": "book",
            "author": author_id,
            "year": "2020-now",
            "language": edition.work.language,
            "access": "online",
        },
    )
    assert filtered_fulltext.status_code == 200
    assert filtered_fulltext.data["pagination"]["total"] >= 1
    assert filtered_fulltext.data["counts"]["passages"] >= 1
    assert any(option["value"] == author_id for option in filtered_fulltext.data["facets"]["authors"])
    assert any(
        option["value"] == edition.work.language
        for option in filtered_fulltext.data["facets"]["languages"]
    )
    excluded_author = api_client.get(
        "/api/catalog/search/",
        {
            "q": "power",
            "scope": "fulltext",
            "author": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert excluded_author.data["counts"]["passages"] == 0

    school_response = api_client.get("/api/catalog/theory-schools/")
    school_row = next(row for row in school_response.data["results"] if row["name"] == "测试理论")
    assert school_row["work_count"] == 1
    school_search = api_client.get("/api/catalog/search/", {"q": "ceshililun"})
    assert school_search.data["counts"]["theories"] == 1
    school_detail = api_client.get(f"/api/catalog/theory-schools/{school_row['slug']}/")
    assert any(work["title"] == "测试社会学著作" for work in school_detail.data["works"])
    assert any(
        scholar["person"]["preferred_name"] == "测试学者"
        for scholar in school_detail.data["scholars"]
    )

    topic_response = api_client.get("/api/catalog/topics/")
    topic_row = next(row for row in topic_response.data["results"] if row["name"] == "测试主题")
    assert topic_row["work_count"] == 1
    topic_search = api_client.get("/api/catalog/search/", {"q": "ceshizhuti"})
    assert topic_search.data["counts"]["topics"] == 1
    topic_detail = api_client.get(f"/api/catalog/topics/{topic_row['slug']}/")
    assert any(work["title"] == "测试社会学著作" for work in topic_detail.data["works"])
    assert any(
        scholar["person"]["preferred_name"] == "测试学者"
        for scholar in topic_detail.data["scholars"]
    )
    filtered_schools = api_client.get(
        "/api/catalog/theory-schools/",
        {
            "theme": topic_row["slug"],
            "has_works": "true",
            "has_scholars": "true",
            "sort": "works",
        },
    )
    assert filtered_schools.status_code == 200
    assert [row["name"] for row in filtered_schools.data["results"]] == ["测试理论"]

    scholar_list = api_client.get("/api/catalog/scholars/")
    test_scholar = next(row for row in scholar_list.data["results"] if row["person"]["preferred_name"] == "测试学者")
    scholar_detail = api_client.get(f"/api/catalog/scholars/{test_scholar['slug']}/")
    assert scholar_detail.status_code == 200
    assert any(work["title"] == "测试社会学著作" for work in scholar_detail.data["works"])

    citation = api_client.get(f"/api/catalog/editions/{edition.id}/citations/", {"page": "12"})
    assert citation.status_code == 200
    assert "GB/T" not in citation.data["gbt7714-2025"]
    assert "测试学者" in citation.data["gbt7714-2025"]
    assert "12" in citation.data["gbt7714-2025"]

    asset = edition.assets.get(kind=Asset.Kind.NORMALIZED)
    manifest = api_client.get(f"/api/catalog/assets/{asset.id}/manifest/")
    assert manifest.status_code == 200
    assert manifest.data["work"]["title"] == "测试社会学著作"
    assert manifest.data["edition_id"] == str(edition.id)
    assert manifest.data["page_count"] == 3
    assert manifest.data["related_scholars"][0]["name"] == "测试学者"
    assert manifest.data["related_theories"][0]["name"] == "测试理论"
    assert manifest.data["related_topics"][0]["name"] == "测试主题"

    page_content = api_client.get(f"/api/catalog/assets/{asset.id}/pages/1/")
    assert page_content.status_code == 200
    assert page_content.data["width"] == 595
    assert page_content.data["height"] == 842
    assert page_content.data["blocks"]

    document_search = api_client.get(
        f"/api/catalog/assets/{asset.id}/search/",
        {"q": "power"},
    )
    assert document_search.status_code == 200
    assert document_search.data["matches"][0]["page_index"] == 1
    assert document_search.data["matches"][0]["width"] == 595
    assert document_search.data["matches"][0]["blocks"][0]["bbox"]
    precise_highlights = document_search.data["matches"][0]["highlights"]
    assert precise_highlights
    assert precise_highlights[0]["source"] == "pdf-text"
    block_bbox = document_search.data["matches"][0]["blocks"][0]["bbox"]
    highlight_bbox = precise_highlights[0]["bbox"]
    assert highlight_bbox[2] - highlight_bbox[0] < block_bbox[2] - block_bbox[0]
    assert highlight_bbox[3] - highlight_bbox[1] < block_bbox[3] - block_bbox[1]

    access = api_client.get(f"/api/distribution/assets/{asset.id}/access/")
    assert access.status_code == 200
    assert access.data["source"] == "local-nas"
    assert access.data["supports_range"] is True
    head_response = api_client.head(f"/api/distribution/assets/{asset.id}/file/")
    assert head_response.status_code == 200
    assert head_response["Content-Type"] == "application/pdf"
    assert head_response["Accept-Ranges"] == "bytes"
    assert head_response["Cache-Control"] == "public, max-age=300, must-revalidate, no-transform"
    assert head_response["ETag"] == f'"{asset.sha256}"'
    assert head_response["X-Content-Type-Options"] == "nosniff"
    assert int(head_response["Content-Length"]) > 5
    file_response = api_client.get(
        f"/api/distribution/assets/{asset.id}/file/",
        HTTP_RANGE="bytes=0-4",
    )
    assert file_response.status_code == 206
    assert file_response["Content-Range"].startswith("bytes 0-4/")
    assert file_response["Accept-Ranges"] == "bytes"
    assert file_response["ETag"] == f'"{asset.sha256}"'
    assert b"".join(file_response.streaming_content) == b"%PDF-"

    settings.X_ACCEL_REDIRECT_ENABLED = True
    settings.X_ACCEL_REDIRECT_PREFIX = "/__protected_assets/"
    accelerated = api_client.get(
        f"/api/distribution/assets/{asset.id}/file/",
        HTTP_X_USE_X_ACCEL="1",
    )
    assert accelerated.status_code == 200
    assert accelerated["X-Accel-Redirect"].startswith("/__protected_assets/")
    assert accelerated["Accept-Ranges"] == "bytes"
    assert accelerated["Cache-Control"] == "public, max-age=300, must-revalidate, no-transform"
    assert int(accelerated["Content-Length"]) > 5
    direct_after_enable = api_client.get(
        f"/api/distribution/assets/{asset.id}/file/",
        HTTP_RANGE="bytes=0-4",
    )
    assert direct_after_enable.status_code == 206
    assert b"".join(direct_after_enable.streaming_content) == b"%PDF-"

    settings.PUBLIC_DEPLOYMENT_MODE = True
    public_direct = api_client.get(
        f"/api/distribution/assets/{asset.id}/file/",
        HTTP_RANGE="bytes=0-4",
    )
    assert public_direct.status_code == 503
    assert public_direct.data["detail"] == "公网文件请求必须经过受信任的文件代理。"
    public_accelerated = api_client.get(
        f"/api/distribution/assets/{asset.id}/file/",
        HTTP_X_USE_X_ACCEL="1",
    )
    assert public_accelerated.status_code == 200
    assert public_accelerated["X-Accel-Redirect"].startswith("/__protected_assets/")
    settings.PUBLIC_DEPLOYMENT_MODE = False

    dashboard_before = api_client.get("/api/ingestion/dashboard/")
    assert dashboard_before.data["documents"]["published"] == 1
    assert dashboard_before.data["pdf_assets"] == 1

    old_asset = asset
    old_normalized_path = Path(old_asset.file.path)
    old_original = edition.assets.get(kind=Asset.Kind.ORIGINAL, is_current=True)
    old_original_path = Path(old_original.file.path)
    annotation = Annotation.objects.create(
        user=reader_user,
        asset=old_asset,
        page=old_asset.pages.get(index=1),
        kind=Annotation.Kind.HIGHLIGHT,
        selector={"text": "Power"},
        quote="Power",
        asset_sha256=old_asset.sha256,
    )
    replacement_source = tmp_path / "replacement.pdf"
    replacement_payload = build_test_pdf(
        replacement_source,
        marker="ReplacementMarker unique current text",
    )
    with patch("ingestion.services.dispatch.dispatch_upload_item") as queued:
        replace_response = api_client.post(
            f"/api/ingestion/items/{item.id}/replace/",
            {
                "file": SimpleUploadedFile(
                    "replacement-unstructured-name.pdf",
                    replacement_payload,
                    content_type="application/pdf",
                ),
            },
            format="multipart",
        )
    assert replace_response.status_code == 202
    assert queued.call_count == 1
    assert str(replace_response.data["replacement_of_asset"]) == str(old_asset.id)
    replacement_item = UploadItem.objects.get(pk=replace_response.data["id"])
    assert replacement_item.batch.source == "replacement"

    replacement_item = run_pipeline(str(replacement_item.id))
    replacement_item.refresh_from_db()
    edition.refresh_from_db()
    old_asset.refresh_from_db()
    old_original.refresh_from_db()
    annotation.refresh_from_db()
    new_asset = edition.assets.get(
        kind=Asset.Kind.NORMALIZED,
        is_current=True,
    )
    new_original = edition.assets.get(
        kind=Asset.Kind.ORIGINAL,
        is_current=True,
    )
    assert replacement_item.status == UploadItem.Status.PUBLISHED
    assert edition.state == PublicationState.PUBLISHED
    assert edition.work.title == "测试社会学著作"
    assert old_asset.is_current is False
    assert old_original.is_current is False
    assert new_asset.id != old_asset.id
    assert new_asset.version == 2
    assert new_original.version == 2
    assert old_normalized_path.exists()
    assert old_original_path.exists()
    assert annotation.orphaned is True
    assert edition.assets.filter(kind=Asset.Kind.NORMALIZED).count() == 2
    assert edition.assets.filter(kind=Asset.Kind.ORIGINAL).count() == 2

    assert api_client.get(f"/api/catalog/assets/{old_asset.id}/manifest/").status_code == 404
    assert api_client.get(f"/api/catalog/assets/{old_asset.id}/search/", {"q": "power"}).status_code == 404
    assert api_client.get(f"/api/distribution/assets/{old_asset.id}/access/").status_code == 404
    assert api_client.get(f"/api/distribution/assets/{new_asset.id}/access/").status_code == 200
    replacement_search = api_client.get(
        f"/api/catalog/assets/{new_asset.id}/search/",
        {"q": "replacementmarker"},
    )
    assert replacement_search.status_code == 200
    assert replacement_search.data["matches"][0]["page_index"] == 1
    global_replacement_search = api_client.get(
        "/api/catalog/search/",
        {"q": "replacementmarker"},
    )
    assert global_replacement_search.data["counts"]["passages"] >= 1
    assert global_replacement_search.data["passages"][0]["asset_id"] == str(new_asset.id)
    dashboard_after_replacement = api_client.get("/api/ingestion/dashboard/")
    assert dashboard_after_replacement.data["documents"]["published"] == 1
    assert dashboard_after_replacement.data["pdf_assets"] == 2

    withdraw_response = api_client.post(
        f"/api/ingestion/items/{item.id}/withdraw/",
        {"reason": "联动验收下架"},
        format="json",
    )
    assert withdraw_response.status_code == 200
    assert api_client.get("/api/catalog/search/", {"q": "测试社会学著作"}).data["counts"]["works"] == 0
    assert api_client.get(f"/api/distribution/assets/{new_asset.id}/access/").status_code == 404
    assert not UploadItem.objects.filter(
        edition=edition,
    ).exclude(status=UploadItem.Status.WITHDRAWN).exists()

    republish_response = api_client.post(
        f"/api/ingestion/items/{item.id}/publish/",
        {"confirm_warnings": True},
        format="json",
    )
    assert republish_response.status_code == 200
    edition.refresh_from_db()
    item.refresh_from_db()
    assert edition.state == PublicationState.PUBLISHED
    assert item.status == UploadItem.Status.PUBLISHED
    assert api_client.get("/api/catalog/search/", {"q": "测试社会学著作"}).data["counts"]["works"] == 1
    assert api_client.get(f"/api/distribution/assets/{new_asset.id}/access/").status_code == 200
    assert PublicationEvent.objects.filter(
        edition=edition,
        event_type=PublicationEvent.EventType.REPUBLISH,
    ).exists()
