"""Bounded image ingestion/renditions. Original bytes are never overwritten."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import json
import warnings

from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from PIL import Image, ImageOps, UnidentifiedImageError

from catalog.models import MediaAsset, MediaRendition
from ingestion.models import AuditEvent


MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 24_000_000
MIME_TYPES = {"JPEG": ("image/jpeg", {".jpg", ".jpeg"}), "PNG": ("image/png", {".png"}), "WEBP": ("image/webp", {".webp"})}
RENDITION_WIDTHS = (320, 640, 1280)
MEDIA_SOURCE_TYPES = MediaAsset.SourceType.choices
RENDITION_KINDS = ("cover", "portrait", "hero", "card", "thumbnail")
METADATA_FIELDS = ("source_type", "source_url", "source_label", "rights", "license", "credit", "alt_text", "focal_x", "focal_y")
PUBLIC_METADATA_FIELDS = ("alt_text", "source_label", "source_url", "rights", "license", "credit")


class MediaValidationError(ValueError):
    pass


def _inspect(data, filename, content_type):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                image_format = image.format
                if image_format not in MIME_TYPES or image.width * image.height > MAX_IMAGE_PIXELS:
                    raise MediaValidationError("仅支持不超过 2400 万像素的 JPEG、PNG 或 WebP。")
                expected_mime, suffixes = MIME_TYPES[image_format]
                if Path(filename).suffix.lower() not in suffixes or content_type != expected_mime:
                    raise MediaValidationError("文件内容、扩展名与声明类型不一致。")
                image.verify()
            with Image.open(BytesIO(data)) as image:
                oriented = ImageOps.exif_transpose(image)
                return expected_mime, oriented.width, oriented.height
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise MediaValidationError("图片损坏或尺寸超出安全限制。") from error


@transaction.atomic
def ingest_image(uploaded, *, actor, metadata=None):
    if uploaded.size > MAX_IMAGE_BYTES:
        raise MediaValidationError("图片不能超过 20 MB。")
    data = uploaded.read(MAX_IMAGE_BYTES + 1)
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise MediaValidationError("图片为空或超过 20 MB。")
    mime, width, height = _inspect(data, uploaded.name, uploaded.content_type)
    checksum = sha256(data).hexdigest()
    existing = MediaAsset.objects.filter(checksum=checksum).first()
    if existing:
        return existing, False
    metadata = dict(metadata or {})
    if set(metadata) - set(METADATA_FIELDS):
        raise MediaValidationError("包含不可修改的媒体字段。")
    row = MediaAsset(media_type=mime, width=width, height=height, checksum=checksum, byte_size=len(data), created_by=actor, **metadata)
    extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[mime]
    row.file.save(f"{uuid4().hex}{extension}", ContentFile(data), save=False)
    try:
        row.full_clean(validate_unique=False)
        try:
            with transaction.atomic():
                row.save()
        except IntegrityError:
            existing = MediaAsset.objects.filter(checksum=checksum).first()
            if existing is None:
                raise
            row.file.storage.delete(row.file.name)
            return existing, False
    except Exception:
        # Only the new unreferenced file created by this call, never an old
        # original or a user-provided path, can be removed on failed insertion.
        row.file.storage.delete(row.file.name)
        raise
    AuditEvent.objects.create(actor=actor, action="media.upload", object_type="MediaAsset", object_id=str(row.pk),
                              after={"checksum": checksum, "width": width, "height": height})
    return row, True


@transaction.atomic
def update_media_metadata(media_id, *, actor, metadata, expected_updated_at=None):
    if set(metadata) - set(METADATA_FIELDS):
        raise MediaValidationError("不能替换媒体原文件或身份。")
    row = MediaAsset.objects.select_for_update().get(pk=media_id)
    if expected_updated_at is not None and row.updated_at != expected_updated_at:
        raise MediaValidationError("媒体资料已由其他操作更新，请重新读取后再保存。")
    before = {name: getattr(row, name) for name in metadata}
    for name, value in metadata.items():
        setattr(row, name, value)
    row.full_clean()
    row.save(update_fields=[*metadata, "updated_at"])
    AuditEvent.objects.create(actor=actor, action="media.metadata", object_type="MediaAsset", object_id=str(row.pk),
                              before=before, after=dict(metadata))
    return row


@transaction.atomic
def build_rendition(media_id, *, width=640, kind="cover"):
    if width not in RENDITION_WIDTHS or kind not in RENDITION_KINDS:
        raise MediaValidationError("不支持的衍生图尺寸或用途。")
    media = MediaAsset.objects.select_for_update().get(pk=media_id)
    metadata = {name: getattr(media, name) for name in PUBLIC_METADATA_FIELDS}
    metadata_key = sha256(json.dumps(metadata, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    group = sha256(f"webp-v2:{kind}:{media.focal_x}:{media.focal_y}:{metadata_key}".encode()).hexdigest()
    key = sha256(f"{group}:{width}".encode()).hexdigest()
    existing = media.renditions.filter(variant_key=key).first()
    if existing:
        if not existing.group_key:
            existing.group_key = group
            existing.save(update_fields=["group_key", "updated_at"])
        return existing
    with media.file.open("rb") as source, Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert("RGBA" if image.mode in {"RGBA", "LA", "P"} else "RGB")
        if kind in {"portrait", "hero"}:
            ratio = 4 / 5 if kind == "portrait" else 16 / 9
            target_width = max(1, min(width, image.width, int(image.height * ratio)))
            image = ImageOps.fit(image, (target_width, max(1, round(target_width / ratio))), Image.Resampling.LANCZOS,
                                 centering=(media.focal_x, media.focal_y))
        else:
            image.thumbnail((width, width * 4), Image.Resampling.LANCZOS)
        output = BytesIO()
        image.save(output, format="WEBP", quality=82, method=4)
        data = output.getvalue()
        rendition = MediaRendition(media=media, variant_key=key, group_key=group, kind=kind, requested_width=width,
                                   width=image.width, height=image.height, checksum=sha256(data).hexdigest(), byte_size=len(data),
                                   metadata_snapshot=metadata)
    rendition.file.save(f"{media.pk}-{key}.webp", ContentFile(data), save=False)
    try:
        rendition.save()
    except Exception:
        rendition.file.storage.delete(rendition.file.name)
        raise
    return rendition


def cover_media_snapshot(work, *, primary=None):
    """A publication captures exact rendition IDs; later crop edits are drafts."""
    if primary is None and not work.cover_rendition_id:
        return None
    primary = primary if primary is not None else work.cover_rendition
    media = primary.media
    variants = media.renditions.filter(group_key=primary.group_key).order_by("requested_width") if primary.group_key else [primary]
    by_width = {row.width: row for row in variants}
    by_width[primary.width] = primary
    return {
        "media_id": str(media.pk), "primary_rendition_id": str(primary.pk),
        # Old local renditions without a captured statement stay blank until
        # explicitly reselected; do not invent historical attribution.
        **{name: primary.metadata_snapshot.get(name, "") for name in PUBLIC_METADATA_FIELDS},
        "renditions": [{"id": str(row.pk), "width": row.width, "height": row.height,
                         "url": f"/api/catalog/works/{work.pk}/cover/?rendition={row.pk}"} for row in sorted(by_width.values(), key=lambda row: row.width)],
    }


@transaction.atomic
def select_work_cover(edition_id, media_id, *, actor):
    from catalog.models import Edition, Work
    from catalog.services.editorial_revision import save_workflow_editorial_revision
    from catalog.services.field_decisions import record_edition_field_decision

    edition = Edition.objects.select_for_update().get(pk=edition_id)
    work = Work.objects.select_for_update().get(pk=edition.work_id)
    variants = {width: build_rendition(media_id, width=width, kind="cover") for width in RENDITION_WIDTHS}
    primary = variants[640]
    revision = None
    if work.editions.filter(state="published").exists():
        revision = save_workflow_editorial_revision(
            work_id=work.pk, section_patch={"cover_rendition": str(primary.pk), "cover": primary.file.name}, actor=actor,
            change_note="从媒体库选择封面，等待正式发布",
        )
    else:
        work.cover_rendition = primary
        work.cover = primary.file.name
        work.save(update_fields=["cover_rendition", "cover", "updated_at"])
    record_edition_field_decision(edition, "cover", value=primary.file.name, status="confirmed", actor=actor,
                                  provenance={"source": "media_library", "media_id": str(media_id), "canonical_write_deferred": revision is not None})
    return {"saved": True, "edition_id": str(edition.pk), "media_id": str(media_id),
            "editorial_revision_id": str(revision.pk) if revision else None,
            "workbench_url": f"/admin/library/works/{work.pk}?edition={edition.pk}#work"}
