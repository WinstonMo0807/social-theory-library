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
WORK_IMAGE_SLOTS = {
    "cover": {"field": "cover", "relation": "cover_rendition", "kind": "cover", "snapshot": "cover_media", "route": "cover"},
    "recommendation": {"field": "recommendation_image", "relation": "recommendation_rendition", "kind": "hero", "snapshot": "recommendation_media", "route": "recommendation-image"},
}


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


def work_media_snapshot(work, *, slot="cover", primary=None):
    """A publication captures exact rendition IDs; later crop edits are drafts."""
    config = WORK_IMAGE_SLOTS[slot]
    if primary is None and not getattr(work, f"{config['relation']}_id"):
        return None
    primary = primary if primary is not None else getattr(work, config["relation"])
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
                         "url": f"/api/catalog/works/{work.pk}/{config['route']}/?rendition={row.pk}"} for row in sorted(by_width.values(), key=lambda row: row.width)],
    }


def cover_media_snapshot(work, *, primary=None):
    return work_media_snapshot(work, slot="cover", primary=primary)


def preview_work_media(work, *, slot, preview=None):
    config = WORK_IMAGE_SLOTS[slot]
    identifier = (preview or {}).get(config["relation"], getattr(work, f"{config['relation']}_id"))
    primary = MediaRendition.objects.select_related("media").filter(pk=identifier, kind=config["kind"]).first() if identifier else None
    return work_media_snapshot(work, slot=slot, primary=primary) if primary else None


def validate_work_image_patch(work, patch):
    """Keep file-path compatibility paired with an exact, valid rendition."""
    from catalog.contracts.fields import FIELD_LABELS

    for config in WORK_IMAGE_SLOTS.values():
        field, relation = config["field"], config["relation"]
        selected = None
        if patch.get(relation):
            selected = MediaRendition.objects.filter(pk=patch[relation], kind=config["kind"]).first()
            if selected is None or not selected.file.storage.exists(selected.file.name):
                raise MediaValidationError(f"所选{FIELD_LABELS[field]}不存在或不能读取。")
            patch.setdefault(field, selected.file.name)
        elif relation in patch:
            patch.setdefault(field, "")
        if field not in patch:
            continue
        name = str(patch[field] or "")
        current = getattr(work, field)
        legacy_prefix = f"public/{'covers' if field == 'cover' else 'recommendations'}/editorial/{work.pk}/"
        if selected is not None and name != selected.file.name:
            raise MediaValidationError(f"{FIELD_LABELS[field]}文件与所选媒体版本不一致。")
        if selected is None and name and name != current.name and (
            not name.startswith(legacy_prefix) or ".." in name.split("/") or "\\" in name or not current.storage.exists(name)
        ):
            raise MediaValidationError(f"{FIELD_LABELS[field]}必须来自当前作品已保存的图片选择。")
        patch[field] = name
        if selected is None and name != current.name:
            patch[relation] = None


def select_work_image(edition_id, media_id, *, slot, actor, automatic=False, expected_work_id=None):
    config = WORK_IMAGE_SLOTS[slot]
    # Prepared media persists independently from a failed catalog decision.
    # One transaction keeps every size on the same immutable metadata version.
    with transaction.atomic():
        variants = {width: build_rendition(media_id, width=width, kind=config["kind"]) for width in RENDITION_WIDTHS} if media_id else {}
    return _select_prepared_work_image(edition_id, variants.get(640), slot=slot, actor=actor, automatic=automatic, expected_work_id=expected_work_id)


@transaction.atomic
def _select_prepared_work_image(edition_id, primary, *, slot, actor, automatic, expected_work_id):
    from catalog.contracts.fields import FIELD_LABELS
    from catalog.models import CatalogFieldDecision, Edition, Work
    from catalog.services.editorial_revision import save_workflow_editorial_revision
    from catalog.services.field_decisions import record_edition_field_decision

    edition = Edition.objects.select_for_update().get(pk=edition_id)
    if expected_work_id is not None and str(edition.work_id) != str(expected_work_id):
        raise MediaValidationError("版本对应的作品已变化，请重新进入编目工作台。")
    work = Work.objects.select_for_update().get(pk=edition.work_id)
    config = WORK_IMAGE_SLOTS[slot]
    field, relation = config["field"], config["relation"]
    published = work.editions.filter(state="published").exists()
    if automatic and (published or CatalogFieldDecision.objects.filter(
        edition=edition, field_name=field, status__in=["confirmed", "not_applicable"],
    ).exists()):
        return {"saved": False, "edition_id": str(edition.pk)}
    media_id = primary.media_id if primary else None
    name = primary.file.name if primary else ""
    revision = None
    if published:
        revision = save_workflow_editorial_revision(
            work_id=work.pk, section_patch={relation: str(primary.pk) if primary else None, field: name}, actor=actor,
            change_note=f"更新{FIELD_LABELS[field]}选择，等待正式发布",
        )
    else:
        setattr(work, relation, primary)
        setattr(work, field, name)
        work.save(update_fields=[relation, field, "updated_at"])
    record_edition_field_decision(edition, field, value=name, status="suggested" if automatic else "confirmed" if primary else "not_applicable", actor=actor,
                                  provenance={"source": "media_library", "media_id": str(media_id) if media_id else None,
                                              "canonical_write_deferred": revision is not None,
                                              "editorial_revision_id": str(revision.pk) if revision else None})
    return {"saved": True, "edition_id": str(edition.pk), "media_id": str(media_id) if media_id else None,
            "editorial_revision_id": str(revision.pk) if revision else None,
            "canonical_write_deferred": revision is not None,
            "workbench_url": f"/admin/library/works/{work.pk}?edition={edition.pk}#work"}


def select_work_cover(edition_id, media_id, *, actor):
    return select_work_image(edition_id, media_id, slot="cover", actor=actor)
