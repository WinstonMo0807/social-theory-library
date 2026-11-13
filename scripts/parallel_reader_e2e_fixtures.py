"""Real, synthetic PDF sources for the disposable parallel Reader acceptance run.

Only call seed_parallel_reader() from the isolated E2E fixture runner. This file
does not start a server, apply migrations, run OCR, or fabricate extracted rows.
The long reference pages exercise more than 20 extractor-created passages.
Nothing here has been executed during the development phase.
"""
from hashlib import sha256
import json
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone


IDS = {
    "left_work": "41300000-0000-4000-8000-000000000100",
    "left_edition": "41300000-0000-4000-8000-000000000101",
    "left_original": "41300000-0000-4000-8000-000000000102",
    "left_asset": "41300000-0000-4000-8000-000000000103",
    "right_work": "41300000-0000-4000-8000-000000000200",
    "right_edition": "41300000-0000-4000-8000-000000000201",
    "right_original": "41300000-0000-4000-8000-000000000202",
    "right_asset": "41300000-0000-4000-8000-000000000203",
    "scan_edition": "41300000-0000-4000-8000-000000000301",
    "scan_original": "41300000-0000-4000-8000-000000000302",
    "scan_asset": "41300000-0000-4000-8000-000000000303",
}
LEFT_MARKERS = [f"PARALLEL LEFT SEGMENT {index:02d}" for index in range(1, 26)]
RIGHT_MARKERS = ["INSERTED NOTE 01", "INSERTED NOTE 02"] + [
    f"PARALLEL RIGHT SEGMENT {index:02d}" for index in range(1, 26)
]


def _isolated_media():
    database = settings.DATABASES["default"]
    database_path = Path(database["NAME"]).resolve()
    media = Path(settings.MEDIA_ROOT).resolve()
    if (database["ENGINE"] != "django.db.backends.sqlite3"
            or not database_path.parent.name.startswith("stl-v305-e2e-")
            or database_path.name != "local_fixture.sqlite3"
            or media != database_path.parent / "media"):
        raise RuntimeError("Parallel fixtures require the disposable E2E SQLite database and its own media directory")
    return media


def copy_fixture_pdf(original, edition, asset_id, label):
    """A distinct synthetic file, with its real checksum, for another edition."""
    media = _isolated_media()
    from catalog.models import Asset
    source = Path(original.file.path).resolve()
    if not source.is_relative_to(media):
        raise RuntimeError("Fixture source is outside the disposable media directory")
    # PDF comments after EOF do not change pages/text. Do not spoof the digest
    # or weaken the real (sha256, kind) uniqueness constraint for test records.
    content = source.read_bytes() + f"\n% isolated fixture {asset_id}\n".encode("ascii")
    asset = Asset.objects.create(id=asset_id, edition=edition, kind="normalized",
        status="ready", validation_status="valid", access_status="public",
        sha256=sha256(content).hexdigest(), byte_size=len(content),
        page_count=original.page_count, is_current=True, original_filename=label)
    asset.file.save(label, ContentFile(content), save=True)
    return asset


def _paragraph(marker):
    # Every printed block exceeds the extractor's 700-character merge threshold.
    # These are labelled fixture sentences, not academic claims or test results.
    return f"{marker}. " + " ".join(
        f"Fixture sentence {index:02d} belongs to this printed block and describes only synthetic reading material."
        for index in range(1, 10)
    )


def _native_pdf(markers, *, introductory_page=False):
    import fitz

    document = fitz.open()
    try:
        if introductory_page:
            page = document.new_page(width=595, height=842)
            remaining = page.insert_textbox(fitz.Rect(50, 150, 545, 720),
                _paragraph("PARALLEL RIGHT INTRODUCTION"), fontsize=11)
            if remaining < 0:
                raise RuntimeError("Parallel fixture introduction did not fit its printed page")
        # A clearly synthetic foldout gives 25/27 actual long paragraphs enough
        # space. Body text is never placed over other text to inflate extraction.
        page = document.new_page(width=820, height=180 + 140 * len(markers))
        for index, marker in enumerate(markers):
            top = 90 + 140 * index
            remaining = page.insert_textbox(fitz.Rect(50, top, 770, top + 118),
                _paragraph(marker), fontsize=10)
            if remaining < 0:
                raise RuntimeError(f"Parallel fixture block did not fit: {marker}")
        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()


def _scanned_pdf():
    import fitz

    source, scanned = fitz.open(), fitz.open()
    try:
        page = source.new_page(width=595, height=842)
        remaining = page.insert_textbox(fitz.Rect(50, 150, 545, 720),
            _paragraph("PARALLEL IMAGE ONLY SCAN"), fontsize=11)
        if remaining < 0:
            raise RuntimeError("Parallel scan image source did not fit")
        pixels = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).tobytes("png")
        image_page = scanned.new_page(width=595, height=842)
        image_page.insert_image(image_page.rect, stream=pixels)
        return scanned.tobytes(garbage=4, deflate=True)
    finally:
        source.close()
        scanned.close()


def _publish_pdf(edition, key, content, media, *, expected_pages, fulltext):
    from catalog.models import Asset, CatalogPublicationRevision
    from catalog.services.document_intelligence import synchronize_native_extraction
    from catalog.services.knowledge_publication import catalog_snapshot
    from ingestion.services.extract import extract_native_pages, ocr_required_page_indexes, persist_pages

    digest = sha256(content).hexdigest()
    original = None
    for kind, suffix in (("original", "original"), ("normalized", "asset")):
        asset = Asset.objects.create(id=IDS[f"{key}_{suffix}"], edition=edition, kind=kind,
            source_asset=original, sha256=digest, byte_size=len(content), page_count=expected_pages,
            status="ready", validation_status="valid", access_status="public",
            mime_type="application/pdf", original_filename=f"parallel-{key}.pdf")
        filename = f"parallel-{key}.pdf"
        generated = asset.file.field.generate_filename(asset, filename)
        if not Path(asset.file.storage.path(generated)).resolve().is_relative_to(media):
            raise RuntimeError("Parallel fixture storage escaped its disposable media directory")
        asset.file.save(filename, ContentFile(content), save=True)
        if kind == "original":
            original = asset
    pages, needs_ocr = extract_native_pages(asset.file.path)
    if len(pages) != expected_pages or needs_ocr == fulltext:
        raise RuntimeError("Parallel fixture native text/OCR state does not match its intended source")
    if not fulltext and any(page.text.strip() for page in pages):
        raise RuntimeError("The image-only fixture unexpectedly contains a selectable text layer")
    asset.validation_details = {**(asset.validation_details or {}),
        "ocr_required_page_indexes": ocr_required_page_indexes(pages)}
    asset.save(update_fields=["validation_details", "updated_at"])
    persist_pages(asset, pages)
    interpreted = synchronize_native_extraction(asset, schedule_claims=False, schedule_outline=False)
    document_revision = asset.document_revisions.get(pk=interpreted["revision_id"])
    snapshot, related = catalog_snapshot(edition, content_asset_id=asset.pk)
    current = snapshot["document"]
    if (current["asset_id"] != str(asset.pk)
            or current["document_revision_id"] != str(document_revision.pk)
            or bool(current["quality_ready"]) != fulltext):
        raise RuntimeError("Parallel fixture did not obtain its intended real publication qualification")
    now = timezone.now()
    revision = CatalogPublicationRevision.objects.create(edition=edition, revision=1, status="active",
        metadata_ready=True, fulltext_ready=fulltext, reader_asset=asset, document_revision=document_revision,
        snapshot=snapshot, related_entities=related, changed_fields=["catalog_publish"],
        provenance={"source": "isolated-parallel-reader-fixture"},
        content_fingerprint=sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True,
            separators=(",", ":")).encode("utf-8")).hexdigest(), activated_at=now)
    edition.active_catalog_revision = revision
    edition.metadata_ready_at = now
    edition.fulltext_ready_at = now if fulltext else None
    edition.published_at = edition.first_published_at = edition.last_published_at = now
    edition.save(update_fields=["active_catalog_revision", "metadata_ready_at", "fulltext_ready_at",
        "published_at", "first_published_at", "last_published_at", "updated_at"])
    return asset, document_revision


def _verify_segments(asset, document_revision, page_index, markers):
    from catalog.models import EvidenceSpan

    page = asset.pages.get(index=page_index)
    passages = list(page.passages.order_by("order"))
    if len(passages) != len(markers):
        raise RuntimeError(f"Expected {len(markers)} real extracted passages on fixture page {page_index}; got {len(passages)}")
    output = []
    for passage, marker in zip(passages, markers):
        if (not passage.text.startswith(marker)
                or page.text[passage.start_offset:passage.end_offset] != passage.text
                or not passage.bbox_union):
            raise RuntimeError(f"Extractor did not produce an exact located passage for {marker}")
        span = EvidenceSpan.objects.filter(document_revision=document_revision, page=page,
            passage=passage, is_stale=False).first()
        if (span is None or span.page_number != page_index or span.original_text != passage.text
                or span.content_hash != sha256((passage.normalized_text or passage.text).encode("utf-8")).hexdigest()):
            raise RuntimeError(f"Real document revision has no exact evidence span for {marker}")
        output.append({"marker": marker, "passage_id": str(passage.pk), "evidence_span_id": str(span.pk),
            "pdf_page": page_index, "content_hash": span.content_hash,
            "start_offset": span.start_offset, "end_offset": span.end_offset})
    return output


def seed_parallel_reader():
    media = _isolated_media()
    from catalog.models import Edition, Work

    # Never reset records or replace files from an earlier run. A failing seed
    # belongs to the disposable directory; create a fresh runner to try again.
    if (Work.objects.filter(pk__in=[IDS["left_work"], IDS["right_work"]]).exists()
            or Edition.objects.filter(pk__in=[IDS[f"{key}_edition"] for key in ("left", "right", "scan")]).exists()):
        raise RuntimeError("Parallel fixture identifiers already exist; use a fresh disposable E2E directory")
    with transaction.atomic():
        original = Work.objects.create(id=IDS["left_work"], title="并读隔离夹具·原作", language="en", document_type="report")
        translated = Work.objects.create(id=IDS["right_work"], title="并读隔离夹具·译作", language="en",
            document_type="report", translation_of=original)
        sources = {}
        for key, work, primary, label in (
            ("left", original, True, "合成原作·参考页 1"),
            ("right", translated, True, "合成译作·参考页 2"),
            ("scan", original, False, "合成扫描本·尚无文字"),
        ):
            edition = Edition.objects.create(id=IDS[f"{key}_edition"], work=work, is_primary=primary,
                state="published", public_slug=f"parallel-fixture-{key}", publication_year=2026,
                version_label=label, ocr_status="pending" if key == "scan" else "not_required")
            content = _scanned_pdf() if key == "scan" else _native_pdf(
                LEFT_MARKERS if key == "left" else RIGHT_MARKERS, introductory_page=key == "right")
            asset, document = _publish_pdf(edition, key, content, media,
                expected_pages=2 if key == "right" else 1, fulltext=key != "scan")
            sources[key] = {"asset_id": str(asset.pk), "edition_id": str(edition.pk),
                "document_revision_id": str(document.pk), "reference_page": 2 if key == "right" else 1}
            if key != "scan":
                sources[key]["segments"] = _verify_segments(asset, document, sources[key]["reference_page"],
                    LEFT_MARKERS if key == "left" else RIGHT_MARKERS)
        return sources
