"""Explicit public defaults for a Work's reader and download entry points."""

from __future__ import annotations

from uuid import UUID

from django.db import transaction

from catalog.models import Asset, Edition, Work
from catalog.services.publication_commands import catalog_publication_state
from common.capabilities import Capability, has_capability
from ingestion.models import AuditEvent


class EditionDefaultsError(ValueError):
    """A safe, actionable validation error for the admin defaults command."""


def _label(edition: Edition) -> str:
    parts = [edition.version_label, edition.publisher, str(edition.publication_year or "年代待补")]
    return " · ".join(str(value).strip() for value in parts if str(value or "").strip()) or "出版版本待补"


def _reader_ready(edition: Edition) -> bool:
    revision = edition.active_catalog_revision
    asset = getattr(revision, "reader_asset", None) if revision else None
    return bool(
        revision
        and revision.reader_asset_id
        and asset
        and asset.edition_id == edition.pk
        and asset.kind == Asset.Kind.NORMALIZED
        and asset.status == Asset.Status.READY
        and asset.validation_status == Asset.ValidationStatus.VALID
    )


def _option(edition: Edition) -> dict:
    publication = catalog_publication_state(edition)
    return {
        "id": str(edition.pk),
        "label": _label(edition),
        "version_label": edition.version_label,
        "publication_year": edition.publication_year,
        "publisher": edition.publisher,
        "is_primary": edition.is_primary,
        "public": bool(publication["catalog_revision_active"]),
        "public_state": publication["public_state"],
        "reader_ready": _reader_ready(edition),
        "download_ready": _reader_ready(edition),
    }


def _rows(work: Work) -> list[Edition]:
    return list(
        Edition.objects.filter(work=work)
        .select_related("active_catalog_revision", "active_catalog_revision__reader_asset")
        .order_by("-is_primary", "-publication_year", "created_at", "pk")
    )


def serialize_work_edition_defaults(work: Work) -> dict:
    rows = _rows(work)
    options = [_option(row) for row in rows]
    public_ids = {row["id"] for row in options if row["public"]}

    def selected(field: str, *, require_reader: bool = False) -> str | None:
        identifier = str(getattr(work, f"{field}_id", "") or "")
        if identifier in public_ids:
            option = next(row for row in options if row["id"] == identifier)
            if not require_reader or option["reader_ready"]:
                return identifier
        primary = next((row for row in options if row["is_primary"] and row["public"] and (not require_reader or row["reader_ready"])), None)
        return primary["id"] if primary else next((row["id"] for row in options if row["public"] and (not require_reader or row["reader_ready"])), None)

    return {
        "work_id": str(work.pk),
        "title": work.title,
        "reader_default_edition_id": str(work.reader_default_edition_id) if work.reader_default_edition_id else None,
        "download_default_edition_id": str(work.download_default_edition_id) if work.download_default_edition_id else None,
        "effective_reader_edition_id": selected("reader_default_edition", require_reader=True),
        "effective_download_edition_id": selected("download_default_edition", require_reader=True),
        "options": options,
        "detail": "未单独选择时，读者入口跟随主版本；保存后分别控制在线阅读和下载默认版本。",
        "can_edit": True,
    }


def _parse_id(value, field: str) -> UUID | None:
    if value in (None, ""):
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError) as error:
        raise EditionDefaultsError(f"{field}不是有效的出版版本标识。") from error


@transaction.atomic
def update_work_edition_defaults(
    work_id,
    *,
    reader_default_edition_id,
    download_default_edition_id,
    actor,
    request_id: str,
) -> dict:
    if not has_capability(actor, Capability.PUBLISH_WORK):
        raise EditionDefaultsError("当前账户没有修改读者默认出版版本的权限。")
    work = Work.objects.select_for_update().get(pk=work_id)
    reader_id = _parse_id(reader_default_edition_id, "在线阅读默认版本")
    download_id = _parse_id(download_default_edition_id, "下载默认版本")
    rows = {row.pk: row for row in _rows(work)}

    def validate(identifier: UUID | None, field: str) -> None:
        if identifier is None:
            return
        edition = rows.get(identifier)
        if edition is None:
            raise EditionDefaultsError(f"{field}不属于《{work.title}》。")
        publication = catalog_publication_state(edition)
        if not publication["catalog_revision_active"]:
            raise EditionDefaultsError(f"{field}尚未有有效的公开版本，不能作为读者默认入口。")
        if not _reader_ready(edition):
            raise EditionDefaultsError(f"{field}没有通过验证的阅读文件，暂不能作为在线阅读或下载默认版本。")

    validate(reader_id, "在线阅读默认版本")
    validate(download_id, "下载默认版本")
    before = {
        "reader_default_edition_id": str(work.reader_default_edition_id) if work.reader_default_edition_id else None,
        "download_default_edition_id": str(work.download_default_edition_id) if work.download_default_edition_id else None,
    }
    work.reader_default_edition_id = reader_id
    work.download_default_edition_id = download_id
    work.save(update_fields=["reader_default_edition", "download_default_edition", "updated_at"])
    after = {
        "reader_default_edition_id": str(reader_id) if reader_id else None,
        "download_default_edition_id": str(download_id) if download_id else None,
    }
    AuditEvent.objects.create(
        actor=actor,
        action="catalog.work_edition_defaults.updated",
        object_type="catalog.Work",
        object_id=str(work.pk),
        before=before,
        after={**after, "request_id": request_id, "public_behavior_changed": True},
        request_id=request_id,
    )
    return {**serialize_work_edition_defaults(work), "request_id": request_id, "saved": True, "before": before}
