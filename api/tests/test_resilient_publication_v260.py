from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import patch

import fitz
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from catalog.models import (
    AnonymousUsageEvent,
    Asset,
    DocumentType,
    Edition,
    OcrStatus,
    Page,
    PageLabelStatus,
    PublicationState,
    ReaderRenditionPolicy,
    SearchQueryAggregate,
    TextBlock,
    Work,
)
from catalog.services.analytics import aggregate_search_queries
from catalog.services.page_labels import infer_page_labels
from catalog.services.semantic_search import semantic_model_health
from ingestion.models import FieldLock, UploadBatch, UploadItem
from ingestion.services.metadata import Candidate
from ingestion.services.publication import (
    PublicationWarningsRequireConfirmation,
    publication_preflight,
    publish_edition,
    withdraw_edition,
)
from ingestion.services.ocr_pdf import create_searchable_ocr_pdf
from ingestion.views import _schedule_publication_background_tasks


def create_item_with_files(settings, tmp_path, *, title="状态分离测试"):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.NAS_ORIGINAL_ROOT = settings.MEDIA_ROOT / "originals"
    settings.NAS_PUBLIC_ROOT = settings.MEDIA_ROOT / "public"
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = False
    settings.ALLOW_LOCAL_PUBLIC_ASSET_ACCESS = True
    settings.PUBLIC_DEPLOYMENT_MODE = False
    settings.X_ACCEL_REDIRECT_ENABLED = False

    work = Work.objects.create(
        document_type=DocumentType.BOOK,
        title=title,
        language="zh-CN",
    )
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.READY,
        public_slug=f"resilient-{work.id}",
        canonical_filename=f"{title}.pdf",
        ocr_status=OcrStatus.PENDING,
        page_label_status=PageLabelStatus.PENDING,
        review_progress=60,
    )
    fixture_sha = sha256(title.encode("utf-8")).hexdigest()
    original = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.ORIGINAL,
        file=SimpleUploadedFile("original.pdf", b"%PDF-1.4 original source"),
        sha256=fixture_sha,
        byte_size=24,
        page_count=1,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
    )
    normalized = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=SimpleUploadedFile("reader.pdf", b"%PDF-1.4 stable reader copy"),
        sha256=fixture_sha,
        byte_size=27,
        page_count=1,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        source_asset=original,
    )
    return work, edition, original, normalized


@pytest.mark.django_db
def test_publication_state_is_independent_from_ocr_review_and_semantic_work(
    settings,
    tmp_path,
):
    _work, edition, original, normalized = create_item_with_files(settings, tmp_path)

    preflight = publication_preflight(edition)
    assert preflight["blockers"] == []
    assert "人工复核尚未完成（60%）" in preflight["warnings"]
    assert "OCR 尚未完成，扫描件暂时不能选择文字" in preflight["warnings"]
    assert set(preflight["background_tasks"]) >= {"OCR", "页码识别", "语义索引"}

    with pytest.raises(PublicationWarningsRequireConfirmation):
        publish_edition(edition)

    publish_edition(edition, confirm_warnings=True)
    edition.refresh_from_db()
    first_published_at = edition.first_published_at
    stable_slug = edition.public_slug
    assert edition.state == PublicationState.PUBLISHED
    assert first_published_at is not None

    edition.ocr_status = OcrStatus.FAILED
    edition.save(update_fields=["ocr_status", "updated_at"])
    edition.refresh_from_db()
    assert edition.state == PublicationState.PUBLISHED

    withdraw_edition(edition, reason="测试下架但保留资料")
    edition.refresh_from_db()
    assert edition.state == PublicationState.WITHDRAWN
    assert Asset.objects.filter(pk__in=[original.pk, normalized.pk]).count() == 2

    publish_edition(edition, confirm_warnings=True)
    edition.refresh_from_db()
    assert edition.state == PublicationState.PUBLISHED
    assert edition.public_slug == stable_slug
    assert edition.first_published_at == first_published_at
    assert edition.last_published_at >= first_published_at


@pytest.mark.django_db
def test_ocr_disabled_publication_keeps_page_labels_but_skips_empty_semantic_work(
    settings,
    tmp_path,
    admin_user,
):
    _work, edition, _original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="跳过 OCR 扫描本",
    )
    edition.ocr_status = OcrStatus.DISABLED
    edition.page_label_status = PageLabelStatus.PENDING
    edition.save(update_fields=["ocr_status", "page_label_status", "updated_at"])
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="skip.pdf",
        status=UploadItem.Status.READY,
        edition=edition,
        asset=normalized,
    )
    page_job = SimpleNamespace(
        id="page-job",
        status="pending",
        started_at=None,
        attempt=0,
    )

    with patch(
        "ingestion.views.queue_page_label_job",
        return_value=page_job,
    ) as page_labels, patch(
        "ingestion.views.queue_semantic_job",
    ) as semantic:
        scheduled, warnings = _schedule_publication_background_tasks(
            item,
            normalized,
            admin_user,
        )

    assert warnings == []
    assert [task["type"] for task in scheduled] == ["page_labels"]
    page_labels.assert_called_once_with(
        normalized,
        upload_item=item,
        actor=admin_user,
        force=False,
    )
    semantic.assert_not_called()


@pytest.mark.django_db
def test_admin_publish_survives_search_index_failure_and_withdraw_preserves_files(
    settings,
    tmp_path,
    api_client,
    admin_user,
    reader_user,
):
    _work, edition, original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="索引故障仍可发布",
    )
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="source.pdf",
        status=UploadItem.Status.READY,
        edition=edition,
        asset=normalized,
    )

    api_client.force_authenticate(reader_user)
    assert api_client.post(
        f"/api/ingestion/items/{item.id}/publish/",
        {"confirm_warnings": True},
        format="json",
    ).status_code == 403

    api_client.force_authenticate(admin_user)
    with patch("ingestion.views.index_asset", side_effect=RuntimeError("search offline")), patch(
        "ingestion.views.queue_semantic_job",
    ) as semantic_queue, patch(
        "ingestion.views.queue_ocr_job",
    ) as ocr_queue:
        ocr_queue.return_value.id = "ocr-job"
        ocr_queue.return_value.status = "pending"
        ocr_queue.return_value.started_at = None
        ocr_queue.return_value.attempt = 0
        response = api_client.post(
            f"/api/ingestion/items/{item.id}/publish/",
            {"confirm_warnings": True},
            format="json",
        )
    assert response.status_code == 200
    assert "search offline" in response.data["index_warning"]
    semantic_queue.assert_not_called()
    ocr_queue.assert_called_once_with(
        normalized,
        upload_item=item,
        actor=admin_user,
        force=False,
    )
    assert response.data["scheduled_tasks"][0]["type"] == "ocr"
    edition.refresh_from_db()
    assert edition.state == PublicationState.PUBLISHED

    with patch("ingestion.views.remove_asset_from_index"), patch(
        "ingestion.views.remove_semantic_asset",
    ):
        response = api_client.post(
            f"/api/ingestion/items/{item.id}/withdraw/",
            {"reason": "管理测试"},
            format="json",
        )
    assert response.status_code == 200
    edition.refresh_from_db()
    assert edition.state == PublicationState.WITHDRAWN
    assert Asset.objects.filter(pk__in=[original.pk, normalized.pk]).count() == 2
    assert original.file.storage.exists(original.file.name)
    assert normalized.file.storage.exists(normalized.file.name)


@pytest.mark.django_db
def test_withdrawal_stays_effective_when_search_cleanup_is_unavailable(
    settings,
    tmp_path,
    api_client,
    admin_user,
):
    _work, edition, _original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="下架优先测试",
    )
    edition.state = PublicationState.PUBLISHED
    edition.save(update_fields=["state", "updated_at"])
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="withdraw.pdf",
        status=UploadItem.Status.PUBLISHED,
        edition=edition,
        asset=normalized,
    )
    api_client.force_authenticate(admin_user)

    with patch(
        "ingestion.views.remove_asset_from_index",
        side_effect=ConnectionError("keyword search offline"),
    ), patch(
        "ingestion.views.remove_semantic_asset",
        side_effect=ConnectionError("semantic search offline"),
    ):
        response = api_client.post(
            f"/api/ingestion/items/{item.id}/withdraw/",
            {"reason": "管理员决定"},
            format="json",
        )

    assert response.status_code == 200
    assert len(response.data["index_warnings"]) == 2
    edition.refresh_from_db()
    item.refresh_from_db()
    assert edition.state == PublicationState.WITHDRAWN
    assert item.status == UploadItem.Status.WITHDRAWN


@pytest.mark.django_db
def test_remote_metadata_candidates_never_overwrite_locked_manual_fields(
    settings,
    tmp_path,
    api_client,
    admin_user,
):
    _work, edition, _original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="人工锁定书名",
    )
    edition.publisher = "人工出版社"
    edition.save(update_fields=["publisher", "updated_at"])
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="metadata.pdf",
        status=UploadItem.Status.READY,
        edition=edition,
        asset=normalized,
    )
    FieldLock.objects.create(
        edition=edition,
        field_name="title",
        locked_by=admin_user,
        locked_value="人工锁定书名",
        reason="人工复核",
    )
    api_client.force_authenticate(admin_user)
    candidates = [
        Candidate(
            "title",
            "外部候选书名",
            "openlibrary_title",
            0.82,
            {"query": "人工锁定书名", "record_url": "https://openlibrary.org/works/OL1W"},
        ),
        Candidate("publisher", "外部出版社", "openlibrary_title", 0.78),
    ]

    with patch(
        "ingestion.views.refresh_remote_candidates",
        return_value=(candidates, []),
    ):
        response = api_client.post(
            f"/api/ingestion/items/{item.id}/metadata-suggestions/",
            {},
            format="json",
        )

    assert response.status_code == 200
    assert response.data["added"] == 2
    assert "title" in response.data["locked_fields"]
    edition.refresh_from_db()
    edition.work.refresh_from_db()
    assert edition.work.title == "人工锁定书名"
    assert edition.publisher == "人工出版社"
    assert item.metadata_candidates.filter(
        field_name="title",
        value="外部候选书名",
        selected=False,
    ).exists()


@pytest.mark.django_db
def test_reader_and_download_use_only_validated_ocr_pdf_with_original_fallback(
    settings,
    tmp_path,
    api_client,
):
    _work, edition, original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="阅读副本回退测试",
    )
    edition.state = PublicationState.PUBLISHED
    edition.reader_rendition_policy = ReaderRenditionPolicy.OCR
    edition.save(update_fields=["state", "reader_rendition_policy", "updated_at"])
    invalid_ocr = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.OCR_PDF,
        file=SimpleUploadedFile("bad-ocr.pdf", b"not a usable pdf"),
        sha256="2" * 64,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.INVALID,
        source_asset=original,
    )

    access_url = f"/api/distribution/assets/{normalized.id}/access/"
    response = api_client.get(access_url)
    assert response.status_code == 200
    assert response.data["requested_asset_id"] == str(normalized.id)
    assert response.data["served_asset_id"] == str(normalized.id)
    assert response.data["source_artifact_id"] == str(original.id)
    assert response.data["reader_fallback_reason"]
    assert response.data["download_url"].endswith(f"/{normalized.id}/file/?download=1")

    valid_ocr = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.OCR_PDF,
        file=SimpleUploadedFile("good-ocr.pdf", b"%PDF-1.4 validated OCR copy"),
        sha256="3" * 64,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        source_asset=original,
        processor="PaddleOCR",
        processor_version="test",
    )
    edition.ocr_status = OcrStatus.SUCCEEDED
    edition.save(update_fields=["ocr_status", "updated_at"])
    response = api_client.get(access_url)
    assert response.status_code == 200
    assert response.data["served_asset_id"] == str(valid_ocr.id)
    assert response.data["rendition"] == Asset.Kind.OCR_PDF
    assert response.data["download_url"].endswith(f"/{normalized.id}/file/?download=1")
    assert response.data["original_download_url"].endswith(
        f"/{normalized.id}/file/?download=original"
    )
    assert response.data["download_rendition"] == Asset.Kind.OCR_PDF

    download = api_client.get(access_url, {"download": "1"})
    assert download.status_code == 200
    assert download.data["served_asset_id"] == str(valid_ocr.id)
    assert download.data["source_artifact_id"] == str(original.id)
    original_download = api_client.get(access_url, {"download": "original"})
    assert original_download.status_code == 200
    assert original_download.data["served_asset_id"] == str(normalized.id)
    assert invalid_ocr.validation_status == Asset.ValidationStatus.INVALID


@pytest.mark.django_db
def test_searchable_ocr_pdf_is_versioned_and_keeps_mixed_language_text(
    settings,
    tmp_path,
):
    settings.MEDIA_ROOT = tmp_path / "media"
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.draw_rect(fitz.Rect(40, 40, 555, 802), color=(0.2, 0.2, 0.2))
    payload = document.tobytes()
    document.close()
    digest = sha256(payload).hexdigest()
    work = Work.objects.create(document_type=DocumentType.BOOK, title="OCR 下载副本", language="zh-CN")
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        public_slug=f"ocr-download-{work.id}",
        canonical_filename="OCR下载副本.pdf",
        ocr_status=OcrStatus.SUCCEEDED,
    )
    original = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.ORIGINAL,
        file=SimpleUploadedFile("original.pdf", payload, content_type="application/pdf"),
        sha256=digest,
        byte_size=len(payload),
        page_count=1,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
    )
    normalized = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=SimpleUploadedFile("reader.pdf", payload, content_type="application/pdf"),
        sha256=digest,
        byte_size=len(payload),
        page_count=1,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        source_asset=original,
    )
    page_row = Page.objects.create(
        asset=normalized,
        index=1,
        text="布迪厄 Bourdieu 1958 1962 INSEE",
        normalized_text="布迪厄 bourdieu 1958 1962 insee",
        text_source=Page.TextSource.OCR,
        confidence=0.98,
        width=595,
        height=842,
    )
    TextBlock.objects.create(
        page=page_row,
        order=0,
        text="布迪厄 Bourdieu 1958 1962 INSEE",
        normalized_text="布迪厄 bourdieu 1958 1962 insee",
        bbox=[80, 120, 450, 155],
        confidence=0.98,
    )

    derivative = create_searchable_ocr_pdf(
        normalized,
        processor="paddleocr_nas",
        processor_version="test-settings",
    )

    assert derivative.kind == Asset.Kind.OCR_PDF
    assert derivative.source_asset_id == original.id
    assert derivative.version == 1
    assert derivative.validation_status == Asset.ValidationStatus.VALID
    assert derivative.validation_details["inserted_blocks"] == 1
    output = fitz.open(derivative.file.path)
    extracted = output[0].get_text()
    output.close()
    assert "1958" in extracted
    assert "1962" in extracted
    assert "Bourdieu" in extracted
    assert "布迪厄" in extracted


@pytest.mark.django_db
def test_page_segment_maps_pdf_page_73_to_printed_page_50(
    settings,
    tmp_path,
    api_client,
    admin_user,
):
    _work, edition, _original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="真实页码测试",
    )
    edition.state = PublicationState.PUBLISHED
    edition.citation_data = {"type": "book", "title": edition.work.title}
    edition.save(update_fields=["state", "citation_data", "updated_at"])
    normalized.page_count = 73
    normalized.save(update_fields=["page_count", "updated_at"])
    Page.objects.bulk_create(
        [
            Page(
                asset=normalized,
                index=index,
                text_source=Page.TextSource.NONE,
                label_source=Page.LabelSource.FILE_INDEX,
                width=595,
                height=842,
            )
            for index in range(1, 74)
        ]
    )

    api_client.force_authenticate(admin_user)
    endpoint = f"/api/catalog/admin/assets/{normalized.id}/page-mapping/"
    response = api_client.post(
        endpoint,
        {
            "action": "create_segment",
            "start_file_page_index": 24,
            "end_file_page_index": 73,
            "start_label": "1",
            "style": "arabic",
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.data["updated_pages"] == 50
    page_73 = normalized.pages.get(index=73)
    assert page_73.printed_label == "50"
    assert page_73.is_label_manual is True

    response = api_client.post(endpoint, {"action": "confirm"}, format="json")
    assert response.status_code == 200
    edition.refresh_from_db()
    assert edition.page_label_status == PageLabelStatus.READY

    api_client.force_authenticate(user=None)
    page = api_client.get(f"/api/catalog/assets/{normalized.id}/pages/73/")
    assert page.status_code == 200
    assert page.data["file_page_index"] == 73
    assert page.data["printed_label"] == "50"
    assert page.data["citation_page_label"] == "50"

    citation = api_client.get(
        f"/api/catalog/editions/{edition.id}/citations/",
        {"pdf_page": 73},
    )
    assert citation.status_code == 200
    assert citation.data["page"] == {
        "pdf_page": 73,
        "printed_label": "50",
        "citation_label": "50",
        "source": "pdf-label",
    }


@pytest.mark.django_db
def test_embedded_book_page_header_maps_pdf_page_48_to_printed_page_32(
    settings,
    tmp_path,
):
    _work, edition, _original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="页眉页码自动识别",
    )
    pages = []
    for file_page, printed_page in ((47, 31), (48, 32), (49, 33)):
        page = Page.objects.create(
            asset=normalized,
            index=file_page,
            text=f"第 {printed_page} 页\n正文",
            text_source=Page.TextSource.EMBEDDED,
            label_source=Page.LabelSource.FILE_INDEX,
            width=595,
            height=842,
        )
        TextBlock.objects.create(
            page=page,
            order=0,
            block_type="header",
            text=f"第 {printed_page} 页",
            normalized_text=str(printed_page),
            bbox=[284, 26, 332, 34],
            confidence=1,
        )
        pages.append(page)

    result = infer_page_labels(normalized)

    pages[1].refresh_from_db()
    edition.refresh_from_db()
    assert result["accepted_continuous_candidates"] == 3
    assert pages[1].printed_label == "32"
    assert pages[1].label_source == Page.LabelSource.EMBEDDED_TEXT
    assert pages[1].label_confidence > 0.95
    assert edition.page_label_status == PageLabelStatus.NEEDS_REVIEW


@pytest.mark.django_db
def test_anonymous_search_events_generate_privacy_preserving_hot_searches(settings):
    settings.DEBUG = True
    clients = [APIClient(), APIClient(), APIClient()]
    queries = ["  SOCIAL\u3000THEORY  ", "social theory", "ＳＯＣＩＡＬ THEORY"]
    for client, query in zip(clients, queries, strict=True):
        response = client.post(
            "/api/catalog/usage-events/",
            {
                "event_type": "search_submit",
                "query": query,
                "result_count": 4,
                "source": "global-search",
            },
            format="json",
        )
        assert response.status_code == 202
        assert response.data["accepted"] is True

    click = clients[0].post(
        "/api/catalog/usage-events/",
        {
            "event_type": "search_result_click",
            "query": "social theory",
            "result_count": 4,
            "source": "global-search",
        },
        format="json",
    )
    assert click.status_code == 202

    events = AnonymousUsageEvent.objects.all()
    assert events.count() == 4
    assert events.filter(normalized_query="social theory").count() == 4
    assert events.values("session_hash").distinct().count() == 3
    assert all(len(value) == 64 for value in events.values_list("session_hash", flat=True))
    assert not any(field.name in {"ip", "ip_address", "user"} for field in AnonymousUsageEvent._meta.fields)

    aggregate_search_queries()
    aggregate = SearchQueryAggregate.objects.get(normalized_query="social theory")
    assert aggregate.search_count == 3
    assert aggregate.unique_sessions == 3
    assert aggregate.click_count == 1
    assert aggregate.excluded is False

    hot = clients[0].get("/api/catalog/hot-searches/")
    assert hot.status_code == 200
    assert hot.data["results"][0] == {
        "query": "social theory",
        "search_count": 3,
        "unique_sessions": 3,
        "click_count": 1,
        "zero_result_count": 0,
    }


def test_offline_semantic_health_checks_revision_files_and_dimensions(tmp_path):
    cache = tmp_path / "models"
    model_root = cache / "models--sentence-transformers--test-model"
    snapshot = model_root / "snapshots" / "abc123"
    snapshot.mkdir(parents=True)
    (model_root / "refs").mkdir()
    (model_root / "refs" / "main").write_text("abc123", encoding="utf-8")
    (snapshot / "config.json").write_text('{"hidden_size": 384}', encoding="utf-8")
    (snapshot / "tokenizer_config.json").write_text("{}", encoding="utf-8")
    (snapshot / "model.safetensors").write_bytes(b"test-weights")
    runtime = {
        "engine": "meilisearch_hybrid",
        "provider": "huggingFace",
        "model_repo_id": "sentence-transformers/test-model",
        "model_local_path": str(cache),
        "model_revision": "main",
        "dimensions": 384,
        "offline_mode": True,
    }

    health = semantic_model_health(runtime)
    assert health["available"] is True
    assert health["resolved_revision"] == "abc123"
    assert health["detected_dimensions"] == 384

    health = semantic_model_health({**runtime, "dimensions": 768})
    assert health["available"] is False
    assert health["error_code"] == "MODEL_UNAVAILABLE"
    assert health["files"]["dimensions_match"] is False

    health = semantic_model_health({**runtime, "model_revision": "missing"})
    assert health["available"] is False
    assert health["error_code"] == "MODEL_UNAVAILABLE"
    assert health["files"]["revision_available"] is False

    direct_commit = semantic_model_health({**runtime, "model_revision": "abc123"})
    assert direct_commit["files"]["revision_available"] is True
    assert direct_commit["files"]["meilisearch_revision_ref"] is False
    assert direct_commit["available"] is False
    assert "revision 引用" in direct_commit["reason"]

    (model_root / "refs" / "abc123").write_text("abc123", encoding="utf-8")
    direct_commit = semantic_model_health({**runtime, "model_revision": "abc123"})
    assert direct_commit["files"]["meilisearch_revision_ref"] is True
    assert direct_commit["available"] is True
