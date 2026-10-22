"""Read-only publication desk over the canonical revision and delivery ledger."""
from hashlib import sha256
import json

from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from django.utils import timezone

from catalog.contracts.fields import FIELD_CONTRACTS
from catalog.models import Edition, EditorialRevision, KnowledgePublicationEvent
from catalog.services.publication_commands import PublicationCommandError, catalog_publication_state, prepare_revision


def version(edition):
    drafts = list(EditorialRevision.objects.filter(target_type="work", target_id=edition.work_id).order_by("-revision").values_list("pk", "updated_at")[:1])
    latest = list(edition.catalog_revisions.order_by("-revision").values_list("pk", "updated_at")[:1])
    return sha256(json.dumps([edition.pk, edition.state, edition.updated_at, edition.work.updated_at,
                            edition.active_catalog_revision_id, latest, drafts], default=str).encode()).hexdigest()


def check_version(edition, expected):
    if expected != version(edition):
        raise PublicationCommandError("发布状态或内容已经变化，请重新检查影响范围与版本后继续。")


def revision_row(row, edition):
    current = bool(row.pk == edition.active_catalog_revision_id and edition.state == "published" and row.status == "active" and row.metadata_ready)
    return {"id": str(row.pk), "revision": row.revision, "title": row.snapshot.get("work", {}).get("title", ""),
        "status": row.status, "created_at": row.created_at, "activated_at": row.activated_at,
        "created_by": (row.created_by.display_name or row.created_by.get_username()) if row.created_by else "",
        "note": str(row.provenance.get("reason") or ""),
        "changed_fields": [FIELD_CONTRACTS[name].label if name in FIELD_CONTRACTS else {"catalog_publish": "正式发布", "catalog_withdraw": "撤回公开", "document_revision": "阅读原文", "asset": "阅读文件", "fulltext_ready": "全文索引"}.get(name, "关联内容") for name in row.changed_fields],
        "is_current": current, "can_rollback": bool(edition.state == "published" and not current and row.activated_at and row.status in {"active", "superseded"})}


def snapshot_fields(snapshot):
    work, edition = snapshot.get("work", {}), snapshot.get("edition", {})
    authors = "、".join(row.get("name", "") for row in snapshot.get("contributions", []) if row.get("role") == "author")
    names = lambda section, key: "、".join(row.get("name", "") for row in snapshot.get(section, {}).get(key, []))
    return {"title": ("标题", work.get("title", "")), "original_title": ("原文标题", work.get("original_title", "")),
        "abstract": ("简介", work.get("abstract", "")), "authors": ("作者", authors),
        "version_label": ("出版版本", edition.get("version_label", "")), "publisher": ("出版机构", edition.get("publisher", "")),
        "publication_year": ("出版年", str(edition.get("publication_year") or "")),
        "theories": ("理论与概念", names("knowledge", "nodes")), "topics": ("主题", names("knowledge", "topics")),
        "disciplines": ("学科", names("classification", "disciplines")),
        "document": ("阅读文件", "已保存阅读文件关联" if snapshot.get("document", {}).get("asset_id") else "仅书目")}


def review_details(edition, preparation):
    """PDF 136 read model. Gate decisions remain in the original preflight."""
    from catalog.models import Asset, KnowledgeNode, Person, TheorySchool, Topic
    from catalog.services.publication_commands import editorial_draft_applies_to_edition

    changes = {row["field"]: row for row in preparation["changes"]}
    public = catalog_publication_state(edition)
    current = edition.active_catalog_revision if public["catalog_revision_active"] else None
    draft = EditorialRevision.objects.filter(target_type="work", target_id=edition.work_id, status="draft").select_related("created_by").order_by("-revision").first()
    if not editorial_draft_applies_to_edition(draft, edition):
        draft = None
    asset_id = changes.get("reader_asset", {}).get("after")
    asset = edition.assets.filter(pk=asset_id).first() if asset_id else None
    previous_asset = edition.assets.filter(pk=current.reader_asset_id).first() if current and current.reader_asset_id else None
    groups = []
    for field, title, model, label in (("theories", "关联理论", KnowledgeNode, "canonical_name_zh"), ("authors", "关联责任者", Person, "preferred_name"), ("topics", "关联主题", Topic, "name")):
        row = changes.get(field, {})
        before, after = [str(value) for value in row.get("before") or []], [str(value) for value in row.get("after") or []]
        names = {str(obj.pk): str(getattr(obj, label) or getattr(obj, "canonical_name_en", "") or "名称待确认") for obj in model.objects.filter(pk__in=set(before + after))}
        if field == "theories":
            names.update({str(obj.pk): obj.name for obj in TheorySchool.objects.filter(pk__in=set(before + after))})
        groups.append({"title": title, "field": field, "count": len(after), "items": [
            {"id": identifier, "label": names.get(identifier, "原关联对象已不可用"), "change": "removed" if identifier not in after else "added" if identifier not in before else "unchanged"}
            for identifier in dict.fromkeys(after + before)]})
    mode = changes.get("publication_mode", {}).get("after") or edition.publication_mode
    bibliography = mode == Edition.PublicationMode.BIBLIOGRAPHIC
    if bibliography:
        asset = None
    file_href = f"/admin/library/works/{edition.work_id}/files?edition={edition.pk}&tab=files"
    work_href = f"/admin/library/works/{edition.work_id}?edition={edition.pk}"
    checks = [
        {"key": "file", "title": "PDF 文件", "state": "notice" if bibliography else "ready" if asset and asset.validation_status == Asset.ValidationStatus.VALID else "warning", "detail": "仅公开书目，无阅读或下载文件" if bibliography else f"已关联阅读文件，共 {asset.page_count} 页" if asset else "阅读文件尚未就绪", "href": file_href},
        {"key": "ocr", "title": "OCR 识别", "state": "notice" if bibliography else "ready" if edition.ocr_status in {"not_required", "succeeded"} else "warning", "detail": "书目发布不依赖 OCR" if bibliography else edition.get_ocr_status_display(), "href": file_href},
        {"key": "pages", "title": "页面定位", "state": "notice" if bibliography else "ready" if edition.page_label_status == "ready" else "warning", "detail": "仅书目，无原文页定位" if bibliography else edition.get_page_label_status_display(), "href": work_href + "#reader"},
        {"key": "index", "title": "关联与索引", "state": "notice", "detail": "发布后按正式修订异步更新；当前全文" + ("已就绪" if public["fulltext_ready"] else "未就绪") + "，智能检索" + edition.get_semantic_index_status_display(), "href": work_href + "#publication"},
        {"key": "rights", "title": "权限与公开范围", "state": "notice", "detail": ("仅公开书目信息" if bibliography else f"阅读文件：{asset.get_access_status_display()}" if asset else "阅读文件尚未关联") + "；发布者须确认本次公开授权", "href": file_href.replace("tab=files", "tab=rights")},
    ]
    return {"current": revision_row(current, edition) if current else None, "saved_at": draft.updated_at if draft else max(edition.updated_at, edition.work.updated_at),
            "saved_by": (draft.created_by.display_name or draft.created_by.get_username()) if draft and draft.created_by else "", "note": draft.change_note if draft else "",
            "page_count_before": previous_asset.page_count if previous_asset else None, "page_count_after": asset.page_count if asset else None,
            "relations": groups, "checks": checks}


def desk(edition, *, page=1, selected_revision=None, impact_page=1, include_review=False):
    from catalog.services.edition_file_workspace import impacts
    edition = Edition.objects.select_related("work", "active_catalog_revision").get(pk=edition.pk)
    current_version = version(edition)
    preparation = prepare_revision(edition)
    selected = Paginator(edition.catalog_revisions.select_related("created_by").order_by("-revision"), 20).page(page)
    public = catalog_publication_state(edition)
    snapshot = edition.active_catalog_revision.snapshot if public["catalog_revision_active"] else {}
    rows = [revision_row(row, edition) for row in selected.object_list]
    history = {"count": selected.paginator.count, "page": selected.number, "pages": selected.paginator.num_pages, "results": rows}
    detail = None
    if selected_revision:
        row = get_object_or_404(edition.catalog_revisions.select_related("created_by"), pk=selected_revision)
        before, after = snapshot_fields(snapshot), snapshot_fields(row.snapshot)
        changes = [{"field": name, "label": label, "before": before[name][1], "after": value,
                    "before_display": str(before[name][1] or ""), "after_display": str(value or ""),
                    "change": "unchanged" if before[name][1] == value else "changed"} for name, (label, value) in after.items()]
        if snapshot.get("document") != row.snapshot.get("document"):
            entry = next(change for change in changes if change["field"] == "document")
            entry.update(change="changed", after_display=f"{entry['after_display']}（文件或文档修订与当前公开版不同）")
        detail = {"revision": revision_row(row, edition), "changes": changes,
                  "notice": "比较历史保存的书目与关联摘要。原PDF、原文页与引用不迁移，完整修订身份始终保留。"}
    changes = {row["field"]: row for row in preparation["changes"]}
    title = changes.get("title", {}).get("after_display") or edition.work.title
    scope = [{"title": "书目详情", "detail": "以正式修订更新书目信息；撤回后停止公开此版本。", "href": public["public_url"]},
             {"title": "在线阅读与引用", "detail": "阅读文件和文档修订按正式版本切换，已有引用仍保存原文件与页定位。", "href": f"/admin/library/works/{edition.work_id}/files?edition={edition.pk}"},
             {"title": "检索索引", "detail": "由原发布任务异步更新；页面公开与索引处理状态分别核对。", "href": f"/admin/library/works/{edition.work_id}?edition={edition.pk}#publication"}]
    for name in ("authors", "theories", "topics", "disciplines", "subdisciplines"):
        row = changes.get(name)
        if row and (row["before_display"] or row["after_display"]):
            scope.append({"title": row["label"], "detail": f"当前公开：{row['before_display'] or '未关联'}；已保存：{row['after_display'] or '未关联'}。关联对象仍需各自满足公开条件。", "href": f"/admin/library/works/{edition.work_id}?edition={edition.pk}#knowledge"})
    events = [{"id": str(row.pk), "revision": row.catalog_revision.revision, "action": row.get_event_type_display(),
               "status": row.status, "created_at": row.created_at, "processed_at": row.processed_at,
               "actor": (row.actor.display_name or row.actor.get_username()) if row.actor else "",
               "detail": "需要检查原发布任务，已保存内容保留。" if row.status in {"failed", "dead_letter"} else "以当前公开修订与各处理结果为准。"}
              for row in KnowledgePublicationEvent.objects.filter(catalog_revision__edition=edition).select_related("catalog_revision", "actor").order_by("-created_at")[:20]]
    dependencies = impacts(edition, page=impact_page)
    review = review_details(edition, preparation) if include_review else None
    fresh = Edition.objects.select_related("work").get(pk=edition.pk)
    check_version(fresh, current_version)
    return {"edition_id": str(edition.pk), "work_id": str(edition.work_id), "version": current_version, "checked_at": timezone.now(),
            "title": title, "authors": changes.get("authors", {}).get("after_display", ""), "publication": public,
            "preparation": preparation, "history": history, "selected": detail, "impacts": scope, "dependencies": dependencies, "review": review,
            "events": events, "events_limited": len(events) == 20, "workbench_url": f"/admin/library/works/{edition.work_id}?edition={edition.pk}#publication",
            "preview_url": f"/admin/preview/works/{edition.pk}",
            "notice": "影响范围按已有书目关联与馆藏证据列出，不推算访问量或未建立的引用关系。恢复单一版本不会自动恢复其他已撤回对象。"}
