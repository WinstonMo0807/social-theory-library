import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import uuid

import fitz
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.models import Asset, OcrStatus, PublicationState, SemanticIndexStatus
from ingestion.models import MetadataCandidate, UploadItem
from ingestion.services.metadata import Candidate
from ingestion.services.pipeline import run_pipeline


def _build_text_pdf(path: Path) -> bytes:
    document = fitz.open()
    for page_number in range(1, 4):
        page = document.new_page(width=595, height=842)
        page.insert_textbox(
            fitz.Rect(55, 55, 540, 780),
            (
                "Chinese sociology publication workflow\n"
                "This born-digital page has a selectable text layer. " * 20
                + f"\nPrinted page {page_number}"
            ),
            fontsize=10,
            fontname="helv",
        )
    document.set_metadata(
        {
            "title": "待复核的中文书目",
            "author": "待复核作者",
            "subject": "中国社会学",
        }
    )
    document.save(path)
    document.close()
    return path.read_bytes()


def _build_chinese_journal_pdf(path: Path) -> bytes:
    document = fitz.open()
    for page_number in range(1, 3):
        page = document.new_page(width=595, height=842)
        body = "\n".join(
            [
                "Abstract",
                "Keywords: social theory; Chinese experience",
                "DOI: 10.1234/chinese-journal.2026.01",
                *[
                    "This born-digital journal article keeps a selectable text layer."
                    for _index in range(8)
                ],
                f"Article page {page_number}",
            ]
        )
        page.insert_textbox(
            fitz.Rect(55, 55, 540, 780),
            body,
            fontsize=10,
            fontname="helv",
        )
    document.set_metadata(
        {
            "title": "社会理论的中国经验",
            "author": "张三; 李明",
            "subject": "中文社会科学期刊论文 Abstract Keywords",
        }
    )
    document.save(path)
    document.close()
    return path.read_bytes()


def _pending_job():
    return SimpleNamespace(
        id=uuid.uuid4(),
        status="pending",
        started_at=None,
        attempt=0,
        attempts=0,
    )


@pytest.mark.django_db(transaction=True)
def test_complete_chinese_pdf_http_ingestion_review_publish_and_withdraw(
    api_client,
    admin_user,
    tmp_path,
    settings,
):
    """Force the public-safe path from HTTP upload through publication.

    External services are deliberately replaced at their adapters.  The test
    still exercises the real API views, pipeline state, persisted assets,
    metadata candidate import, administrator preflight and public catalog
    filtering without touching Redis, OCR, Meilisearch, NAS or the internet.
    """

    settings.MEDIA_ROOT = tmp_path / "media"
    settings.NAS_ORIGINAL_ROOT = settings.MEDIA_ROOT / "originals"
    settings.NAS_PUBLIC_ROOT = settings.MEDIA_ROOT / "public"
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = False
    settings.ALLOW_LOCAL_PUBLIC_ASSET_ACCESS = True
    settings.REQUIRE_EXTERNAL_SEARCH = False
    settings.CELERY_TASK_ALWAYS_EAGER = False

    source = tmp_path / "chinese-book.pdf"
    pdf = _build_text_pdf(source)
    api_client.force_authenticate(admin_user)

    batch_response = api_client.post(
        "/api/ingestion/batches/create/",
        {
            "expected_count": 1,
            "label": "中文图书完整上架回归",
            "access_policy": "public",
            "ocr_strategy": "auto",
            "duplicate_policy": "review",
            "external_enrichment_enabled": True,
            "ai_suggestions_enabled": False,
        },
        format="json",
    )
    assert batch_response.status_code == 201

    with patch("ingestion.services.dispatch.dispatch_upload_item") as dispatch:
        upload_response = api_client.post(
            f"/api/ingestion/batches/{batch_response.data['id']}/items/",
            {
                "client_token": "complete-chinese-flow-2026",
                "file": SimpleUploadedFile(
                    "乡土中国_测试.pdf",
                    pdf,
                    content_type="application/pdf",
                ),
            },
            format="multipart",
        )
    assert upload_response.status_code == 202
    assert upload_response.data["accepted"] is True
    dispatch.assert_called_once()
    item = UploadItem.objects.get(pk=upload_response.data["item"]["id"])

    def offline_enrichment(candidates, *_args, **_kwargs):
        return candidates, ["测试环境未调用外部书目服务，保留本地候选。"]

    with (
        patch(
            "ingestion.services.pipeline.enrich_candidates_with_gateway",
            side_effect=offline_enrichment,
        ),
        patch(
            "ingestion.services.pipeline.index_asset",
            return_value={"indexed": True, "test_adapter": True},
        ),
        patch("ingestion.services.pipeline.queue_semantic_job"),
        patch("ingestion.services.pipeline.queue_page_label_job"),
        patch(
            "ingestion.services.pipeline.generate_theory_review_tasks",
            return_value={"created": 0, "reused": 0},
        ),
        patch("ingestion.services.pipeline.detect_publication_places", return_value=[]),
        patch("ingestion.services.pipeline.generate_cover_candidates", return_value=[]),
    ):
        processed = run_pipeline(str(item.id))

    processed.refresh_from_db()
    processed.edition.refresh_from_db()
    assert processed.status == UploadItem.Status.READY
    assert processed.workflow_state == UploadItem.WorkflowState.READY
    assert processed.preflight_summary["text_profile"] == "born_digital"
    assert processed.edition.ocr_status == OcrStatus.NOT_REQUIRED
    assert processed.edition.semantic_index_status == SemanticIndexStatus.PENDING
    original = processed.edition.assets.get(kind=Asset.Kind.ORIGINAL, is_current=True)
    normalized = processed.edition.assets.get(kind=Asset.Kind.NORMALIZED, is_current=True)
    assert original.sha256 == normalized.sha256 == processed.sha256
    assert Path(original.file.path).is_file()
    assert Path(normalized.file.path).is_file()
    assert normalized.pages.count() == 3

    sidecar = {
        "schema_version": 1,
        "title": "乡土中国",
        "authors": ["费孝通"],
        "publisher": "北京大学出版社",
        "publication_place": "北京",
        "publication_year": 2012,
        "isbn": "9787301174821",
        "language": "zh-CN",
    }
    import_response = api_client.post(
        f"/api/ingestion/items/{item.id}/metadata-import/",
        {
            "file": SimpleUploadedFile(
                "乡土中国.sidecar.json",
                json.dumps(sidecar, ensure_ascii=False).encode("utf-8"),
                content_type="application/json",
            )
        },
        format="multipart",
    )
    assert import_response.status_code == 201
    assert import_response.data["format"] == "sidecar_json"
    assert import_response.data["stats"]["added"] >= 6
    assert all(
        row["lifecycle"] == MetadataCandidate.Lifecycle.PROPOSED
        and row["selected"] is False
        for row in import_response.data["candidates"]
    )
    processed.edition.work.refresh_from_db()
    assert processed.edition.work.title != "乡土中国"

    review_response = api_client.put(
        f"/api/ingestion/items/{item.id}/review/",
        {
            "title": "乡土中国",
            "subtitle": "",
            "document_type": "book",
            "language": "zh-CN",
            "publication_year": 2012,
            "publisher": "北京大学出版社",
            "publication_place": "北京",
            "journal_title": "",
            "volume": "",
            "issue": "",
            "page_range": "",
            "degree_institution": "",
            "degree_type": "",
            "report_institution": "",
            "isbn": "9787301174821",
            "doi": "",
            "abstract": "用于完整上架流程回归的中文图书。",
            "authors": ["费孝通"],
            "theory_schools": [],
            "topics": [],
            "lock_fields": [
                "title",
                "authors",
                "publisher",
                "publication_place",
                "publication_year",
                "isbn",
            ],
            "retry_publication": False,
        },
        format="json",
    )
    assert review_response.status_code == 200
    assert review_response.data["review_data"]["title"] == "乡土中国"
    assert review_response.data["review_data"]["language"] == "zh-CN"
    assert set(review_response.data["review_data"]["locked_fields"]) >= {
        "title",
        "authors",
        "publisher",
    }

    preflight_response = api_client.get(f"/api/ingestion/items/{item.id}/publish/")
    assert preflight_response.status_code == 200
    assert preflight_response.data["blockers"] == []
    assert preflight_response.data["warnings"]

    confirmation_response = api_client.post(
        f"/api/ingestion/items/{item.id}/publish/",
        {"confirm_warnings": False},
        format="json",
    )
    assert confirmation_response.status_code == 409
    assert confirmation_response.data["confirmation_required"] is True

    with (
        patch(
            "ingestion.views.index_asset",
            return_value={"indexed": True, "test_adapter": True},
        ),
        patch("ingestion.views.queue_page_label_job", side_effect=lambda *_a, **_k: _pending_job()),
        patch("ingestion.views.queue_semantic_job", side_effect=lambda *_a, **_k: _pending_job()),
    ):
        publish_response = api_client.post(
            f"/api/ingestion/items/{item.id}/publish/",
            {"confirm_warnings": True},
            format="json",
        )
    assert publish_response.status_code == 200
    assert {row["type"] for row in publish_response.data["scheduled_tasks"]} == {
        "page_labels",
        "semantic_index",
    }

    processed.refresh_from_db()
    processed.edition.refresh_from_db()
    assert processed.status == UploadItem.Status.PUBLISHED
    assert processed.workflow_state == UploadItem.WorkflowState.PUBLISHED
    assert processed.edition.state == PublicationState.PUBLISHED
    assert processed.edition.work.title == "乡土中国"
    assert processed.edition.first_published_at is not None

    public_list = api_client.get("/api/catalog/works/")
    assert public_list.status_code == 200
    assert any(row["title"] == "乡土中国" for row in public_list.data["results"])
    access_response = api_client.get(f"/api/distribution/assets/{normalized.id}/access/")
    assert access_response.status_code == 200

    with (
        patch("ingestion.views.remove_asset_from_index"),
        patch("ingestion.views.remove_semantic_asset"),
    ):
        withdraw_response = api_client.post(
            f"/api/ingestion/items/{item.id}/withdraw/",
            {"reason": "完整流程回归下架"},
            format="json",
        )
    assert withdraw_response.status_code == 200
    processed.refresh_from_db()
    processed.edition.refresh_from_db()
    assert processed.status == UploadItem.Status.WITHDRAWN
    assert processed.edition.state == PublicationState.WITHDRAWN
    assert Path(original.file.path).is_file()
    assert Path(normalized.file.path).is_file()
    public_after_withdraw = api_client.get("/api/catalog/works/")
    assert all(row["title"] != "乡土中国" for row in public_after_withdraw.data["results"])
    assert api_client.get(f"/api/distribution/assets/{normalized.id}/access/").status_code == 404


@pytest.mark.django_db(transaction=True)
def test_complete_chinese_journal_upload_remote_candidates_review_and_publish(
    api_client,
    admin_user,
    tmp_path,
    settings,
):
    """A Chinese journal article follows the same review-first publication path.

    Provider results are deterministic fixtures.  The test therefore verifies
    the production candidate store and review APIs without any real network,
    Redis, Celery or Meilisearch dependency.
    """

    settings.MEDIA_ROOT = tmp_path / "media"
    settings.NAS_ORIGINAL_ROOT = settings.MEDIA_ROOT / "originals"
    settings.NAS_PUBLIC_ROOT = settings.MEDIA_ROOT / "public"
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = False
    settings.ALLOW_LOCAL_PUBLIC_ASSET_ACCESS = True
    settings.REQUIRE_EXTERNAL_SEARCH = False
    settings.CELERY_TASK_ALWAYS_EAGER = False

    source = tmp_path / "chinese-journal.pdf"
    pdf = _build_chinese_journal_pdf(source)
    api_client.force_authenticate(admin_user)
    batch_response = api_client.post(
        "/api/ingestion/batches/create/",
        {
            "expected_count": 1,
            "label": "中文期刊完整上架回归",
            "access_policy": "public",
            "ocr_strategy": "auto",
            "external_enrichment_enabled": True,
            "ai_suggestions_enabled": False,
        },
        format="json",
    )
    assert batch_response.status_code == 201

    with patch("ingestion.services.dispatch.dispatch_upload_item"):
        upload_response = api_client.post(
            f"/api/ingestion/batches/{batch_response.data['id']}/items/",
            {
                "client_token": "complete-chinese-journal-2026",
                "file": SimpleUploadedFile(
                    "社会理论的中国经验.pdf",
                    pdf,
                    content_type="application/pdf",
                ),
            },
            format="multipart",
        )
    assert upload_response.status_code == 202
    item = UploadItem.objects.get(pk=upload_response.data["item"]["id"])

    with (
        patch(
            "ingestion.services.pipeline.enrich_candidates_with_gateway",
            side_effect=lambda candidates, *_args, **_kwargs: (candidates, []),
        ),
        patch(
            "ingestion.services.pipeline.index_asset",
            return_value={"indexed": True, "test_adapter": True},
        ),
        patch("ingestion.services.pipeline.queue_semantic_job"),
        patch("ingestion.services.pipeline.queue_page_label_job"),
        patch(
            "ingestion.services.pipeline.generate_theory_review_tasks",
            return_value={"created": 0, "reused": 0},
        ),
        patch("ingestion.services.pipeline.detect_publication_places", return_value=[]),
        patch("ingestion.services.pipeline.generate_cover_candidates", return_value=[]),
    ):
        processed = run_pipeline(str(item.id))

    processed.refresh_from_db()
    processed.edition.refresh_from_db()
    assert processed.status == UploadItem.Status.READY
    assert processed.preflight_summary["text_profile"] == "born_digital"
    assert processed.edition.ocr_status == OcrStatus.NOT_REQUIRED
    assert processed.edition.work.document_type == "journal_article"

    provider_candidates = [
        Candidate(
            "title",
            "社会理论的中国经验",
            "crossref_title",
            0.96,
            {"record_url": "https://doi.org/10.1234/chinese-journal.2026.01"},
        ),
        Candidate("authors", ["张三", "Li Ming"], "openalex_title", 0.91),
        Candidate("journal_title", "社会学研究", "openalex_title", 0.94),
        Candidate("publication_year", 2026, "crossref_title", 0.93),
        Candidate("volume", "41", "openalex_title", 0.9),
        Candidate("issue", "1", "openalex_title", 0.9),
        Candidate("page_range", "15-31", "openalex_title", 0.9),
        Candidate(
            "doi",
            "10.1234/chinese-journal.2026.01",
            "crossref_title",
            0.99,
        ),
    ]

    with patch(
        "ingestion.views.refresh_remote_candidates",
        return_value=(provider_candidates, []),
    ):
        suggestions = api_client.post(
            f"/api/ingestion/items/{item.id}/metadata-suggestions/",
            {},
            format="json",
        )
    assert suggestions.status_code == 200
    assert suggestions.data["added"] == len(provider_candidates)
    assert suggestions.data["queued"] is False
    assert all(row["lifecycle"] == MetadataCandidate.Lifecycle.PROPOSED for row in suggestions.data["results"])
    processed.edition.refresh_from_db()
    assert processed.edition.journal_title == ""

    review_response = api_client.put(
        f"/api/ingestion/items/{item.id}/review/",
        {
            "title": "社会理论的中国经验",
            "subtitle": "",
            "document_type": "journal_article",
            "language": "zh-CN",
            "publication_year": 2026,
            "publisher": "",
            "publication_place": "",
            "journal_title": "社会学研究",
            "volume": "41",
            "issue": "1",
            "page_range": "15-31",
            "degree_institution": "",
            "degree_type": "",
            "report_institution": "",
            "isbn": "",
            "doi": "10.1234/chinese-journal.2026.01",
            "abstract": "用于中文期刊完整上架回归。",
            "authors": ["张三", "Li Ming"],
            "theory_schools": [],
            "topics": [],
            "lock_fields": [
                "title",
                "authors",
                "journal_title",
                "publication_year",
                "volume",
                "issue",
                "page_range",
                "doi",
            ],
            "retry_publication": False,
        },
        format="json",
    )
    assert review_response.status_code == 200
    assert review_response.data["review_data"]["document_type"] == "journal_article"
    assert review_response.data["review_data"]["journal_title"] == "社会学研究"
    assert {"journal_title", "volume", "issue", "doi"}.issubset(
        review_response.data["review_data"]["locked_fields"]
    )

    preflight = api_client.get(f"/api/ingestion/items/{item.id}/publish/")
    assert preflight.status_code == 200
    assert preflight.data["blockers"] == []
    with (
        patch(
            "ingestion.views.index_asset",
            return_value={"indexed": True, "test_adapter": True},
        ),
        patch("ingestion.views.queue_page_label_job", side_effect=lambda *_a, **_k: _pending_job()),
        patch("ingestion.views.queue_semantic_job", side_effect=lambda *_a, **_k: _pending_job()),
    ):
        publish_response = api_client.post(
            f"/api/ingestion/items/{item.id}/publish/",
            {"confirm_warnings": True},
            format="json",
        )
    assert publish_response.status_code == 200
    processed.refresh_from_db()
    processed.edition.refresh_from_db()
    assert processed.status == UploadItem.Status.PUBLISHED
    assert processed.edition.state == PublicationState.PUBLISHED
    assert processed.edition.work.document_type == "journal_article"
    assert processed.edition.journal_title == "社会学研究"
    assert processed.edition.doi == "10.1234/chinese-journal.2026.01"

    public_list = api_client.get("/api/catalog/works/")
    assert public_list.status_code == 200
    article = next(row for row in public_list.data["results"] if row["title"] == "社会理论的中国经验")
    assert article["document_type"] == "journal_article"
    public_search = api_client.get("/api/catalog/search/", {"q": "社会理论的中国经验"})
    assert public_search.status_code == 200
    assert public_search.data["counts"]["works"] == 1
