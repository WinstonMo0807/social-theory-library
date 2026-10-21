from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
import tempfile

from django.core.files import File
from django.db import transaction
from django.utils import timezone

from catalog.models import Asset, Page
from catalog.services.page_geometry import normalized_bbox, validated_geometry

from .files import materialize_field_file, safe_component, sha256_file, validate_pdf_structure


if TYPE_CHECKING:
    import fitz


class OcrPdfValidationError(RuntimeError):
    pass


def _scaled_rectangle(block_bbox, source_page: Page, pdf_page) -> fitz.Rect | None:
    import fitz
    geometry = validated_geometry(source_page.geometry, source_page=pdf_page)
    coordinates = normalized_bbox(block_bbox, geometry)
    if not coordinates:
        return None
    displayed = pdf_page.rect
    rectangle = fitz.Rect(
        displayed.x0 + coordinates[0] * displayed.width,
        displayed.y0 + coordinates[1] * displayed.height,
        displayed.x0 + coordinates[2] * displayed.width,
        displayed.y0 + coordinates[3] * displayed.height,
    ) * pdf_page.derotation_matrix
    return None if rectangle.is_empty else rectangle


def _insert_invisible_text(pdf_page, rectangle: fitz.Rect, text: str) -> bool:
    import fitz
    text = str(text or "").replace("\x00", "").strip()
    if not text:
        return False
    displayed = rectangle * pdf_page.rotation_matrix
    font_size = max(4, min(18, displayed.height * 0.72))
    result = pdf_page.insert_textbox(
        rectangle,
        text,
        fontname="china-s",
        fontsize=font_size,
        lineheight=1,
        render_mode=3,
        overlay=True,
        rotate=pdf_page.rotation,
    )
    if result >= 0:
        return True
    # OCR boxes can be slightly tighter than the font metrics. Invisible text
    # may safely use a smaller baseline fallback while preserving copy/search.
    pdf_page.insert_text(
        fitz.Point(displayed.x0, max(displayed.y0 + font_size, displayed.y1 - 1)) * pdf_page.derotation_matrix,
        text.replace("\n", " "),
        fontname="china-s",
        fontsize=max(3, min(font_size, displayed.height * 0.55)),
        render_mode=3,
        overlay=True,
        rotate=pdf_page.rotation,
    )
    return True


def _write_searchable_copy(source_path: Path, target_path: Path, asset: Asset) -> dict:
    import fitz
    document = fitz.open(str(source_path))
    inserted_blocks = 0
    inserted_pages = 0
    unlocated_blocks = 0
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
                    unlocated_blocks += 1
                    continue
                if _insert_invisible_text(pdf_page, rectangle, block.text):
                    page_insertions += 1
                    inserted_blocks += 1
            if page_insertions:
                inserted_pages += 1
        if inserted_blocks == 0:
            raise OcrPdfValidationError("OCR 正文已保留，但文字块缺少与源 PDF 相符的坐标，未生成定位不可靠的 OCR 下载副本。")
        document.save(str(target_path), garbage=4, deflate=True)
    finally:
        document.close()
    return {"inserted_blocks": inserted_blocks, "inserted_pages": inserted_pages,
            "unlocated_blocks": unlocated_blocks, "geometry_schema": 1,
            "geometry_status": "partial" if unlocated_blocks else "validated"}


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
    staging = bool(asset.text_revision and not asset.is_current)

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
            text_revision=asset.text_revision if staging else 0,
        ).first()
        if existing is not None:
            if staging:
                return existing
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
            is_current=not staging,
            version=version,
            text_revision=asset.text_revision if staging else 0,
            source_asset=asset if staging else asset.source_asset or asset,
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
        if not staging:
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
