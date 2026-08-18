from __future__ import annotations

from pathlib import Path
import tempfile

import fitz
from django.core.files import File
from django.db import transaction
from django.utils import timezone

from catalog.models import Asset, Page

from .files import materialize_field_file, safe_component, sha256_file, validate_pdf_structure


class OcrPdfValidationError(RuntimeError):
    pass


def _scaled_rectangle(block_bbox, source_page: Page, pdf_page) -> fitz.Rect | None:
    if len(block_bbox) != 4:
        return None
    try:
        rectangle = fitz.Rect([float(value) for value in block_bbox])
    except (TypeError, ValueError):
        return None
    if rectangle.is_empty or rectangle.is_infinite:
        return None
    scale_x = float(pdf_page.rect.width) / max(float(source_page.width), 1)
    scale_y = float(pdf_page.rect.height) / max(float(source_page.height), 1)
    rectangle = fitz.Rect(
        rectangle.x0 * scale_x,
        rectangle.y0 * scale_y,
        rectangle.x1 * scale_x,
        rectangle.y1 * scale_y,
    ) & pdf_page.rect
    return None if rectangle.is_empty else rectangle


def _insert_invisible_text(pdf_page, rectangle: fitz.Rect, text: str) -> bool:
    text = str(text or "").replace("\x00", "").strip()
    if not text:
        return False
    font_size = max(4, min(18, rectangle.height * 0.72))
    result = pdf_page.insert_textbox(
        rectangle,
        text,
        fontname="china-s",
        fontsize=font_size,
        lineheight=1,
        render_mode=3,
        overlay=True,
    )
    if result >= 0:
        return True
    # OCR boxes can be slightly tighter than the font metrics. Invisible text
    # may safely use a smaller baseline fallback while preserving copy/search.
    pdf_page.insert_text(
        fitz.Point(rectangle.x0, max(rectangle.y0 + font_size, rectangle.y1 - 1)),
        text.replace("\n", " "),
        fontname="china-s",
        fontsize=max(3, min(font_size, rectangle.height * 0.55)),
        render_mode=3,
        overlay=True,
    )
    return True


def _write_searchable_copy(source_path: Path, target_path: Path, asset: Asset) -> dict:
    document = fitz.open(str(source_path))
    inserted_blocks = 0
    inserted_pages = 0
    try:
        if document.page_count != asset.page_count:
            raise OcrPdfValidationError(
                f"源 PDF 页数 {document.page_count} 与馆藏记录 {asset.page_count} 不一致。"
            )
        pages = asset.pages.filter(
            text_source__in=[Page.TextSource.OCR, Page.TextSource.HYBRID],
        ).prefetch_related("blocks").order_by("index")
        for source_page in pages:
            if source_page.index < 1 or source_page.index > document.page_count:
                continue
            pdf_page = document[source_page.index - 1]
            page_insertions = 0
            for block in source_page.blocks.all().order_by("order"):
                rectangle = _scaled_rectangle(block.bbox, source_page, pdf_page)
                if rectangle is None:
                    continue
                if _insert_invisible_text(pdf_page, rectangle, block.text):
                    page_insertions += 1
                    inserted_blocks += 1
            if page_insertions:
                inserted_pages += 1
        if inserted_blocks == 0:
            raise OcrPdfValidationError("OCR 已完成，但没有可写入 PDF 的文字块。")
        document.save(str(target_path), garbage=4, deflate=True)
    finally:
        document.close()
    return {"inserted_blocks": inserted_blocks, "inserted_pages": inserted_pages}


@transaction.atomic
def create_searchable_ocr_pdf(
    asset: Asset,
    *,
    processor: str,
    processor_version: str,
) -> Asset:
    """Create a versioned derivative without replacing the reader anchor."""

    # Only the normalized source row coordinates derivative version creation.
    # source_asset is nullable provenance and must not be included in FOR UPDATE.
    asset = (
        Asset.objects.select_for_update(of=("self",))
        .select_related("edition", "source_asset")
        .get(pk=asset.pk)
    )
    if asset.kind != Asset.Kind.NORMALIZED or asset.status != Asset.Status.READY:
        raise OcrPdfValidationError("只有已验证的规范阅读 PDF 可以生成 OCR 下载副本。")

    source_path, cleanup_source = materialize_field_file(asset.file)
    temporary = tempfile.NamedTemporaryFile(prefix="library-ocr-pdf-", suffix=".pdf", delete=False)
    temporary_path = Path(temporary.name)
    temporary.close()
    saved_name = ""
    try:
        details = _write_searchable_copy(source_path, temporary_path, asset)
        page_count = validate_pdf_structure(temporary_path, max(asset.page_count, 1))
        if page_count != asset.page_count:
            raise OcrPdfValidationError("OCR PDF 验证后的页数与原文件不一致。")
        digest, byte_size = sha256_file(temporary_path)
        existing = Asset.objects.filter(
            edition=asset.edition,
            kind=Asset.Kind.OCR_PDF,
            sha256=digest,
        ).first()
        if existing is not None:
            Asset.objects.filter(
                edition=asset.edition,
                kind=Asset.Kind.OCR_PDF,
                is_current=True,
            ).exclude(pk=existing.pk).update(is_current=False, updated_at=timezone.now())
            existing.is_current = True
            existing.status = Asset.Status.READY
            existing.validation_status = Asset.ValidationStatus.VALID
            existing.validation_details = {
                **(existing.validation_details or {}),
                **details,
                "validated_at": timezone.now().isoformat(),
            }
            existing.save(
                update_fields=[
                    "is_current",
                    "status",
                    "validation_status",
                    "validation_details",
                    "updated_at",
                ]
            )
            return existing

        latest_version = asset.edition.assets.filter(
            kind=Asset.Kind.OCR_PDF,
        ).order_by("-version").values_list("version", flat=True).first()
        version = (latest_version or 0) + 1
        derivative = Asset(
            edition=asset.edition,
            kind=Asset.Kind.OCR_PDF,
            sha256=digest,
            byte_size=byte_size,
            page_count=page_count,
            status=Asset.Status.READY,
            extraction_method=processor,
            is_current=True,
            version=version,
            source_asset=asset.source_asset or asset,
            processor=processor,
            processor_version=processor_version,
            validation_status=Asset.ValidationStatus.VALID,
            validation_details={
                **details,
                "source_normalized_asset_id": str(asset.id),
                "visual_source_sha256": asset.sha256,
                "validated_at": timezone.now().isoformat(),
            },
        )
        filename = (
            f"{safe_component(Path(asset.edition.canonical_filename or asset.file.name).stem)}"
            f".ocr.v{version}.pdf"
        )
        with temporary_path.open("rb") as handle:
            derivative.file.save(filename, File(handle), save=False)
        saved_name = derivative.file.name
        derivative.save()
        Asset.objects.filter(
            edition=asset.edition,
            kind=Asset.Kind.OCR_PDF,
            is_current=True,
        ).exclude(pk=derivative.pk).update(is_current=False, updated_at=timezone.now())
        return derivative
    except Exception:
        if saved_name:
            try:
                asset.file.storage.delete(saved_name)
            except Exception:
                pass
        raise
    finally:
        temporary_path.unlink(missing_ok=True)
        if cleanup_source:
            cleanup_source()
