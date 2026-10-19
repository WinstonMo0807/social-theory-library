"""Public metadata resolver and private source-update inbox. Never performs network probes."""
import hashlib
import json
import logging
import re
from urllib.parse import urlsplit
from uuid import UUID

from celery import shared_task
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from catalog.models import Asset, CatalogPublicationRevision, Page
from catalog.services.publication_eligibility import public_editions
from catalog.services.public_feedback import safe_public_path
from .research import ResearchConflict
from .source_models import SourceFollow, SourceFollowEvent

PAGE_SIZE = 20
MAX_FOLLOWS = 500
NOTICE = "仅在站内记录公开来源状态变更，不发送邮件。定时检查依赖后台任务运行；检查时间不表示文件网络探活。"
logger = logging.getLogger(__name__)


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def canonical_path(raw):
    path = safe_public_path(raw)
    base = (urlsplit(path).path.rstrip("/") or "/") if path else ""
    match = re.fullmatch(r"/reader/([^/]+)", base)
    if match:
        try:
            return f"/reader/{UUID(match.group(1))}"
        except ValueError:
            return ""
    return base


def resolve_public_source(raw):
    """Shared by feedback cards and follows: only activated anonymous-public metadata."""
    path = safe_public_path(raw)
    base = canonical_path(path)
    result = {"path": path, "canonical_path": base, "status": "unavailable", "title": "来源当前不可用",
        "authors": [], "cover_url": "", "source_type": "", "version_label": "", "location": "",
        "updated_at": None, "checked_at": timezone.now().isoformat(), "can_subscribe": False,
        "reader_url": "", "work_id": None, "edition_id": None, "asset_id": None,
        "catalog_revision_id": None, "document_revision_id": None,
        "notice": "当前无法核对公开来源。未公开、撤回或不存在的来源均不显示旧书目信息。"}
    match = re.fullmatch(r"/(reader|works)/([^/]+)", base)
    if not match:
        # Navigation labels are local product metadata, never caller-supplied titles.
        labels = {"/": "首页", "/help": "使用帮助与反馈", "/about": "关于书库", "/explore": "探索书库",
                  "/help/search": "搜索资料", "/help/reading": "阅读文献", "/help/citation": "引用与导出",
                  "/help/source": "来源说明", "/help/account": "账户与隐私"}
        if base in labels:
            result.update(status="page", title=labels[base], notice="站内页面，不是可订阅的原文来源。")
        return result
    kind, identifier = match.groups()
    source_asset = None
    editions = public_editions()
    if kind == "reader":
        try:
            identifier = str(UUID(identifier))
        except ValueError:
            return result
        # Neither an ORIGINAL nor a never-published staged file proves public identity.
        source_asset = Asset.objects.filter(pk=identifier, kind=Asset.Kind.NORMALIZED).first()
        if source_asset is None or source_asset.access_status not in {Asset.AccessStatus.PUBLIC, Asset.AccessStatus.INHERIT}:
            return result
        edition = editions.filter(pk=source_asset.edition_id).first()
        if not edition or not CatalogPublicationRevision.objects.filter(edition=edition, reader_asset=source_asset,
                status__in=["active", "superseded"]).exists():
            return result
    else:
        edition = editions.filter(public_slug=identifier).first()
        if edition is None:
            return result
    revision = edition.active_catalog_revision
    snapshot = revision.snapshot if isinstance(revision.snapshot, dict) else {}
    work, edition_values = snapshot.get("work") or {}, snapshot.get("edition") or {}
    current = revision.reader_asset
    readable = bool(current and current.edition_id == edition.pk and current.kind == Asset.Kind.NORMALIZED
                    and current.status == Asset.Status.READY and current.validation_status == "valid"
                    and current.access_status in {Asset.AccessStatus.PUBLIC, Asset.AccessStatus.INHERIT} and current.file)
    # Edition metadata is already public even when its current file is restricted/unavailable.
    status = "available" if readable else "unavailable"
    if source_asset and readable and current.pk != source_asset.pk:
        status = "replaced"
    title = work.get("title") or "题名待补"
    media = work.get("cover_media") or {}
    cover = reverse("public-work-cover", kwargs={"work_id": edition.work_id}) if work.get("cover") or media else ""
    if cover and media.get("primary_rendition_id"):
        cover += f"?rendition={media['primary_rendition_id']}"
    authors = [(row.get("person") or {}).get("preferred_name") or row.get("name", "")
               for row in snapshot.get("contributions", snapshot.get("contributors")) or []
               if isinstance(row, dict) and row.get("role") == "author"]
    page = re.search(r"\?page=([1-9]\d{0,5})$", path)
    location = ""
    if page and source_asset and current and current.pk == source_asset.pk and readable:
        page_row = Page.objects.filter(asset=source_asset, index=int(page.group(1))).first()
        if page_row:
            location = f"PDF 第 {page.group(1)} 页" + (f" · 印刷页 {page_row.printed_label}" if page_row.printed_label else "")
        else:
            location = "所选 PDF 页码当前无法核对"
    result.update(status=status, title=title, authors=[value for value in authors if value], cover_url=cover,
        source_type="PDF 阅读文件" if current else "公开书目信息", version_label=edition_values.get("version_label") or "",
        location=location, updated_at=revision.activated_at.isoformat() if revision.activated_at else None,
        can_subscribe=True, reader_url=f"/reader/{current.pk}" if readable else "", work_id=str(edition.work_id),
        edition_id=str(edition.pk), asset_id=str(current.pk) if readable else None, catalog_revision_id=str(revision.pk),
        document_revision_id=str(revision.document_revision_id) if readable and revision.document_revision_id else None,
        notice={"available": "来源已公开。此处核对发布状态，文件能否打开以阅读页当次访问为准。",
                "replaced": "这份阅读文件已有新的正式版本。旧位置不能自动换算，请打开当前原文重新核对。",
                "unavailable": "公开书目信息仍可核对，阅读文件暂不可用。可以订阅站内更新或提交来源纠错。"}[status])
    return result


def state_fingerprint(source):
    return digest({key: source[key] for key in ("status", "catalog_revision_id", "document_revision_id", "asset_id")})


def lock_owner(user_id):
    return get_user_model().objects.select_for_update().filter(pk=user_id).first()


@transaction.atomic
def refresh(follow_id, owner_id):
    owner = lock_owner(owner_id)
    if owner is None:
        return None
    row = SourceFollow.objects.select_for_update().filter(pk=follow_id, user_id=owner_id).first()
    if row is None or not row.active:
        return row
    from .privacy import retention_enabled
    if not retention_enabled(owner, "source_follows"):
        return row
    source = resolve_public_source(row.path)
    fingerprint = state_fingerprint(source)
    changed = fingerprint != row.state_fingerprint
    if changed:
        row.revision += 1
        SourceFollowEvent.objects.create(follow=row, user_id=owner_id, action="changed",
            before_status=row.source_status, after_status=source["status"], revision=row.revision)
        row.source_status, row.state_fingerprint = source["status"], fingerprint
    row.last_checked_at, row.check_error = timezone.now(), ""
    row.save(update_fields=["revision", "source_status", "state_fingerprint", "last_checked_at", "check_error"]
             + (["updated_at"] if changed else []))
    return row


def event_output(event):
    return {"id": str(event.pk), "action": event.action, "before_status": event.before_status,
            "after_status": event.after_status, "observed_at": event.created_at.isoformat(), "revision": event.revision}


def output(row, *, history_page=1, export=False):
    from .privacy import retention_enabled
    source = resolve_public_source(row.path)  # No historical titles survive withdrawal.
    events = row.events.order_by("-created_at", "-id")
    changed = events.filter(action="changed")
    if row.read_at:
        changed = changed.filter(created_at__gt=row.read_at)
    start = (history_page - 1) * PAGE_SIZE
    return {"id": str(row.pk), "owner_id": str(row.user_id), "path": row.path, "active": row.active,
        "revision": row.revision, "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
        "last_checked_at": row.last_checked_at.isoformat() if row.last_checked_at else None,
        "check_error": row.check_error, "unread_count": changed.count(), "source": source, "notice": NOTICE,
        "updates_paused": row.active and not retention_enabled(row.user, "source_follows"),
        "history": {"count": events.count(), "page": history_page, "page_size": PAGE_SIZE,
                    "results": [event_output(event) for event in (events if export else events[start:start + PAGE_SIZE])]}}


@transaction.atomic
def command(user, data):
    lock_owner(user.pk)
    path = canonical_path(data["path"])
    if not re.fullmatch(r"/(reader|works)/[^/]+", path):
        raise ValidationError({"path": "请选择可核对的站内公开原文或书目页面。"})
    action = data["action"]
    fingerprint = digest({**data, "path": path})
    prior = SourceFollowEvent.objects.filter(user=user, request_id=data["request_id"]).first()
    if prior:
        if prior.request_fingerprint != fingerprint:
            raise ResearchConflict("该请求标识已用于不同操作，请重新读取后操作。")
        return output(prior.follow)
    row = SourceFollow.objects.select_for_update().filter(user=user, path=path).first()
    if data["expected_revision"] != (row.revision if row else 0):
        raise ResearchConflict("来源关注已变化，请重新读取；尚未应用本次操作。")
    if action == "subscribe":
        from .privacy import require_retention
        require_retention(user, "source_follows")
        source = resolve_public_source(path)
        if not source["can_subscribe"]:
            raise ValidationError("当前不能核对这项公开来源，未建立订阅。")
        if row is None:
            if SourceFollow.objects.filter(user=user).count() >= MAX_FOLLOWS:
                raise ValidationError("已达到 500 项来源记录上限，请先在隐私与资料中删除不需要的历史记录。")
            row = SourceFollow.objects.create(user=user, path=path, state_fingerprint=state_fingerprint(source),
                source_status=source["status"], last_checked_at=timezone.now())
        else:
            row.active = True
            row.revision += 1
            row.source_status, row.state_fingerprint = source["status"], state_fingerprint(source)
            row.last_checked_at = timezone.now()
            row.check_error = ""
    elif row is None:
        raise NotFound("本人来源关注记录不存在。")
    else:
        row.revision += 1
        if action == "unsubscribe":
            row.active = False
        elif action == "mark_read":
            row.read_at = timezone.now()
    row.save()
    SourceFollowEvent.objects.create(follow=row, user=user, action=action, after_status=row.source_status,
        request_id=data["request_id"], request_fingerprint=fingerprint, revision=row.revision)
    return output(row)


@shared_task(name="reading.refresh_source_follows", ignore_result=True, soft_time_limit=100, time_limit=120)
def refresh_source_follows():
    # Bounded oldest-first cursor is persisted per follow; failures also move on.
    from accounts.models import ReaderProfile
    paused = ReaderProfile.objects.filter(reading_preferences__privacy_retention__source_follows=False).values("user_id")
    candidates = list(SourceFollow.objects.filter(active=True)
                      .exclude(user_id__in=paused)
                      .order_by(F("last_checked_at").asc(nulls_first=True), "id")
                      .values_list("id", "user_id")[:200])
    for follow_id, owner_id in candidates:
        try:
            refresh(follow_id, owner_id)
        except Exception as exc:
            # Preserve the last known state; a failed check is never a source transition.
            SourceFollow.objects.filter(pk=follow_id, user_id=owner_id, active=True).exclude(user_id__in=paused).update(
                last_checked_at=timezone.now(), check_error="status_check_failed")
            logger.warning("Source status check failed (%s)", type(exc).__name__)
    return len(candidates)
