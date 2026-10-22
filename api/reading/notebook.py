"""R28 projects the original annotations and bookmarks, always for their owner."""
import heapq
import json
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

from django.db import transaction
from django.db.models import CharField, Count, Value
from django.urls import reverse
from rest_framework.exceptions import NotFound, ValidationError

from catalog.models import Edition
from catalog.services.publication_eligibility import public_edition_q
from . import privacy, research
from .knowledge_models import KnowledgeSaveReceipt
from .models import Annotation, Bookmark, ResearchProject
from .services import decrypt_private_text, encrypt_private_text

PAGE_SIZE = 20
SEARCH_LIMIT = 5000
MODELS = {"annotations": Annotation, "bookmarks": Bookmark}


def annotation_retired(user, pk, *, retire=False):
    """A minimal tombstone prevents a late create retry from undoing erasure."""
    request_id = uuid5(NAMESPACE_URL, f"stl:annotation-erased:{pk}")
    key = sha256(f"annotation-erased:{pk}".encode()).hexdigest()
    if retire:
        receipt, _ = KnowledgeSaveReceipt.objects.get_or_create(user=user, request_id=request_id,
            defaults={"target_key": key, "fingerprint": "", "applied_saved": False})
        if receipt.target_key != key:
            raise research.ResearchConflict("删除回执冲突，请保留原记录并重新核对。")
        return True
    return KnowledgeSaveReceipt.objects.filter(user=user, request_id=request_id, target_key=key, applied_saved=False).exists()


def collection(user, category):
    return MODELS[category].objects.filter(user=user).select_related("asset__edition", "page")


def owned(user, category, pk):
    row = collection(user, category).filter(pk=research.identifier(pk)).first()
    if row is None:
        raise NotFound("这条本人阅读记录已不存在。")
    return row


def published_work(work_id):
    edition = Edition.objects.filter(public_edition_q(), work_id=work_id, is_primary=True).select_related("active_catalog_revision").first()
    if edition is None:
        return {"id": str(work_id), "title": "来源当前不可用", "authors": [], "year": None, "href": None, "cover_url": None}
    snapshot = edition.active_catalog_revision.snapshot or {}
    work, version = snapshot.get("work") or {}, snapshot.get("edition") or {}
    media = work.get("cover_media") or {}
    cover = reverse("public-work-cover", kwargs={"work_id": work_id}) if media or work.get("cover") else None
    if cover and media.get("primary_rendition_id"):
        cover += f"?rendition={media['primary_rendition_id']}"
    return {"id": str(work_id), "title": work.get("title") or "题名待补", "authors": [
        str(value.get("name") or (value.get("person") or {}).get("preferred_name") or "")
        for value in snapshot.get("contributions", []) if isinstance(value, dict) and value.get("role") == "author"],
        "year": version.get("publication_year"), "href": f"/works/{work_id}", "cover_url": cover}


def record(user, category, row):
    is_note = category == "annotations"
    ref = research.annotation_source(user, row) if is_note else None
    if not is_note and row.page.asset_id == row.asset_id:
        edition = research.source_queryset("edition", research.access_for(user)).filter(active_catalog_revision__reader_asset_id=row.asset_id).first()
        if edition:
            ref = {"asset_id": str(row.asset_id), "pdf_page": row.page.index,
                "document_revision_id": str(edition.active_catalog_revision.document_revision_id)}
    source = research.resolve_reference(ref, user) if ref else {"source_status": "unavailable"}
    tags = json.loads(decrypt_private_text(row.tags_ciphertext) or "[]") if is_note else []
    return {**privacy.target_of(row, category), "key": f"{category}:{row.pk}", "owner_id": str(user.pk),
        "kind": row.kind if is_note else "bookmark", "asset_id": str(row.asset_id), "page_id": str(row.page_id),
        "pdf_page": row.page.index, "work": published_work(row.asset.edition.work_id),
        "body": decrypt_private_text(row.body_ciphertext) if is_note else "", "tags": tags,
        "label": "" if is_note else row.label, "saved_quote": row.quote if is_note else "",
        "source": source, "created_at": row.created_at, "updated_at": row.updated_at,
        "notice": "保存的摘录仅本人可见；当前原文需另行核对。" if source.get("source_status") != "available" else ""}


def linked_targets(user, project_id):
    project = research.owned(ResearchProject, user, project_id)
    data = research.unpack(project)
    active = {research.reference_identity(ref) for ref in data.get("selections", [])}
    return [row for row in data.get("notebook_links", []) if row.get("reference_id") in active]


def branches(user, options):
    result = {}
    links = linked_targets(user, options["project"]) if options.get("project") else None
    for category in MODELS:
        rows = collection(user, category)
        kind = options.get("kind", "all")
        if (kind == "bookmark" and category == "annotations") or (kind not in {"all", "bookmark"} and category == "bookmarks"):
            continue
        if category == "annotations" and kind != "all":
            rows = rows.filter(kind__in=["highlight", "underline"] if kind == "excerpt" else ["note"])
        for key, field in (("work", "asset__edition__work_id"), ("asset", "asset_id")):
            if options.get(key):
                rows = rows.filter(**{field: options[key]})
        if options.get("start"):
            rows = rows.filter(created_at__date__gte=options["start"])
        if options.get("end"):
            rows = rows.filter(created_at__date__lte=options["end"])
        if links is not None:
            rows = rows.filter(pk__in=[value["id"] for value in links if value.get("category") == category])
        result[category] = rows
    return result


def listing(user, options):
    queries = branches(user, options)
    total = sum(rows.count() for rows in queries.values())
    page, q = options["page"], options["q"].strip().casefold()
    start, stop = (page - 1) * PAGE_SIZE, page * PAGE_SIZE
    reverse = options["order"] == "newest"
    if q:
        if total > SEARCH_LIMIT:
            raise ValidationError({"q": "所选范围超过5000条，请按作品、日期或类型缩小范围后搜索；没有截断结果。"})
        total, metadata = 0, {}
        def matches():
            nonlocal total
            for category, rows in queries.items():
                for row in rows.order_by("id").iterator(chunk_size=100):
                    key = row.asset.edition.work_id
                    if key not in metadata:
                        metadata[key] = published_work(key)
                    work = metadata[key]
                    text = [work["title"], *work["authors"]]
                    text.extend([decrypt_private_text(row.body_ciphertext), row.quote, decrypt_private_text(row.tags_ciphertext)] if category == "annotations" else [row.label])
                    if q in " ".join(text).casefold():
                        total += 1
                        yield row.updated_at, str(row.pk), category
        selected = (heapq.nlargest if reverse else heapq.nsmallest)(stop, matches())[start:stop]
    else:
        parts = [rows.order_by().annotate(record_category=Value(category, output_field=CharField())).values_list("id", "updated_at", "record_category") for category, rows in queries.items()]
        union = parts[0].union(*parts[1:], all=True) if len(parts) > 1 else parts[0]
        fields = ("-updated_at", "-id", "-record_category") if reverse else ("updated_at", "id", "record_category")
        selected = [(stamp, str(pk), category) for pk, stamp, category in union.order_by(*fields)[start:stop]]
    if page > 1 and start >= total:
        raise NotFound("这一页已没有记录，请返回第一页。")
    results = []
    for stamp, pk, category in selected:
        row = owned(user, category, pk)
        if row.updated_at != stamp:
            raise research.ResearchConflict("记录已变化，请重新读取当前页。")
        results.append(record(user, category, row))
    return {"owner_id": str(user.pk), "count": total, "page": page, "total_pages": max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE), "results": results}


def choices(user, kind, page):
    start = (page - 1) * PAGE_SIZE
    if kind == "projects":
        rows = ResearchProject.objects.filter(user=user, archived=False).order_by("-updated_at", "-id")
        total = rows.count()
        results = [{"id": str(row.pk), "title": research.unpack(row).get("title") or "未命名研究", "revision": row.revision} for row in rows[start:start + PAGE_SIZE]]
    else:
        parts = [collection(user, category).order_by().values_list("asset__edition__work_id", flat=True) for category in MODELS]
        ids = parts[0].union(parts[1]).order_by("asset__edition__work_id")
        total = ids.count()
        selected = list(ids[start:start + PAGE_SIZE])
        counts = {}
        for category in MODELS:
            for row in collection(user, category).filter(asset__edition__work_id__in=selected).order_by().values("asset__edition__work_id").annotate(total=Count("pk")):
                pk = row["asset__edition__work_id"]
                counts[pk] = counts.get(pk, 0) + row["total"]
        results = [{**published_work(pk), "count": counts[pk]} for pk in selected]
    return {"owner_id": str(user.pk), "count": total, "page": page, "total_pages": max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE), "results": results}


def project_receipt(user, project_id, request_id):
    key = sha256(f"notebook-project:{project_id}".encode()).hexdigest()
    receipt = KnowledgeSaveReceipt.objects.filter(user=user, request_id=request_id, target_key=key).first()
    if receipt is None:
        raise NotFound("尚未找到此账户的原请求回执。")
    project = ResearchProject.objects.filter(user=user, pk=project_id).first()
    return {"owner_id": str(user.pk), "project_id": str(project_id), "exists": project is not None,
        "revision": project.revision if project else None}


@transaction.atomic
def edit(user, category, pk, data):
    privacy.lock_owner(user)
    row = owned(user, category, pk)
    body = data.get("body")
    if privacy.version(row) != data["expected_version"]:
        # A response lost after an exact save may be acknowledged without writing twice.
        same = ((category == "annotations" and body == decrypt_private_text(row.body_ciphertext)
            and data.get("tags", []) == json.loads(decrypt_private_text(row.tags_ciphertext) or "[]"))
            or (category == "bookmarks" and data.get("label") == row.label and body is None))
        if not same:
            raise research.ResearchConflict("这条记录已修改，请保留输入并重新读取。")
        return record(user, category, row)
    if category == "annotations":
        if body is None or "label" in data:
            raise ValidationError("笔记需提供正文与标签。")
        if len(body) > max(500, len(decrypt_private_text(row.body_ciphertext))):
            raise ValidationError({"body": "新笔记最多500字；既有长笔记可以保留原长度。"})
        row.body_ciphertext = encrypt_private_text(body)
        row.tags_ciphertext = encrypt_private_text(json.dumps(data.get("tags", []), ensure_ascii=False))
        row.save(update_fields=["body_ciphertext", "tags_ciphertext", "updated_at"])
    else:
        if body is not None or "label" not in data:
            raise ValidationError("书签需提供名称；添加笔记请在原文位置保存。")
        row.label = data["label"]
        row.save(update_fields=["label", "updated_at"])
    return record(user, category, row)


@transaction.atomic
def add_to_project(user, data):
    privacy.lock_owner(user)
    project = research.owned(ResearchProject, user, data["project_id"], lock=True)
    key = sha256(f"notebook-project:{project.pk}".encode()).hexdigest()
    fingerprint = sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
    receipt = KnowledgeSaveReceipt.objects.filter(user=user, request_id=data["request_id"]).first()
    if receipt:
        if receipt.target_key != key or receipt.fingerprint != fingerprint:
            raise research.ResearchConflict("原请求已用于其他内容，请核对原结果。")
        return {"owner_id": str(user.pk), "project_id": str(project.pk), "revision": project.revision}
    refs, links = [], []
    for target in data["targets"]:
        row = privacy.verify_target(user, target)
        current = record(user, target["category"], row)
        source = current["source"]
        if source.get("source_status") != "available":
            raise ValidationError("所选记录中有来源当前不可核对的项目，请调整选择；原笔记仍保留。")
        ref = research.compact_reference(source)
        refs.append(ref)
        links.append({"category": target["category"], "id": str(row.pk), "reference_id": research.reference_identity(ref)})
    project = research.change_selection(user, project.pk, {"action": "add", "expected_revision": data["expected_revision"], "references": refs, "note": data.get("note", "")})
    payload = research.unpack(project)
    saved = payload.setdefault("notebook_links", [])
    for link in links:
        if link not in saved:
            saved.append(link)
    if len(saved) > 2000:
        raise ValidationError("研究已关联2000条阅读记录，请先整理现有选材。")
    research.save_data(project, payload)
    KnowledgeSaveReceipt.objects.create(user=user, request_id=data["request_id"], target_key=key, fingerprint=fingerprint, applied_saved=True)
    return {"owner_id": str(user.pk), "project_id": str(project.pk), "revision": project.revision}


@transaction.atomic
def add_bookmark_note(request, pk, data):
    """An independent authored note; the bookmark and its page remain unchanged."""
    user = request.user
    privacy.lock_owner(user)
    bookmark = owned(user, "bookmarks", pk)
    previous = Annotation.objects.filter(user=user, pk=data["request_id"]).first()
    expected_selector = {"page_index": bookmark.page.index, "notebook_bookmark_id": str(bookmark.pk)}
    if previous:
        if (previous.asset_id != bookmark.asset_id or previous.page_id != bookmark.page_id or previous.kind != "note"
                or previous.selector != expected_selector or decrypt_private_text(previous.body_ciphertext) != data["body"]
                or json.loads(decrypt_private_text(previous.tags_ciphertext) or "[]") != data.get("tags", [])):
            raise research.ResearchConflict("原请求内容已有变化，请核对已保存笔记。")
        return record(user, "annotations", previous)
    if privacy.version(bookmark) != data["expected_version"]:
        raise research.ResearchConflict("书签已修改，请保留输入并重新读取。")
    from .serializers import AnnotationSerializer
    current = record(user, "bookmarks", bookmark)
    # Use the original encrypted writer and retirement guard. The source check is
    # represented explicitly for old files; this never opens a withdrawn file.
    row = AnnotationSerializer(context={"request": request}).create({
        "request_id": data["request_id"], "asset": bookmark.asset, "page": bookmark.page,
        "kind": "note", "selector": expected_selector, "body": data["body"], "tags": data.get("tags", []),
        "orphaned": current["source"]["source_status"] != "available"})
    return record(user, "annotations", row)
