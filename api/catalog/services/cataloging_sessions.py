"""Process ownership for intake, manual cataloguing and existing edition edits."""

from django.contrib.auth import get_user_model
from django.db import transaction

from catalog.models import CatalogingSession, DocumentType, Edition, Work
from ingestion.models import UploadItem


OPEN_STATUSES = (
    CatalogingSession.Status.DRAFTING, CatalogingSession.Status.REVIEWING,
    CatalogingSession.Status.READY, CatalogingSession.Status.PUBLISHING,
)


class CatalogingSessionConflict(ValueError):
    pass


@transaction.atomic
def open_cataloging_session(*, actor, edition_id=None, upload_item_id=None,
                            source_type="existing", title="", document_type="book",
                            language="zh-CN", request_key=None):
    """Open/reuse one process; never synthesize an UploadItem for metadata."""
    if source_type not in CatalogingSession.SourceType.values:
        raise ValueError("未知的编目来源。")
    if document_type not in DocumentType.values:
        raise ValueError("未知的文献类型。")
    if actor is None or not actor.pk:
        raise ValueError("编目会话需要记录创建者。")
    if request_key is not None:
        # Serialize repeat submissions before creating Work/Edition, including
        # the absent-key case. Only this actor's explicit create is locked.
        get_user_model().objects.select_for_update().get(pk=actor.pk)
        existing = CatalogingSession.objects.filter(created_by=actor, request_key=request_key).first()
        if existing:
            if (existing.source_type != source_type
                    or (edition_id and str(existing.edition_id) != str(edition_id))
                    or (upload_item_id and str(existing.upload_item_id) != str(upload_item_id))):
                raise CatalogingSessionConflict("该请求编号已用于其他编目会话。")
            return existing, False
    item = None
    if upload_item_id:
        item = UploadItem.objects.get(pk=upload_item_id)
        if edition_id and str(item.edition_id) != str(edition_id):
            raise CatalogingSessionConflict("上传记录与指定版本不一致。")
        edition_id = item.edition_id
        source_type = CatalogingSession.SourceType.UPLOAD
    elif source_type == CatalogingSession.SourceType.UPLOAD:
        raise ValueError("上传编目需要真实上传记录。")

    edition = None
    if edition_id:
        edition = Edition.objects.select_for_update(of=("self",)).get(pk=edition_id)
    elif source_type in {CatalogingSession.SourceType.MANUAL, CatalogingSession.SourceType.IMPORT}:
        work = Work.objects.create(title=title.strip(), document_type=document_type, language=language)
        edition = Edition.objects.create(work=work, publication_mode=Edition.PublicationMode.BIBLIOGRAPHIC)
        if source_type == CatalogingSession.SourceType.MANUAL:
            from catalog.services.field_decisions import record_edition_field_decision
            for name, value in {"title": title.strip(), "document_type": document_type, "language": language}.items():
                if value:
                    record_edition_field_decision(edition, name, value=value, status="confirmed", actor=actor,
                                                 provenance={"source": "manual_catalog_creation"})
    elif item is None:
        raise ValueError("编辑已有馆藏需要指定版本。")

    if item is not None:
        locked_item = UploadItem.objects.select_for_update(of=("self",)).get(pk=item.pk)
        if locked_item.edition_id != item.edition_id:
            raise CatalogingSessionConflict("上传记录正在建立或更换版本，请稍后重试。")
        item = locked_item
        previous_session = CatalogingSession.objects.select_for_update().filter(
            upload_item=item, status__in=OPEN_STATUSES,
        ).first()
        if previous_session is not None:
            if previous_session.edition_id is None and edition is not None:
                if CatalogingSession.objects.filter(edition=edition, status__in=OPEN_STATUSES).exclude(pk=previous_session.pk).exists():
                    raise CatalogingSessionConflict("此版本已有编目会话，请先核对上下文。")
                previous_session.edition = edition
                previous_session.base_public_revision_id = edition.active_catalog_revision_id
                previous_session.full_clean()
                previous_session.save(update_fields=["edition", "base_public_revision", "updated_at"])
            elif previous_session.edition_id != (edition.pk if edition else None):
                raise CatalogingSessionConflict("上传记录与已有编目会话的版本不一致。")
            return previous_session, False

    existing = CatalogingSession.objects.filter(status__in=OPEN_STATUSES)
    existing = existing.filter(edition=edition) if edition else existing.filter(upload_item=item)
    session = existing.first()
    if session is not None:
        # Preserve the original base revision and source. A later upload is
        # not allowed to silently steal another process's pending candidates.
        if item and session.upload_item_id not in {None, item.pk}:
            raise CatalogingSessionConflict("此版本已有另一上传记录的编目会话。")
        return session, False
    session = CatalogingSession(
        edition=edition, upload_item=item, source_type=source_type,
        base_public_revision_id=edition.active_catalog_revision_id if edition else None,
        created_by=actor, request_key=request_key,
    )
    session.full_clean()
    session.save()
    return session, True


@transaction.atomic
def abandon_cataloging_session(session_id, *, actor):
    session = CatalogingSession.objects.select_for_update().get(pk=session_id)
    if session.status == CatalogingSession.Status.ABANDONED:
        return session
    if session.status not in {CatalogingSession.Status.DRAFTING, CatalogingSession.Status.REVIEWING,
                              CatalogingSession.Status.READY}:
        raise CatalogingSessionConflict("发布中的或已发布的会话不能结束编辑。")
    # Ending a process never deletes its canonical draft, decisions or files.
    from ingestion.models import AuditEvent

    previous = session.status
    session.status = CatalogingSession.Status.ABANDONED
    session.save(update_fields=["status", "updated_at"])
    AuditEvent.objects.create(
        actor=actor, action="cataloging_session.abandon", object_type="cataloging_session",
        object_id=str(session.pk), before={"status": previous}, after={"status": session.status},
    )
    return session


def session_payload(session):
    return {
        "id": str(session.pk), "source_type": session.source_type, "status": session.status,
        "edition_id": str(session.edition_id) if session.edition_id else None,
        "work_id": str(session.work_id) if session.work_id else None,
        "upload_item_id": str(session.upload_item_id) if session.upload_item_id else None,
        "base_public_revision_id": str(session.base_public_revision_id) if session.base_public_revision_id else None,
        "created_at": session.created_at, "updated_at": session.updated_at,
        "workbench_url": f"/admin/cataloging/{session.pk}",
    }
