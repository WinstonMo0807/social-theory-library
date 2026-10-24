"""R29 uses the original owner lists, public catalog snapshots and private receipts."""
from datetime import timedelta
from hashlib import sha256
import json
import re
import unicodedata

from pypinyin import lazy_pinyin
from unidecode import unidecode

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from catalog.models import Edition, Work
from catalog.services.publication_eligibility import public_edition_q
from . import privacy, research
from .knowledge_models import KnowledgeSaveReceipt
from .models import ReadingList, ReadingListItem
from .serializers import _reader_work_data
from .services import readable_progress_for_user

MAX_ITEMS = 1000
PAGE_SIZE = 20


def version(row):
    return row.updated_at.isoformat()


def touch(row):
    row.save(update_fields=["updated_at"])
    row._prefetched_objects_cache = {}


def preserve_origin(row):
    if not row.origin_key and re.fullmatch(r"专题书目副本 / [0-9a-f]{64}", row.description):
        row.origin_key = row.description.rsplit(" / ", 1)[1]


def owned(user, pk):
    row = ReadingList.objects.filter(user=user, pk=research.identifier(pk)).first()
    if row is None:
        raise NotFound("这份本人书单已不存在。")
    return row


def public_editions():
    return Edition.objects.filter(public_edition_q(), is_primary=True)


def summary(row):
    return {"id": str(row.pk), "title": row.title, "description": row.description,
        "goal": row.goal, "tags": row.tags, "version": version(row), "created_at": row.created_at,
        "updated_at": row.updated_at, "item_count": row.items.filter(removed_at__isnull=True).count()}


def project_item(request, row):
    available = public_editions().filter(work_id=row.work_id).exists()
    work = _reader_work_data(row.work, {"request": request}) if available else None
    progress = readable_progress_for_user(request.user).filter(asset__edition__work_id=row.work_id).order_by("-updated_at", "-id").first() if available else None
    asset = (work or {}).get("edition", {}).get("readable_asset") if work and work.get("edition") else None
    return {"id": str(row.pk), "work_id": str(row.work_id), "order": row.order, "work": work,
        "created_at": row.created_at, "removed_at": row.removed_at,
        "expires_at": row.removed_at + timedelta(days=30) if row.removed_at else None,
        "progress_ratio": progress.progress_ratio if progress else None,
        "reader_url": f"/reader/{progress.asset_id}?page={progress.current_page}" if progress else f"/reader/{asset['id']}" if asset else None}


def alphabetical_items(rows, order):
    from catalog.services.citations import _contributors
    # ponytail: lists hold <=1000 active works; bounded in-memory sorting reuses
    # installed transliteration and exact public authors without another index.
    if rows.count() > 5000:
        raise ValidationError("当前范围超过5000项，请先缩小范围或使用加入时间排序；没有截断结果。")
    values, versions = {}, {}
    def key(value):
        return unidecode(" ".join(lazy_pinyin(unicodedata.normalize("NFKC", str(value or ""))))).casefold().strip()
    for edition in public_editions().filter(work_id__in=rows.values("work_id")).select_related("active_catalog_revision"):
        snapshot = edition.active_catalog_revision.snapshot or {}
        title = key((snapshot.get("work") or {}).get("title"))
        authors = _contributors(edition, snapshot) if snapshot else []
        selected = key(authors[0]) if order == "author" and authors else "" if order == "author" else title
        values[edition.work_id] = (not bool(selected), selected, title)
        versions[str(edition.pk)] = str(edition.active_catalog_revision_id)
    ordered = sorted(rows, key=lambda item: (*values.get(item.work_id, (True, "", "")), str(item.pk)))
    return ordered, versions


def workspace(request, row, query):
    rows = row.items.select_related("work").order_by("order", "created_at", "id")
    cutoff = timezone.now() - timedelta(days=30)
    trash = query["trash"]
    total_active = rows.filter(removed_at__isnull=True).count()
    total_trash = rows.filter(removed_at__gt=cutoff).count()
    rows = rows.filter(removed_at__gt=cutoff) if trash else rows.filter(removed_at__isnull=True)
    editions = public_editions()
    if query["q"]:
        editions = editions.filter(active_catalog_revision__snapshot__work__title__icontains=query["q"])
    if query["kind"]:
        editions = editions.filter(active_catalog_revision__snapshot__work__document_type=query["kind"])
    if query["q"] or query["kind"]:
        rows = rows.filter(work_id__in=editions.values("work_id"))
    if query["order"] == "newest":
        rows = rows.order_by("-created_at", "-id")
    elif query["order"] == "oldest":
        rows = rows.order_by("created_at", "id")
    count = rows.count()
    page = query["page"]
    if page > 1 and (page - 1) * PAGE_SIZE >= count:
        raise NotFound("这一页已没有作品，请返回第一页。")
    ordered, source_versions = alphabetical_items(rows, query["order"]) if query["order"] in {"title", "author"} else (rows, None)
    result = [project_item(request, item) for item in ordered[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]]
    if source_versions is not None:
        current = public_editions().filter(work_id__in=rows.values("work_id"))
        if source_versions != {str(pk): str(revision) for pk, revision in current.values_list("pk", "active_catalog_revision_id")}:
            raise research.ResearchConflict("公开书目在排序时发生变化，请重新读取。")
    if version(owned(request.user, row.pk)) != version(row):
        raise research.ResearchConflict("书单正在另一页面修改，请重新读取。")
    return {"owner_id": str(request.user.pk), "list": summary(row), "items": result,
        "count": count, "page": page, "total_pages": max(1, (count + PAGE_SIZE - 1) // PAGE_SIZE),
        "active_count": total_active, "trash_count": total_trash}


def receipt_for(user, pk, request_id):
    receipt = KnowledgeSaveReceipt.objects.filter(user=user, request_id=request_id).first()
    if receipt and receipt.target_key != sha256(f"booklist:{pk}".encode()).hexdigest():
        raise research.ResearchConflict("原请求属于另一项操作，请核对原操作。")
    return receipt


def result(user, pk, receipt):
    return {"owner_id": str(user.pk), "id": str(pk), "exists": ReadingList.objects.filter(user=user, pk=pk).exists(),
        "receipt": {"request_id": str(receipt.request_id)}}


def add_work(row, work_id):
    if not public_editions().filter(work_id=work_id).exists():
        raise ValidationError("该作品当前未公开，不能加入书单。")
    existing = row.items.filter(work_id=work_id).first()
    if existing and existing.removed_at is None:
        return existing, False
    if row.items.filter(removed_at__isnull=True).count() >= MAX_ITEMS:
        raise ValidationError("一份书单最多保存1000部作品，请另建书单。")
    order = (row.items.aggregate(value=Max("order"))["value"] or 0) + 1
    if existing:
        existing.removed_at, existing.order = None, order
        existing.save(update_fields=["removed_at", "order", "updated_at"])
        touch(row)
        return existing, False
    item = ReadingListItem.objects.create(reading_list=row, work_id=work_id, order=order)
    touch(row)
    return item, True


@transaction.atomic
def command(user, data):
    privacy.lock_owner(user)
    pk, verb = data["list_id"], data["action"]
    fingerprint = sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
    receipt = receipt_for(user, pk, data["request_id"])
    if receipt:
        if receipt.fingerprint != fingerprint:
            raise research.ResearchConflict("原请求内容已改变，请先核对原结果。")
        return result(user, pk, receipt)
    row = ReadingList.objects.select_for_update().filter(user=user, pk=pk).first()
    if verb == "create":
        if row or data["expected_version"] != "0":
            raise research.ResearchConflict("创建标识已经使用，请重新读取书单。")
        privacy.require_retention(user, "saved_knowledge")
        row = ReadingList.objects.create(pk=pk, user=user, title=data["title"], description=data.get("description", ""))
    else:
        if row is None:
            raise NotFound("这份本人书单已不存在。")
        if data["expected_version"] != version(row):
            raise research.ResearchConflict("书单已在另一页面修改，请读取当前版本后重试。")
        if verb in {"edit", "add", "restore", "move"}:
            privacy.require_retention(user, "saved_knowledge")
        if verb == "edit":
            preserve_origin(row)
            for name in ("title", "description", "goal", "tags"):
                if name in data:
                    setattr(row, name, data[name])
            row.save()
        elif verb == "add":
            add_work(row, data["work_id"])
        elif verb in {"remove", "restore", "purge"}:
            ids = data["item_ids"]
            items = list(row.items.filter(pk__in=ids))
            if len(items) != len(ids):
                raise research.ResearchConflict("所选作品已变化，请重新选择。")
            if verb == "remove":
                row.items.filter(pk__in=ids, removed_at__isnull=True).update(removed_at=timezone.now(), updated_at=timezone.now())
            elif verb == "restore":
                cutoff = timezone.now() - timedelta(days=30)
                if any(item.removed_at is None or item.removed_at <= cutoff for item in items):
                    raise research.ResearchConflict("恢复期限已过或作品已恢复，请重新读取回收站。")
                if row.items.filter(removed_at__isnull=True).count() + len(items) > MAX_ITEMS:
                    raise ValidationError("恢复后将超过1000部作品，请先整理书单。")
                row.items.filter(pk__in=ids).update(removed_at=None, updated_at=timezone.now())
            else:
                if any(item.removed_at is None for item in items):
                    raise ValidationError("只能彻底移除回收站中的作品。")
                row.items.filter(pk__in=ids).delete()
            touch(row)
        elif verb == "move":
            items = list(row.items.filter(removed_at__isnull=True).order_by("order", "created_at", "id"))
            pos = next((index for index, item in enumerate(items) if item.pk == data["item_id"]), None)
            if pos is None:
                raise NotFound("待排序作品已不在书单中。")
            other = pos + data["direction"]
            if 0 <= other < len(items):
                items[pos], items[other] = items[other], items[pos]
                for index, item in enumerate(items):
                    item.order = index
                ReadingListItem.objects.bulk_update(items, ["order"])
                touch(row)
        elif verb == "delete":
            row.delete()
    receipt = KnowledgeSaveReceipt.objects.create(user=user, request_id=data["request_id"],
        target_key=sha256(f"booklist:{pk}".encode()).hexdigest(), fingerprint=fingerprint, applied_saved=verb != "delete")
    return result(user, pk, receipt)


@transaction.atomic
def purge_expired_owner(user):
    privacy.lock_owner(user)
    expired = ReadingListItem.objects.filter(reading_list__user=user, removed_at__lte=timezone.now() - timedelta(days=30))
    rows = list(expired.order_by("removed_at", "id").values_list("id", "reading_list_id")[:1000])
    if rows:
        ReadingListItem.objects.filter(pk__in=[pk for pk, _ in rows]).delete()
        ReadingList.objects.filter(user=user, pk__in={pk for _, pk in rows}).update(updated_at=timezone.now())
    return len(rows)
