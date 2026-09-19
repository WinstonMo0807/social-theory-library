"""Explicit primary selection through existing editorial/publication records."""
from hashlib import sha256
import json
from uuid import uuid4

from django.db import DatabaseError, transaction
from django.db.models import Q

from catalog.models import CatalogFieldDecision, CatalogPublicationRevision, Edition, EditorialRevision, KnowledgePublicationEvent, Work
from catalog.services.editorial_revision import create_editorial_revision, publish_editorial_revision
from catalog.services.publication_commands import PublicationCommandError, catalog_publication_state, validate_revision
from common.capabilities import Capability, has_capability
from ingestion.models import AuditEvent


def _context(edition_id, *, lock=False):
    target = Edition.objects.select_related("work").get(pk=edition_id)
    work = Work.objects.select_for_update().get(pk=target.work_id) if lock else target.work
    rows = work.editions.select_related("active_catalog_revision", "active_catalog_revision__reader_asset")
    if lock:
        # Older publication paths acquire Edition before Work. Never wait for
        # their Edition while holding this Work lock: abort this explicit
        # selection so the ongoing operation can finish without a lock cycle.
        rows = rows.select_for_update(of=("self",), nowait=True)
    try:
        with transaction.atomic():
            editions = list(rows.order_by("id"))
    except DatabaseError as error:
        cause = error.__cause__
        if lock and (getattr(cause, "sqlstate", None) or getattr(cause, "pgcode", None)) == "55P03":
            raise PublicationCommandError("此作品的出版版本正在被其他操作处理，请稍后重新预览主版本。") from error
        raise
    target = next((row for row in editions if row.pk == target.pk), None)
    if target is None:
        raise PublicationCommandError("出版版本归属已经变化，请重新读取作品。")
    drafts = list(EditorialRevision.objects.filter(
        Q(target_type="work", target_id=work.pk) | Q(target_type="edition", target_id__in=[row.pk for row in editions]),
        status="draft",
    ).order_by("id"))
    affected = [row for row in editions if row.is_primary or row.pk == target.pk]
    active_numbers = {row.pk: row.active_catalog_revision.revision if row.active_catalog_revision_id else 0 for row in affected}
    pending = [row for row in CatalogPublicationRevision.objects.filter(edition__in=affected, status__in=["preparing", "failed"])
               if row.revision > active_numbers[row.edition_id] and set(row.changed_fields or []) != {"is_primary"}]
    conflicts = list(CatalogFieldDecision.objects.filter(edition__in=affected, status="conflict").values_list("id", flat=True))
    data = {"work": [str(work.pk), work.updated_at.isoformat()], "target": str(target.pk),
            "editions": [[str(row.pk), row.is_primary, row.state, row.updated_at.isoformat(), str(row.active_catalog_revision_id),
                          row.active_catalog_revision.status if row.active_catalog_revision_id else None,
                          row.active_catalog_revision.metadata_ready if row.active_catalog_revision_id else None]
                         for row in editions],
            "drafts": [[str(row.pk), row.updated_at.isoformat()] for row in drafts], "conflicts": sorted(map(str, conflicts)),
            "pending_publications": [[str(row.pk), row.updated_at.isoformat()] for row in pending]}
    fingerprint = sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    blocking = []
    if not catalog_publication_state(target)["catalog_revision_active"]:
        blocking.append("请先完成此版本的正式公开；主版本选择不会自动发布草稿或修复失效修订。")
    for row in affected:
        if row.state != "published":
            continue
        if not catalog_publication_state(row)["catalog_revision_active"] or row.active_catalog_revision.activated_at is None:
            blocking.append("当前或目标版本的公开修订不完整，请先核查发布记录。")
        elif validate_revision(row.active_catalog_revision, edition=row):
            blocking.append("当前或目标版本的历史文件未通过验证，不能切换主版本。")
    if drafts:
        blocking.append("此作品或出版版本仍有未发布草稿。请先处理草稿，避免混入主版本选择。")
    if conflicts:
        blocking.append("当前或目标出版版本仍有人工字段冲突，请先复核。")
    if pending:
        blocking.append("当前或目标版本已有尚未生效的正式发布修改，请先完成或恢复原发布，避免主版本选择覆盖已批准的修改。")
    return work, target, editions, fingerprint, list(dict.fromkeys(blocking))


def prepare_primary_edition(edition_id, *, actor):
    work, target, editions, fingerprint, blocking = _context(edition_id)
    permitted = has_capability(actor, Capability.PUBLISH_WORK)
    if not permitted:
        blocking.append("当前账户没有馆藏发布权限。")
    return {"work_id": str(work.pk), "edition_id": str(target.pk), "title": work.title,
            "request_key": str(uuid4()), "fingerprint": fingerprint, "can_select": not blocking, "blocking": blocking,
            "current_primary_edition_ids": [str(row.pk) for row in editions if row.is_primary],
            "already_primary": target.is_primary and sum(row.is_primary for row in editions) == 1,
            "target_public_url": f"/works/{target.public_slug}" if target.public_slug else "",
            "preview_url": f"/admin/preview/works/{target.pk}",
            "editions": [{"id": str(row.pk), "version_label": row.version_label, "publication_year": row.publication_year,
                          "is_primary": row.is_primary, "active_revision_id": catalog_publication_state(row)["active_revision_id"],
                          "public_slug": row.public_slug} for row in editions],
            "impact": ["作品列表和作品详情改用所选版本已经公开的快照，不发布其他元数据。",
                       "各版本原有作品链接、Reader文件链接、Page ID和私人阅读记录保留；旧作品链接仍指向同一作品。",
                       "主版本选择在数据库事务中生效；检索、推荐和其他派生结果由原任务系统分别更新，失败可追踪。"]}


def _result(record):
    values = record.after
    edition = Edition.objects.select_related("active_catalog_revision").get(pk=values["edition_id"])
    visibility = catalog_publication_state(edition)
    events = list(KnowledgePublicationEvent.objects.filter(pk__in=values["event_ids"]).select_related("catalog_revision").order_by("created_at", "id"))
    effective = bool(edition.is_primary and visibility["catalog_revision_active"])
    return {"request_key": values["request_key"], "work_id": values["work_id"], "edition_id": values["edition_id"],
            "audit_id": str(record.pk), "command_accepted": True, "listing_effective": effective,
            "publication": visibility, "public_url": visibility["public_url"],
            "current_primary_edition_ids": list(map(str, Edition.objects.filter(work_id=values["work_id"], is_primary=True).values_list("pk", flat=True))),
            "editorial_revision_ids": values["editorial_revision_ids"],
            "events": [{"id": str(row.pk), "edition_id": str(row.catalog_revision.edition_id), "status": row.status,
                        "href": f"/admin/library/works/{values['work_id']}?edition={row.catalog_revision.edition_id}#publication"} for row in events],
            "projections_complete": all(row.status == "completed" for row in events),
            "detail": ("当前已经是唯一主版本，没有重复修改。" if not values["editorial_revision_ids"] else
                       "主版本已切换，作品页面使用所选版本原有的合法公开快照；派生更新请查看事件结果。") if effective else
                      "此请求先前已完成，但后续操作已改变当前主版本。重试没有覆盖后续选择。"}


@transaction.atomic
def select_primary_edition(edition_id, *, actor, fingerprint, request_key):
    if not has_capability(actor, Capability.PUBLISH_WORK):
        raise PublicationCommandError("当前账户没有馆藏发布权限。")
    work, target, editions, current_fingerprint, blocking = _context(edition_id, lock=True)
    previous = AuditEvent.objects.filter(action="catalog.primary_selected", after__request_key=str(request_key)).first()
    if previous:
        if previous.actor_id != actor.pk or previous.after["edition_id"] != str(target.pk) or previous.before["fingerprint"] != fingerprint:
            raise PublicationCommandError("请求编号已用于其他主版本选择。")
        return _result(previous)
    if current_fingerprint != fingerprint:
        raise PublicationCommandError("作品、版本或修订已在预览后变化，请重新检查主版本影响。")
    if blocking:
        raise PublicationCommandError(" ".join(blocking))
    changed = [row for row in editions if row.is_primary != (row.pk == target.pk)]
    revisions = []
    for edition in changed:
        revision = create_editorial_revision(target_type="edition", target_id=edition.pk,
                                             patch={"is_primary": edition.pk == target.pk}, actor=actor,
                                             idempotency_key=f"primary:{work.pk}:{request_key}:{edition.pk}",
                                             change_note="明确选择作品的展示出版版本；保留原公开内容和链接")
        publish_editorial_revision(revision.pk, actor=actor, preserve_catalog_snapshot=edition.state == "published")
        revisions.append(revision.pk)
    event_ids = list(map(str, KnowledgePublicationEvent.objects.filter(
        idempotency_key__in=[f"editorial-catalog:{identifier}" for identifier in revisions],
    ).values_list("pk", flat=True)))
    record = AuditEvent.objects.create(actor=actor, action="catalog.primary_selected", object_type="Work", object_id=str(work.pk),
                                       before={"fingerprint": fingerprint, "primary_edition_ids": [str(row.pk) for row in editions if row.is_primary]},
                                       after={"request_key": str(request_key), "work_id": str(work.pk), "edition_id": str(target.pk),
                                              "editorial_revision_ids": list(map(str, revisions)), "event_ids": event_ids})
    return _result(record)
