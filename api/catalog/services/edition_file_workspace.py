"""Back-office file inventory and explicit reader selection over catalog revisions."""
from hashlib import sha256
import json
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db import DatabaseError, transaction
from django.db.models import Count
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from catalog.models import (Asset, CatalogingSession, CatalogPublicationRevision, Contribution, Edition,
                            EvidenceSnippet, KnowledgePublicationEvent, Work)
from common.capabilities import Capability, has_capability
from ingestion.models import AuditEvent, UploadItem
from distribution.models import CloudObject, CloudProvider
from .edition_file_intake import ACTIVE, format_capabilities, workspace_file
from .edition_files import EditionFileError

PAGE_SIZE = 20
IMPACT_NOTICE = "馆藏证据保留原文件与页定位，切换阅读文件不会自动迁移引用。私人笔记、书签与阅读位置仅提供不含身份的数量，不读取私人正文。"


def page_rows(rows, page, serialize):
    selected = Paginator(rows, PAGE_SIZE).get_page(page)
    return {"count": selected.paginator.count, "page": selected.number, "page_size": PAGE_SIZE,
            "results": [serialize(row) for row in selected.object_list]}


def reader(edition):
    revision = edition.active_catalog_revision
    return revision.reader_asset if (edition.state == "published" and revision
        and revision.edition_id == edition.pk and revision.status == "active" and revision.metadata_ready) else None


def selected_reader(edition):
    if edition.state == "published":
        return reader(edition)
    return edition.assets.filter(kind="normalized", is_current=True, status="ready", validation_status="valid").order_by("-version", "-created_at").first()


def impact_rows(edition, asset_id=None):
    rows = EvidenceSnippet.objects.filter(file__edition=edition).select_related("node", "file")
    return rows.filter(file_id=asset_id).order_by("file_id", "page_number", "id") if asset_id else rows.order_by("file_id", "page_number", "id")


def impact_row(row):
    return {"id": str(row.pk), "kind": "catalog_evidence", "title": (row.node.canonical_name_zh or row.node.canonical_name_en) if row.node_id else "馆藏知识证据",
        "asset_id": str(row.file_id), "file_page_index": row.page_number, "printed_page_label": row.printed_page_label,
        "status": row.review_status, "href": f"/admin/library/works/{row.work_id}?edition={row.file.edition_id}#knowledge"}


def impacts(edition, page=1, asset_id=None):
    if edition is None:
        return {"count": 0, "page": 1, "page_size": PAGE_SIZE, "results": [],
                "summary": {"catalog_evidence": 0, "reader_annotations": 0, "reader_bookmarks": 0, "reader_progress": 0},
                "notice": IMPACT_NOTICE, "export_url": ""}
    from reading.models import Annotation, Bookmark, ReadingProgress
    assets = edition.assets.filter(pk=asset_id) if asset_id else edition.assets.all()
    rows = impact_rows(edition, asset_id)
    result = page_rows(rows, page, impact_row)
    return {**result, "summary": {"catalog_evidence": rows.count(),
        "reader_annotations": Annotation.objects.filter(asset__in=assets).count(),
        "reader_bookmarks": Bookmark.objects.filter(asset__in=assets).count(),
        "reader_progress": ReadingProgress.objects.filter(asset__in=assets).count()}, "notice": IMPACT_NOTICE,
        "export_url": f"/catalog/admin/editions/{edition.pk}/files/impact.csv" + (f"?asset={asset_id}" if asset_id else "")}


def public_preparation(asset, can_publish=False):
    required = bool(settings.REQUIRE_CLOUD_FOR_PUBLICATION and asset.kind == "normalized")
    cloud = (asset.cloud_objects.filter(status="ready").first() or asset.cloud_objects.order_by("-updated_at").first()) if required else None
    status = ("not_prepared" if cloud.status == "deleted" else "syncing" if cloud.status == "deleting" else cloud.status) if cloud else "not_prepared" if required else "not_required"
    stale = bool(cloud and cloud.status in {"pending", "syncing"} and (timezone.now() - cloud.updated_at).total_seconds() >
        (settings.INGESTION_QUEUE_STALLED_SECONDS if status == "pending" else settings.INGESTION_STAGE_STALLED_SECONDS))
    can_prepare = bool(required and can_publish and asset.status == "ready" and asset.validation_status == "valid"
                       and (status in {"not_prepared", "failed", "deleted"} or stale))
    return {"required": required, "status": status, "can_prepare": can_prepare,
        "prepare_url": f"/catalog/admin/editions/{asset.edition_id}/files/{asset.pk}/prepare-public/" if can_prepare else "",
        "detail": "当前部署不要求云端副本。" if not required else "公开分发副本已就绪，采用或正式发布仍需明确确认。" if status == "ready" else
        "公开分发准备失败，可重试；原件与当前阅读文件保留。" if status == "failed" else
        "准备请求已保存，等待或正在传输。" if status in {"pending", "syncing"} else
        "文件仅保存在本地。明确准备后将传至公开分发存储；不会自动发布书目。"}


def file_row(asset, active, actors, can_publish, generatable=(), can_prepare=False):
    base = f"/catalog/admin/editions/{asset.edition_id}/files/{asset.pk}/content/"
    return {"id": str(asset.pk), "kind": asset.kind, "filename": asset.original_filename,
        "mime_type": asset.mime_type, "byte_size": asset.byte_size, "page_count": asset.page_count,
        "sha256": asset.sha256, "version": asset.version, "source_asset_id": str(asset.source_asset_id) if asset.source_asset_id else None,
        "created_at": asset.created_at, "updated_at": asset.updated_at, "created_by": actors.get(str(asset.source_asset_id or asset.pk), ""),
        "status": asset.status, "validation_status": asset.validation_status, "is_current": asset.is_current,
        "is_public_reader": bool(active and active.pk == asset.pk),
        "preview_url": base if asset.mime_type == "application/pdf" and asset.status == "ready" else "",
        "download_url": base + "?download=1", "rights_note": asset.rights_note, "access_status": asset.access_status,
        "generate_reader_url": f"/catalog/admin/editions/{asset.edition_id}/files/{asset.pk}/generate-reader/" if str(asset.pk) in generatable else "",
        "public_preparation": public_preparation(asset, can_prepare),
        "can_adopt": bool(can_publish and asset.kind == "normalized" and asset.status == "ready"
                          and asset.validation_status == "valid" and (not active or active.pk != asset.pk))}


def task_row(item, assets):
    metadata = workspace_file(item)
    original_id = metadata.get("original_asset_id") or (str(item.asset_id) if item.asset_id else None)
    normalized = next((asset for asset in assets if asset.kind == "normalized" and str(asset.source_asset_id) == original_id), None)
    return {"id": str(item.pk), "status": item.status, "dispatch_status": item.dispatch_status,
        "progress": item.stage_progress, "is_active": item.status in ACTIVE, "error_message": item.error_message,
        "retry_url": f"/ingestion/items/{item.pk}/retry/" if item.status == "failed" or item.dispatch_status == "failed" or (metadata and item.status == "needs_review") else "",
        "resume_url": f"/ingestion/items/{item.pk}/resume/" if item.status == "needs_review" and not metadata else "",
        "processing_href": f"/admin/intake/{item.pk}#file", "source_filename": item.source_filename,
        "original_asset_id": original_id, "reader_asset_id": str(normalized.pk) if normalized else None,
        "generate_reader": metadata.get("generate_reader", True), "action": metadata.get("action", item.batch.source),
        "created_at": item.created_at}


def state(work_id, actor, *, edition_id=None, page=1, impact_page=1, history_page=1, asset_id=None):
    work = Work.objects.get(pk=work_id)
    editions = list(work.editions.select_related("active_catalog_revision__reader_asset").order_by("-is_primary", "-publication_year", "id"))
    selected = next((row for row in editions if str(row.pk) == str(edition_id)), None) if edition_id else (editions[0] if editions else None)
    if edition_id and selected is None:
        raise EditionFileError("出版版本不属于当前作品。", status=404)
    if asset_id and (selected is None or not selected.assets.filter(pk=asset_id).exists()):
        raise EditionFileError("文件不属于当前出版版本。", status=404)
    counts = {(str(row["edition_id"]), row["kind"]): row["total"] for row in Asset.objects.filter(edition__work=work)
              .values("edition_id", "kind").annotate(total=Count("id"))}
    can_edit = has_capability(actor, Capability.EDIT_METADATA)
    can_publish = has_capability(actor, Capability.PUBLISH_WORK)
    public = reader(selected) if selected else None
    active = selected_reader(selected) if selected else None
    tasks = selected.uploaditem_set.exclude(status="deleted").select_related("batch__created_by").order_by("-created_at", "-id") if selected else UploadItem.objects.none()
    assets = list(selected.assets.order_by("-version", "kind", "id")) if selected else []
    actors = {str(row.asset_id): row.batch.created_by.display_name or row.batch.created_by.get_username() for row in tasks if row.asset_id}
    readable_formats = {row["extension"] for row in format_capabilities() if row["can_generate_reader"]}
    generated = {str(row.source_asset_id) for row in assets if row.kind == "normalized"}
    generatable = {str(row.asset_id) for row in tasks if can_edit and row.status == "ready"
        and workspace_file(row).get("generate_reader") is False
        and workspace_file(row).get("extension") in readable_formats and str(row.asset_id) not in generated}
    author_names = list(Contribution.objects.filter(edition__work=work, role="author").order_by("order", "person__preferred_name")
                        .values_list("person__preferred_name", flat=True))
    rights_asset = active or next((row for row in assets if row.kind == "original"), None)
    from .publication_eligibility import active_catalog_snapshot
    public_cover = next(((active_catalog_snapshot(row).get("work") or {}) for row in editions if row.is_primary), {})
    revisions = selected.catalog_revisions.order_by("-revision") if selected else CatalogPublicationRevision.objects.none()
    history = page_rows(revisions, history_page, lambda row: {"id": str(row.pk), "revision": row.revision,
        "title": row.snapshot.get("work", {}).get("title", ""), "status": row.status, "activated_at": row.activated_at,
        "is_current": row.pk == selected.active_catalog_revision_id,
        "can_rollback": bool(row.activated_at and row.status in {"active", "superseded"})})
    inspected = next((row for row in assets if str(row.pk) == str(asset_id)), None) if asset_id else None
    return {"work": {"id": str(work.pk), "title": work.title, "updated_at": work.updated_at,
        "cover_url": f"/api/catalog/works/{work.pk}/cover/" if public_cover.get("cover") or public_cover.get("cover_media") else "",
        "authors": list(dict.fromkeys(author_names)), "document_type": work.document_type,
        "original_publication_year": work.first_publication_date.year if work.first_publication_date else None},
        "editions": [{"id": str(row.pk), "label": " · ".join(str(value) for value in (row.version_label, row.publication_year, row.publisher) if value) or "出版信息待补",
            "version_label": row.version_label, "publication_year": row.publication_year, "publisher": row.publisher,
            "language": work.language, "is_primary": row.is_primary, "state": row.state,
            "original_count": counts.get((str(row.pk), "original"), 0), "reader_count": counts.get((str(row.pk), "normalized"), 0),
            "current_reader_asset_id": str(selected_reader(row).pk) if selected_reader(row) else None} for row in editions],
        "selected_edition_id": str(selected.pk) if selected else None,
        "inspected_file": file_row(inspected, public, actors, False) if inspected else None,
        "edition": {"id": str(selected.pk), "updated_at": selected.updated_at,
            "active_revision_id": str(selected.active_catalog_revision_id) if selected.active_catalog_revision_id else None,
            "current_reader_asset_id": str(active.pk) if active else None,
            "public_reader_asset_id": str(public.pk) if public else None,
            "rights": {"note": rights_asset.rights_note if rights_asset else "", "access_status": rights_asset.access_status if rights_asset else "",
                       "source_asset_id": str(rights_asset.pk) if rights_asset else None,
                       "updated_at": rights_asset.updated_at if rights_asset else None,
                       "can_edit": bool(can_edit and rights_asset)},
            "workbench_url": f"/admin/library/works/{work.pk}?edition={selected.pk}"} if selected else None,
        "files": page_rows(assets, page, lambda row: file_row(row, public, actors,
            (can_publish if selected.state == "published" else can_edit) and (active is None or active.pk != row.pk), generatable, can_publish)),
        "current_reader_file": file_row(active, public, actors, can_publish, can_prepare=can_publish) if active else None,
        "public_reader_file": file_row(public, public, actors, can_publish, can_prepare=can_publish) if public else None,
        "tasks": [task_row(row, assets) for row in tasks[:25]], "task_count": tasks.count(),
        "history": history, "impact": impacts(selected, impact_page, asset_id),
        "capabilities": {"formats": format_capabilities(), "can_edit": can_edit, "can_publish": can_publish,
                         "max_active_tasks_per_edition": 1}}


def dispatch_public_preparation(cloud_id):
    from distribution.tasks import sync_cloud_object
    try:
        sync_cloud_object.apply_async(args=[str(cloud_id)], kwargs={"resume_publication": False}, ignore_result=True)
    except Exception:
        CloudObject.objects.filter(pk=cloud_id, status="pending").update(status="failed",
            error_message="公开分发队列暂不可用，请恢复队列后重试。", updated_at=timezone.now())


@transaction.atomic
def prepare_public_file(edition_id, asset_id, actor, data):
    if not has_capability(actor, Capability.PUBLISH_WORK):
        raise EditionFileError("当前账户没有准备公开文件的权限。", status=403)
    get_user_model().objects.select_for_update().get(pk=actor.pk)
    edition = Edition.objects.select_for_update().get(pk=edition_id)
    asset = Asset.objects.get(pk=asset_id, edition=edition)
    request_key = str(data["request_key"])
    signature = {"asset_id": str(asset.pk), "asset_updated_at": str(data["expected_asset_updated_at"])}
    prior = AuditEvent.objects.filter(action="catalog.file_public_prepared", actor=actor, after__request_key=request_key).first()
    if prior and prior.before != signature:
        raise EditionFileError("此请求编号已用于其他公开文件准备。")
    existing_cloud = asset.cloud_objects.select_for_update().filter(pk=prior.after["cloud_object_id"]).first() if prior else None
    if prior and existing_cloud is None:
        raise EditionFileError("原公开准备记录已不存在，请重新核对文件。")
    if existing_cloud and existing_cloud.status == "ready":
        return {"request_key": request_key, "asset_id": str(asset.pk), "status": "ready",
                "detail": "原请求的公开分发副本已就绪；采用或正式发布仍须明确确认。"}
    if not prior and parse_datetime(str(data["expected_asset_updated_at"])) != asset.updated_at:
        raise EditionFileError("文件已改变，请重新核对将要公开准备的文件。")
    if asset.kind != "normalized" or asset.status != "ready" or asset.validation_status != "valid":
        raise EditionFileError("只有通过校验的规范阅读副本可准备公开。")
    if not settings.REQUIRE_CLOUD_FOR_PUBLICATION:
        raise EditionFileError("当前部署不要求云端阅读副本。")
    from ingestion.services.publication import _asset_storage_readable
    from distribution.services import cloud_budget_allows_new_publication
    if not _asset_storage_readable(asset):
        raise EditionFileError("当前本地阅读文件无法读取，请先恢复存储。")
    provider = existing_cloud.provider if existing_cloud else CloudProvider.objects.filter(enabled=True, is_default=True).first()
    if provider is None or not provider.enabled or not cloud_budget_allows_new_publication(provider):
        raise EditionFileError("公开分发存储尚未配置或预算已阻止新增同步。")
    cloud = asset.cloud_objects.select_for_update().filter(provider=provider).order_by("-updated_at").first()
    if existing_cloud:
        cloud = existing_cloud
    if cloud is None:
        cloud = CloudObject.objects.create(asset=asset, provider=provider,
            object_key=f"published/{edition.pk}/{asset.pk}/{asset.sha256}.pdf",
            sha256=asset.sha256, byte_size=asset.byte_size, cdn_enabled=False)
        dispatch = True
    else:
        if cloud.sha256 != asset.sha256 or cloud.byte_size != asset.byte_size:
            raise EditionFileError("分发记录与阅读文件校验不一致，请先核对原记录。")
        dispatch = cloud.status in {"failed", "deleted"} or (cloud.status in {"pending", "syncing"}
            and (timezone.now() - cloud.updated_at).total_seconds() >
            (settings.INGESTION_QUEUE_STALLED_SECONDS if cloud.status == "pending" else settings.INGESTION_STAGE_STALLED_SECONDS))
    if dispatch:
        cloud.status, cloud.error_message = "pending", ""
        cloud.save(update_fields=["status", "error_message", "updated_at"])
        transaction.on_commit(lambda: dispatch_public_preparation(cloud.pk))
    if not prior:
        AuditEvent.objects.create(actor=actor, action="catalog.file_public_prepared", object_type="Asset", object_id=str(asset.pk),
            before=signature, after={"request_key": request_key, "cloud_object_id": str(cloud.pk), "sha256": asset.sha256})
    return {"request_key": request_key, "asset_id": str(asset.pk), "status": "syncing" if cloud.status == "deleting" else cloud.status,
            "detail": "公开分发准备请求已保存；请核对任务结果，成功后再明确采用或正式发布。"}


@transaction.atomic
def update_rights(edition_id, asset_id, actor, data):
    get_user_model().objects.select_for_update().get(pk=actor.pk)
    edition = Edition.objects.select_for_update().get(pk=edition_id)
    request_key = str(data["request_key"])
    fingerprint = sha256(json.dumps({"edition": str(edition.pk), "asset": str(asset_id),
        "updated_at": str(data["expected_asset_updated_at"]), "rights_note": data["rights_note"]},
        sort_keys=True).encode()).hexdigest()
    prior = AuditEvent.objects.filter(actor=actor, action="catalog.file_rights_updated", after__request_key=request_key).first()
    if prior:
        if prior.before.get("fingerprint") != fingerprint:
            raise EditionFileError("此请求编号已用于其他版权说明修改。")
        return prior.after
    try:
        with transaction.atomic():
            asset = Asset.objects.select_for_update(of=("self",), nowait=True).get(pk=asset_id, edition=edition)
    except DatabaseError as error:
        cause = error.__cause__
        if (getattr(cause, "sqlstate", None) or getattr(cause, "pgcode", None)) == "55P03":
            raise EditionFileError("文件正在处理，请稍后重新核对版权说明。") from error
        raise
    if parse_datetime(str(data["expected_asset_updated_at"])) != asset.updated_at:
        raise EditionFileError("文件已被更新，请保留输入并重新核对版权说明。")
    before = {"rights_note": asset.rights_note, "updated_at": asset.updated_at.isoformat(), "fingerprint": fingerprint}
    asset.rights_note = data["rights_note"]
    asset.save(update_fields=["rights_note", "updated_at"])
    response = {"request_key": request_key, "asset_id": str(asset.pk), "rights_note": asset.rights_note,
                "updated_at": asset.updated_at.isoformat()}
    AuditEvent.objects.create(actor=actor, action="catalog.file_rights_updated", object_type="Asset",
                              object_id=str(asset.pk), before=before, after=response)
    return response


@transaction.atomic
def create_edition(work_id, actor, data):
    get_user_model().objects.select_for_update().get(pk=actor.pk)
    work = Work.objects.select_for_update().get(pk=work_id)
    request = str(data["request_key"])
    fingerprint = sha256(json.dumps({key: str(value) for key, value in data.items() if key != "request_key"}, sort_keys=True).encode()).hexdigest()
    previous = AuditEvent.objects.filter(action="catalog.edition_added", actor=actor, after__request_key=request).first()
    if previous:
        if previous.object_id != str(work.pk) or previous.before.get("fingerprint") != fingerprint:
            raise EditionFileError("此请求编号已用于其他出版版本。")
        return {**previous.after, "created": False}
    if parse_datetime(str(data["expected_work_updated_at"])) != work.updated_at:
        raise EditionFileError("作品在预览后变化，请刷新后核对新增版本。")
    session = CatalogingSession.objects.filter(created_by=actor, request_key=data["request_key"]).first()
    if session:
        raise EditionFileError("此请求编号已用于其他编目会话。")
    edition = Edition.objects.create(work=work, version_label=data["version_label"],
        publication_year=data.get("publication_year"), publisher=data.get("publisher", ""),
        is_primary=False, publication_mode=Edition.PublicationMode.BIBLIOGRAPHIC)
    session = CatalogingSession.objects.create(edition=edition, source_type="manual", created_by=actor, request_key=data["request_key"])
    from .field_decisions import record_edition_field_decision
    for name in ("version_label", "publication_year", "publisher"):
        if data.get(name) not in (None, ""):
            record_edition_field_decision(edition, name, value=data[name], status="confirmed", actor=actor,
                                         provenance={"source": "explicit_edition_creation"})
    work.save(update_fields=["updated_at"])
    result = {"created": True, "work_id": str(work.pk), "edition_id": str(edition.pk), "request_key": request,
              "workbench_url": f"/admin/library/works/{work.pk}?edition={edition.pk}"}
    AuditEvent.objects.create(actor=actor, action="catalog.edition_added", object_type="Work", object_id=str(work.pk),
                              before={"fingerprint": fingerprint}, after=result)
    return result


def adoption_context(edition_id, asset_id, actor, *, lock=False):
    editions = Edition.objects.select_related("active_catalog_revision__reader_asset")
    if lock:
        editions = editions.select_for_update(of=("self",))
    edition = editions.get(pk=edition_id)
    assets = Asset.objects.filter(pk=asset_id, edition=edition)
    if lock:
        try:
            with transaction.atomic():
                asset = assets.select_for_update(of=("self",), nowait=True).get()
        except DatabaseError as error:
            cause = error.__cause__
            if (getattr(cause, "sqlstate", None) or getattr(cause, "pgcode", None)) == "55P03":
                raise EditionFileError("文件正在处理，请稍后重新预览采用操作。") from error
            raise
    else:
        asset = assets.get()
    active = selected_reader(edition)
    pending = list(edition.catalog_revisions.filter(status__in=["preparing", "failed"])
                   .filter(revision__gt=edition.active_catalog_revision.revision if edition.active_catalog_revision_id else 0)
                   .values_list("id", "updated_at"))
    document = asset.document_revisions.filter(is_active=True).order_by("-revision").first()
    blocking = []
    required = Capability.PUBLISH_WORK if edition.state == "published" else Capability.EDIT_METADATA
    if not has_capability(actor, required):
        blocking.append("当前账户没有采用此版本阅读文件的权限。")
    revision = edition.active_catalog_revision
    if edition.state == "published" and (revision is None or revision.edition_id != edition.pk
            or revision.status != "active" or not revision.metadata_ready):
        blocking.append("此版本公开修订不完整，请先核对正式发布。")
    if asset.kind != "normalized" or asset.status != "ready" or asset.validation_status != "valid":
        blocking.append("所选文件尚不是通过校验的规范阅读副本。")
    from ingestion.services.publication import _asset_storage_readable
    if not _asset_storage_readable(asset):
        blocking.append("所选文件当前无法读取，请先恢复存储。")
    if pending:
        blocking.append("此版本已有待完成的发布修订，请先完成或恢复原发布。")
    if document is None:
        blocking.append("所选阅读副本尚未完成文档解析。")
    if edition.state == "published" and settings.REQUIRE_CLOUD_FOR_PUBLICATION and not asset.cloud_objects.filter(status="ready").exists():
        blocking.append("当前部署要求公开分发副本，请先明确准备公开阅读文件，成功后重新预览采用。")
    fingerprint = sha256(json.dumps({"edition": str(edition.pk), "updated_at": str(edition.updated_at),
        "active": str(edition.active_catalog_revision_id), "asset": str(asset.pk), "asset_updated": str(asset.updated_at),
        "sha256": asset.sha256, "document": str(document.pk) if document else None,
        "document_updated": str(document.updated_at) if document else None, "pending": [[str(a), str(b)] for a, b in pending]}, sort_keys=True).encode()).hexdigest()
    return edition, asset, active, fingerprint, blocking


def prepare_adoption(edition_id, asset_id, actor):
    edition, asset, active, fingerprint, blocking = adoption_context(edition_id, asset_id, actor)
    from .knowledge_publication import _current_document
    _, _, fulltext_ready = _current_document(edition, content_asset_id=asset.pk) if asset.kind == "normalized" and asset.status == "ready" else (None, None, False)
    return {"edition_id": str(edition.pk), "target_asset_id": str(asset.pk), "current_reader_asset_id": str(active.pk) if active else None,
        "request_key": str(uuid4()), "fingerprint": fingerprint, "can_adopt": not blocking,
        "already_current": bool(active and active.pk == asset.pk), "blocking": blocking,
        "impact": ["完成公开处理后，当前阅读入口切换到所选文件；处理失败时仍使用原文件。" if edition.state == "published" else
                   "此次只选择管理工作台的阅读文件，不公开或恢复公开此版本；仍需完成编目并明确发布。",
                   "当前正式书目、人工字段和未发布草稿保持原样；此次只采用阅读文件。",
                   "原件、旧阅读文件、旧页标识、证据与私人记录全部保留，引用不会自动改绑。",
                   "所选副本的正文已通过质量检查，实际全文检索仍等待发布任务完成。" if fulltext_ready else
                   "所选副本全文尚未就绪。采用后可以阅读，正文检索暂不可用；可再明确启动 OCR 或校准文字。"]}


def adoption_result(record):
    data = record.after
    edition = Edition.objects.select_related("active_catalog_revision__reader_asset").get(pk=data["edition_id"])
    event = KnowledgePublicationEvent.objects.filter(pk=data["event_id"]).first() if data["event_id"] else None
    active = selected_reader(edition)
    public = reader(edition)
    effective = bool(active and str(active.pk) == data["target_asset_id"])
    public_effective = bool(public and str(public.pk) == data["target_asset_id"])
    return {**data, "command_accepted": True, "status": event.status if event else "completed", "effective": effective,
            "public_effective": public_effective, "publication_required": edition.state != "published",
            "detail": "所选文件已成为当前公开阅读文件。" if public_effective else
            "管理阅读文件已选定，仍需完成编目并明确发布。" if effective else "采用请求已保存；请核对发布结果，旧文件与引用保留。"}


@transaction.atomic
def adopt_file(edition_id, asset_id, actor, data):
    get_user_model().objects.select_for_update().get(pk=actor.pk)
    edition, asset, active, fingerprint, blocking = adoption_context(edition_id, asset_id, actor, lock=True)
    previous = AuditEvent.objects.filter(action="catalog.file_selected", actor=actor, after__request_key=str(data["request_key"])).first()
    if previous:
        if previous.after["edition_id"] != str(edition.pk) or previous.after["target_asset_id"] != str(asset.pk) or previous.before["fingerprint"] != data["fingerprint"]:
            raise EditionFileError("此请求编号已用于其他文件选择。")
        return adoption_result(previous)
    if fingerprint != data["fingerprint"]:
        raise EditionFileError("文件、文档或公开修订在预览后变化，请重新确认。")
    if blocking:
        raise EditionFileError(" ".join(blocking))
    event = None
    if edition.state != "published" and (not active or active.pk != asset.pk):
        now = timezone.now()
        Asset.objects.filter(edition=edition, kind="normalized", is_current=True).exclude(pk=asset.pk).update(is_current=False, updated_at=now)
        Asset.objects.filter(pk=asset.pk).update(is_current=True, updated_at=now)
        if asset.source_asset_id and asset.source_asset.kind == Asset.Kind.ORIGINAL:
            Asset.objects.filter(edition=edition, kind="original", is_current=True).exclude(pk=asset.source_asset_id).update(is_current=False, updated_at=now)
            Asset.objects.filter(pk=asset.source_asset_id).update(is_current=True, updated_at=now)
        edition.publication_mode = Edition.PublicationMode.DOCUMENT
        edition.save(update_fields=["publication_mode", "updated_at"])
    elif not active or active.pk != asset.pk:
        from .knowledge_publication import create_catalog_publication_event
        try:
            event = create_catalog_publication_event(edition, event_type="catalog_updated", changed_fields=["asset", "document_revision"],
                actor=actor, idempotency_key=f"file-selection:{edition.pk}:{data['request_key']}", content_asset_id=asset.pk,
                provenance={"source": "file_selection", "previous_reader_asset_id": str(active.pk) if active else None})
        except ValueError as error:
            raise EditionFileError(str(error)) from error
    record = AuditEvent.objects.create(actor=actor, action="catalog.file_selected", object_type="Edition", object_id=str(edition.pk),
        before={"fingerprint": fingerprint}, after={"request_key": str(data["request_key"]), "edition_id": str(edition.pk),
            "target_asset_id": str(asset.pk), "event_id": str(event.pk) if event else ""})
    return adoption_result(record)
