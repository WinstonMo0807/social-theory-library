"""Real synthetic rotated/cropped PDFs, explicit OCR pixels and source-bound Reader contracts."""
from hashlib import sha256
from unittest.mock import patch
from uuid import uuid4

import fitz
import pytest
from django.core.files.base import ContentFile
from django.db import connection

from catalog.models import EvidenceSpan, Page
from catalog.services.document_intelligence import document_text_checksum, synchronize_document_revision
from catalog.services.page_geometry import native_geometry, normalized_bbox, validated_geometry
from ingestion.services.extract import extract_native_pages, extract_ocr_pages, persist_pages
from reading.research import resolve_reference
from tests.test_resilient_publication_v260 import create_item_with_files
from tests.v304_helpers import activate_catalog_revision


def cropped_pdf(path, rotation=90):
    document = fitz.open()
    page = document.new_page(width=280, height=380)
    page.insert_text((65, 95), "Agricultural organization and cooperation", fontsize=8)
    page.set_cropbox(fitz.Rect(40, 30, 240, 330))
    page.set_rotation(rotation)
    document.save(path)
    document.close()
    return path


def rendered_geometry(page, dpi=144):
    matrix = fitz.Matrix(dpi / 72, dpi / 72)
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    return {"schema": 1, "coordinate_space": "rendered_pixels", "render_dpi": dpi,
            "render_matrix": list(matrix), "render_width": pixmap.width, "render_height": pixmap.height,
            "pixmap_origin": [pixmap.x, pixmap.y], "page_rect": list(page.rect),
            "crop_box": list(page.cropbox), "rotation": page.rotation}


@pytest.mark.parametrize("rotation,expected", [
    (0, [.2, 1/6, .4, 7/30]), (90, [23/30, .2, 5/6, .4]),
    (180, [.6, 23/30, .8, 5/6]), (270, [1/6, .6, 7/30, .8]),
])
def test_native_crop_and_all_rotations_map_to_displayed_page(tmp_path, rotation, expected):
    with fitz.open(cropped_pdf(tmp_path / "native.pdf", rotation)) as document:
        geometry = native_geometry(document[0])
        assert validated_geometry(geometry, source_page=document[0])
        assert normalized_bbox([40, 50, 80, 70], geometry) == pytest.approx(expected, abs=1e-7)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_ocr_pixels_remain_in_displayed_space_after_crop_and_rotation(tmp_path, rotation):
    with fitz.open(cropped_pdf(tmp_path / "ocr.pdf", rotation)) as document:
        page = document[0]
        geometry = rendered_geometry(page)
        bbox = [.1*geometry["render_width"], .2*geometry["render_height"],
                .6*geometry["render_width"], .5*geometry["render_height"]]
        assert validated_geometry(geometry, source_page=page)
        assert normalized_bbox(bbox, geometry) == pytest.approx([.1, .2, .6, .5], abs=1e-7)


@pytest.mark.parametrize("field,value", [("rotation", 45), ("rotation", True), ("schema", 1.0),
    ("render_dpi", 0), ("render_width", float("nan")), ("render_height", -2),
    ("render_matrix", [1, 0, 0, 0, 0, 0]), ("pixmap_origin", [90, 90]),
    ("crop_box", [0, 0, float("inf"), 300]), ("coordinate_space", "unknown")])
def test_invalid_provider_geometry_fails_to_page_navigation(tmp_path, field, value):
    with fitz.open(cropped_pdf(tmp_path / "bad.pdf")) as document:
        geometry = rendered_geometry(document[0])
        geometry[field] = value
        assert validated_geometry(geometry) == {}
        assert normalized_bbox([0, 0, 30, 30], geometry) == []


@pytest.mark.parametrize("bad_geometry", [False, True])
def test_ocr_extraction_checks_metadata_against_actual_source_page(tmp_path, bad_geometry):
    path = cropped_pdf(tmp_path / "source.pdf")
    with fitz.open(path) as document:
        geometry = rendered_geometry(document[0])
    if bad_geometry:
        # Internally consistent dimensions but a different source crop/rotation.
        geometry["crop_box"] = [0, 0, 200, 300]
    payload = {"pages": [{"index": 1, "width": geometry["render_width"], "height": geometry["render_height"],
        "geometry": geometry, "confidence": 1, "blocks": [{"text": "Original evidence", "bbox": [20, 30, 70, 90]}]}]}
    with patch("ingestion.services.extract.parse_pdf_with_ocr", return_value=(payload, "fixture")):
        pages, _ = extract_ocr_pages(path)
    assert bool(pages[0].geometry) is not bad_geometry
    assert pages[0].text == "Original evidence"


@pytest.mark.django_db
def test_new_geometry_persists_to_span_private_reference_and_public_reader(settings, tmp_path, api_client, reader_user):
    _, edition, _, asset = create_item_with_files(settings, tmp_path)
    path = cropped_pdf(tmp_path / "reader-source.pdf")
    payload = path.read_bytes()
    asset.file.save("geometry.pdf", ContentFile(payload), save=False)
    asset.sha256 = sha256(payload).hexdigest()
    asset.save(update_fields=["file", "sha256"])
    pages, _ = extract_native_pages(path)
    persist_pages(asset, pages)
    page = asset.pages.get()
    assert page.geometry == pages[0].geometry
    synchronize_document_revision(asset, parser_name="native", parser_version="fixture",
        extraction_method="embedded", extraction_version="geometry-v1", schedule_claims=False)
    revision = asset.document_revisions.get(is_active=True)
    span = EvidenceSpan.objects.get(document_revision=revision)
    assert span.ocr_provenance["geometry"] == page.geometry
    edition.state = "published"
    edition.save(update_fields=["state"])
    activate_catalog_revision(edition, reader_asset=asset, document_revision=revision)
    from catalog.services.discovery_sources import source_units
    edition.refresh_from_db()
    units = list(source_units("edition", edition, {}))
    assert units and all(unit["metadata"]["source_kind"] == "native" for unit in units)
    assert all("ocr_unverified" not in unit["metadata"]["quality_flags"] for unit in units)
    expected = normalized_bbox(span.bbox, page.geometry)
    assert expected
    reference = resolve_reference({"evidence_span_id": str(span.pk)}, reader_user, strict=True)
    assert reference["normalized_bbox"] == expected and reference["geometry_status"] == "validated"
    for identifier in (span.pk, span.passage_id):
        response = api_client.get(f"/api/catalog/passages/{identifier}/focus/")
        assert response.status_code == 200
        assert response.data["normalized_bbox"] == expected
    response = api_client.get(f"/api/catalog/assets/{asset.pk}/pages/1/")
    assert response.status_code == 200
    assert response.data["geometry"] == page.geometry
    assert response.data["blocks"][0]["geometry_status"] == "validated"
    with patch("catalog.views.external_passage_ids", return_value=None):
        response = api_client.get(f"/api/catalog/assets/{asset.pk}/search/?q=Agricultural")
    assert response.status_code == 200
    highlight = response.data["matches"][0]["highlights"][0]
    assert highlight["source"] == "pdf-text" and highlight["geometry_status"] == "validated"
    with fitz.open(path) as document:
        rect = document[0].search_for("Agricultural")[0] * document[0].rotation_matrix
        expected_search = [rect.x0/300, rect.y0/200, rect.x1/300, rect.y1/200]
    assert highlight["normalized_bbox"] == pytest.approx(expected_search, abs=1e-6)


@pytest.mark.django_db
def test_unknown_geometry_is_not_invented_and_changes_revision_fingerprint(settings, tmp_path):
    _, _, _, asset = create_item_with_files(settings, tmp_path)
    page = Page.objects.create(asset=asset, index=1, text="Legacy text", normalized_text="legacy text", text_source="embedded")
    unknown = document_text_checksum(asset)
    assert page.geometry == {} and normalized_bbox([0, 0, 20, 20], page.geometry) == []
    with fitz.open(cropped_pdf(tmp_path / "known.pdf")) as document:
        page.geometry = native_geometry(document[0])
    page.save(update_fields=["geometry"])
    assert document_text_checksum(asset) != unknown
    page.geometry = {}
    page.save(update_fields=["geometry"])
    assert document_text_checksum(asset) == unknown


@pytest.mark.django_db
def test_additive_geometry_keeps_old_writer_insert_compatible(settings, tmp_path):
    _, _, _, asset = create_item_with_files(settings, tmp_path)
    page = Page.objects.create(asset=asset, index=1, text_source="none")
    fields = [field for field in Page._meta.concrete_fields if field.name != "geometry"]
    values = [field.get_db_prep_value(uuid4() if field.primary_key else 2 if field.name == "index"
              else getattr(page, field.attname), connection) for field in fields]
    columns = ",".join(connection.ops.quote_name(field.column) for field in fields)
    with connection.cursor() as cursor:
        cursor.execute(f"INSERT INTO catalog_page ({columns}) VALUES ({','.join(['%s']*len(fields))})", values)
    assert asset.pages.get(index=2).geometry == {}


def test_private_ocr_retains_validated_coordinates_without_public_catalog_writes(settings, tmp_path):
    from reading.private_ocr import enrich_private_manuscript
    settings.RAPIDOCR_SERVICE_URL = "http://127.0.0.1:8090"
    path = cropped_pdf(tmp_path / "private.pdf")
    with fitz.open(path) as document:
        geometry = rendered_geometry(document[0])
    cache = {}
    payload = {"pages": [{"index": 1, "width": geometry["render_width"], "height": geometry["render_height"],
        "geometry": geometry, "blocks": [{"text": "Private source text", "bbox": [60, 80, 360, 200]}]}]}
    with patch("reading.private_ocr._request_document_gateway", return_value=payload):
        result = enrich_private_manuscript(blob=path.read_bytes(), kind="pdf", cache=cache, generation=1,
            paragraphs=[{"text": "", "needs_ocr": True, "location": {"pdf_page": 1}}],
            checkpoint=lambda *args: True, is_current=lambda: True)
    assert result and not result[2]
    record = next(iter(cache.values()))
    assert record["geometry"] == geometry
    assert record["blocks"][0]["normalized_bbox"] == [.1, .2, .6, .5]


@pytest.mark.django_db
@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_download_ocr_layer_has_same_displayed_position_and_keeps_source_pixels(settings, tmp_path, rotation):
    from ingestion.services.extract import ExtractedBlock, ExtractedPage
    from ingestion.services.ocr_pdf import create_searchable_ocr_pdf
    _, _, original, asset = create_item_with_files(settings, tmp_path)
    document = fitz.open()
    page = document.new_page(width=280, height=380)
    page.draw_rect(fitz.Rect(55, 45, 225, 315), color=(0.2, 0.4, 0.7))
    page.set_cropbox(fitz.Rect(40, 30, 240, 330))
    page.set_rotation(rotation)
    geometry = rendered_geometry(page)
    expected = fitz.Rect(30, 40, 180, 70)
    before_pixels = page.get_pixmap().samples
    payload = document.tobytes()
    document.close()
    asset.file.save("download-geometry.pdf", ContentFile(payload), save=False)
    asset.sha256 = sha256(payload).hexdigest()
    asset.save(update_fields=["file", "sha256"])
    original_payload = original.file.read()
    persist_pages(asset, [ExtractedPage(index=1, printed_label="", chapter_title="",
        width=geometry["render_width"], height=geometry["render_height"], text="Evidence",
        source="ocr", confidence=1, geometry=geometry,
        blocks=[ExtractedBlock(order=0, text="Evidence", bbox=[60, 80, 360, 140])])])
    derivative = create_searchable_ocr_pdf(asset, processor="fixture", processor_version="geometry-v1")
    with fitz.open(derivative.file.path) as result:
        page = result[0]
        assert page.get_pixmap().samples == before_pixels
        line = page.get_text("dict")["blocks"][0]["lines"][0]
        assert "Evidence" in page.get_text()
        displayed = fitz.Rect(line["bbox"]) * page.rotation_matrix
        assert displayed.x0 == pytest.approx(expected.x0, abs=.01)
        # CJK font ascenders leave a sub-point margin inside the text box.
        assert expected.y0 <= displayed.y0 <= expected.y0 + 1
        assert displayed.x1 <= expected.x1 and displayed.y1 <= expected.y1
        matrix = page.rotation_matrix
        direction = fitz.Point(line["dir"]) * fitz.Matrix(matrix.a, matrix.b, matrix.c, matrix.d, 0, 0)
        assert tuple(direction) == pytest.approx((1, 0))
    with asset.file.storage.open(asset.file.name, "rb") as source:
        assert source.read() == payload
    with original.file.storage.open(original.file.name, "rb") as source:
        assert source.read() == original_payload


def test_download_ocr_layer_rejects_unknown_or_wrong_source_geometry(tmp_path):
    from types import SimpleNamespace
    from ingestion.services.ocr_pdf import _scaled_rectangle
    with fitz.open(cropped_pdf(tmp_path / "download-unknown.pdf")) as document:
        page = document[0]
        source = SimpleNamespace(width=600, height=400, geometry={})
        assert _scaled_rectangle([60, 80, 360, 140], source, page) is None
        source.geometry = rendered_geometry(page)
        source.geometry["crop_box"] = [0, 0, 200, 300]
        assert _scaled_rectangle([60, 80, 360, 140], source, page) is None


@pytest.mark.django_db
def test_exact_page_offsets_survive_native_blocks_and_formal_spans(settings, tmp_path):
    from ingestion.services.extract import ExtractedBlock, ExtractedPage
    _, _, _, asset = create_item_with_files(settings, tmp_path)
    text = "  First argument.  \n\nSame words.\n\n Same words. \n\nFinal qualification."
    blocks = [ExtractedBlock(order=i, text=value, bbox=[10, 10+i*20, 190, 25+i*20])
              for i, value in enumerate(["  First argument.  ", "Same words.", " Same words. ", "Final qualification."])]
    persist_pages(asset, [ExtractedPage(index=1, printed_label="", chapter_title="", width=200, height=300,
        text=text, source="embedded", confidence=1, blocks=blocks)])
    page = asset.pages.get()
    for passage in page.passages.all():
        assert page.text[passage.start_offset:passage.end_offset] == passage.text
        assert passage.text.count("Same words.") == 2
        assert "\n\n" in passage.text
    synchronize_document_revision(asset, parser_name="native", parser_version="fixture",
        extraction_method="embedded", extraction_version="offset-v1", schedule_claims=False)
    for span in EvidenceSpan.objects.filter(document_revision__asset=asset):
        assert page.text[span.start_offset:span.end_offset] == span.original_text


def test_chunk_boundaries_and_unmatched_blocks_do_not_invent_offsets():
    from ingestion.services.extract import ExtractedBlock, _passage_chunks
    text = " first argument \n\n second argument \n\n last limit "
    blocks = [ExtractedBlock(order=i, text=value, bbox=[1, i*20, 90, i*20+15])
              for i, value in enumerate([" first argument ", " second argument ", " last limit "])]
    chunks = list(_passage_chunks(blocks, text, target_size=20))
    assert len(chunks) == 3
    assert all(text[start:end] == value for _, value, start, end, _ in chunks)
    blocks[1].text = "Provider blocks disagree with page text"
    assert list(_passage_chunks(blocks, text)) == [(0, text, 0, len(text), [])]


def test_public_page_text_range_rejects_legacy_alignment_without_rewriting_text():
    from catalog.services.text import page_text_range
    from catalog.services.discovery_sessions import _deduplicate
    text = "📚第一段\n\n第二段"
    assert page_text_range(text, "第二段", 6, 9) == {"start": 6, "end": 9, "unit": "unicode_codepoints"}
    assert page_text_range(text, "第二段", 5, 8) is None
    assert page_text_range(text, "第二段", True, 9) is None
    assert page_text_range(text, "第二段", 6, 100) is None
    # Legacy offsets can falsely overlap in a different joined string.
    rows = [{"id": str(i), "asset_id": "asset", "pdf_page": 1, "excerpt": value,
             "start_offset": 0, "end_offset": 100, "page_text_range": None}
            for i, value in enumerate(["First distinct evidence", "Second distinct evidence"])]
    assert _deduplicate(rows) == rows
