from io import BytesIO

import pytest

from catalog.models import Asset, Edition, Page, PublicationState, Work
from catalog.services.search_geometry import estimate_block_highlights
from ingestion.services.files import materialize_field_file
from ingestion.services.metadata import extract_text_candidates, select_best
from reading.models import Annotation


def test_ocr_text_can_refine_book_metadata_without_using_filename():
    text = """测试社会学著作
作者：测试学者
测试出版社
2026

本书讨论权力、制度与社会理论。
"""
    selected = select_best(extract_text_candidates(text, source="ocr_first_pages"))
    assert selected["title"] == "测试社会学著作"
    assert selected["authors"] == ["测试学者"]
    assert selected["publisher"] == "测试出版社"
    assert selected["publication_year"] == 2026
    assert selected["language"] == "zh-CN"


def test_ocr_search_highlight_is_narrower_than_the_paragraph_block():
    block_bbox = [100, 100, 500, 500]
    text = (
        "社会理论讨论权力、身份、制度与公共生活。" * 35
        + "需要精确定位的测试概念"
        + "社会结构会影响知识生产。" * 25
    )
    rectangles = estimate_block_highlights(text, block_bbox, "测试概念")
    assert rectangles
    assert all(rectangle[2] - rectangle[0] < 400 for rectangle in rectangles)
    assert all(rectangle[3] - rectangle[1] < 100 for rectangle in rectangles)


def test_remote_intake_file_is_materialized_and_removed():
    class RemoteFieldFile:
        name = "private-intake/example.pdf"

        @property
        def path(self):
            raise NotImplementedError

        def open(self, mode):
            assert mode == "rb"
            return BytesIO(b"%PDF-1.4\nremote")

    path, cleanup = materialize_field_file(RemoteFieldFile())
    try:
        assert path.read_bytes() == b"%PDF-1.4\nremote"
    finally:
        assert cleanup is not None
        cleanup()
    assert not path.exists()


@pytest.mark.django_db
def test_clean_copy_repairs_line_breaks_and_hyphenation(api_client):
    response = api_client.post(
        "/api/catalog/clean-copy/",
        {"text": "Power is exer-\ncised through rela-\ntions.\n\n权力通过\n关系运作。"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["text"] == "Power is exercised through relations.\n\n权力通过关系运作。"
    assert "<p>" in response.data["html"]


@pytest.mark.django_db
def test_clean_copy_repairs_common_unicode_encoding_damage(api_client):
    response = api_client.post(
        "/api/catalog/clean-copy/",
        {"text": "FranÃ§ois said: â€œpowerâ€\u009d."},
        format="json",
    )
    assert response.status_code == 200
    assert "François" in response.data["text"]
    assert "Ã" not in response.data["text"]


@pytest.mark.django_db
def test_page_citation_resolves_pdf_page_to_printed_label(api_client):
    work = Work.objects.create(document_type="book", title="页码映射测试")
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        public_slug="citation-page-map",
        publication_year=2026,
        publisher="测试出版社",
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file="public/citation-page-map.pdf",
        sha256="c" * 64,
        status=Asset.Status.READY,
        page_count=8,
    )
    Page.objects.create(
        asset=asset,
        index=6,
        printed_label="37",
        text_source=Page.TextSource.EMBEDDED,
    )

    response = api_client.get(
        f"/api/catalog/editions/{edition.id}/citations/",
        {"pdf_page": 6},
    )

    assert response.status_code == 200
    assert response.data["page"] == {
        "pdf_page": 6,
        "printed_label": "37",
        "citation_label": "37",
        "source": "pdf-label",
    }
    assert "37" in response.data["gbt7714-2025"]
    assert "：6" not in response.data["gbt7714-2025"]


@pytest.mark.django_db
def test_hex_encoded_pdf_page_label_is_decoded_everywhere(api_client):
    work = Work.objects.create(document_type="book", title="十六进制页码测试")
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        public_slug="hex-page-label",
        publication_year=2026,
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file="public/hex-page-label.pdf",
        sha256="d" * 64,
        status=Asset.Status.READY,
        page_count=12,
    )
    Page.objects.create(
        asset=asset,
        index=10,
        printed_label="<FEFF00310030>",
        text_source=Page.TextSource.EMBEDDED,
    )

    page_response = api_client.get(f"/api/catalog/assets/{asset.id}/pages/10/")
    citation_response = api_client.get(
        f"/api/catalog/editions/{edition.id}/citations/",
        {"pdf_page": 10},
    )

    assert page_response.status_code == 200
    assert page_response.data["printed_label"] == "10"
    assert citation_response.status_code == 200
    assert citation_response.data["page"]["printed_label"] == "10"
    assert "<FEFF" not in citation_response.data["gbt7714-2025"]


@pytest.mark.django_db
def test_private_annotation_body_is_only_returned_to_owner(api_client, reader_user, admin_user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    work = Work.objects.create(document_type="book", title="隐私测试", normalized_title="隐私测试")
    edition = Edition.objects.create(work=work, state=PublicationState.PUBLISHED, public_slug="privacy-test")
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file="assets/test.pdf",
        sha256="a" * 64,
        status=Asset.Status.READY,
        page_count=1,
    )
    page = Page.objects.create(
        asset=asset,
        index=1,
        text_source=Page.TextSource.EMBEDDED,
        text="test",
        normalized_text="test",
    )
    api_client.force_authenticate(reader_user)
    create_response = api_client.post(
        "/api/reading/annotations/",
        {
            "asset": str(asset.id),
            "page": str(page.id),
            "kind": "note",
            "selector": {"start": 0, "end": 4},
            "quote": "test",
            "body": "这是私人笔记",
            "color": "yellow",
        },
        format="json",
    )
    assert create_response.status_code == 201
    annotation = Annotation.objects.get()
    assert b"\xe8\xbf\x99\xe6\x98\xaf" not in bytes(annotation.body_ciphertext)
    assert create_response.data["body_text"] == "这是私人笔记"

    api_client.force_authenticate(admin_user)
    list_response = api_client.get("/api/reading/annotations/")
    assert list_response.status_code == 200
    assert list_response.data["results"] == []
