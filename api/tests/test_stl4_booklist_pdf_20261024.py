"""Deferred booklist PDF acceptance. Generates synthetic fixtures only when later run."""
from io import BytesIO
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image

from catalog.models import Edition
from catalog.services.media import build_rendition, ingest_image, media_rendition_snapshot
from reading import booklist_exports, booklist_pdf, booklists, research
from reading.booklist_views import ListExport
from reading.models import ReadingList, ReadingListItem
from tests.test_publication_invariants_v305 import published_edition

pytestmark = pytest.mark.django_db


def fixture(reader, admin, *, cover=True):
    edition, revision = published_edition("合成导出书目")
    Edition.objects.filter(pk=edition.pk).update(is_primary=True)
    revision.snapshot["edition"] = {"version_label": "合成验收版", "isbn": "9780000000000"}
    if cover:
        data = BytesIO()
        Image.new("RGB", (90, 120), (170, 80, 30)).save(data, format="PNG")
        media, _ = ingest_image(SimpleUploadedFile("synthetic-cover.png", data.getvalue(), content_type="image/png"), actor=admin)
        rendition = build_rendition(media.pk, width=320, kind="cover")
        revision.snapshot["work"]["cover_media"] = media_rendition_snapshot(rendition, lambda row: f"/synthetic/{row.pk}/")
    revision.save(update_fields=["snapshot"])
    row = ReadingList.objects.create(user=reader, title="合成书单", description="仅供未来隔离验收")
    ReadingListItem.objects.create(reading_list=row, work=edition.work, order=1)
    return row, edition, revision


def options(row, **extra):
    return {"expected_version": booklists.version(row), "format": "pdf", "include_notes": False,
        "include_progress": False, "include_covers": True, **extra}


def test_pdf_contains_only_the_selected_public_cover_and_version(tmp_path, reader_user, admin_user):
    import fitz
    with override_settings(MEDIA_ROOT=tmp_path):
        row, edition, revision = fixture(reader_user, admin_user)
        response = booklist_exports.download(SimpleNamespace(user=reader_user), row, options(row))
        with fitz.open(stream=response.content, filetype="pdf") as document:
            text = "".join(page.get_text() for page in document)
            assert "合成验收版" in text and "9780000000000" in text
            images = [image for page in document for image in page.get_images()]
            assert len(images) == 1
            pixels = document.extract_image(images[0][0])["image"]
            with Image.open(BytesIO(pixels)) as image:
                red, green, blue = image.convert("RGB").getpixel((10, 10))
                assert red > green > blue
        before = revision.snapshot
        revision.refresh_from_db()
        assert revision.snapshot == before
        without = booklist_exports.download(SimpleNamespace(user=reader_user), row, options(row, include_covers=False))
        with fitz.open(stream=without.content, filetype="pdf") as document:
            assert not any(page.get_images() for page in document)


def test_source_withdrawal_while_preparing_aborts_delivery(monkeypatch, reader_user, admin_user):
    row, edition, _ = fixture(reader_user, admin_user, cover=False)
    original = booklist_pdf.render
    def withdraw(*args, **kwargs):
        output = original(*args, **kwargs)
        Edition.objects.filter(pk=edition.pk).update(state="draft")
        return output
    monkeypatch.setattr(booklist_pdf, "render", withdraw)
    with pytest.raises(research.ResearchConflict):
        booklist_exports.download(SimpleNamespace(user=reader_user), row, options(row))


def test_missing_cover_is_labelled_and_non_pdf_image_option_is_rejected(reader_user, admin_user):
    import fitz
    row, _, _ = fixture(reader_user, admin_user, cover=False)
    response = booklist_exports.download(SimpleNamespace(user=reader_user), row, options(row))
    with fitz.open(stream=response.content, filetype="pdf") as document:
        assert "暂无公开封面" in "".join(page.get_text() for page in document)
    assert not ListExport(data=options(row, format="csv")).is_valid()


def test_booklist_export_is_owner_bound(api_client, reader_user, admin_user):
    row, _, _ = fixture(reader_user, admin_user, cover=False)
    api_client.force_authenticate(admin_user)
    api_client.credentials(HTTP_X_READER_OWNER=str(admin_user.pk))
    assert api_client.post(f"/api/reading/lists/{row.pk}/export/", options(row), format="json").status_code == 404
