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


def desk(edition, *, page=1, selected_revision=None, impact_page=1):
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
    fresh = Edition.objects.select_related("work").get(pk=edition.pk)
    check_version(fresh, current_version)
    return {"edition_id": str(edition.pk), "work_id": str(edition.work_id), "version": current_version, "checked_at": timezone.now(),
            "title": title, "authors": changes.get("authors", {}).get("after_display", ""), "publication": public,
            "preparation": preparation, "history": history, "selected": detail, "impacts": scope, "dependencies": dependencies,
            "events": events, "events_limited": len(events) == 20, "workbench_url": f"/admin/library/works/{edition.work_id}?edition={edition.pk}#publication",
            "preview_url": f"/admin/preview/works/{edition.pk}",
            "notice": "影响范围按已有书目关联与馆藏证据列出，不推算访问量或未建立的引用关系。恢复单一版本不会自动恢复其他已撤回对象。"}
