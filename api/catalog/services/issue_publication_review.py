"""Saved-issue review on the existing revision ledger, with shared publish checks."""
from math import ceil

from django.utils import timezone

from catalog.models import MediaRendition
from catalog.services.editorial_blocks import body_payload, block_references
from catalog.services.publication_eligibility import public_editions


def checks(payload):
    rows = []
    def add(code, severity, title, detail, section="body", block_id="", item_id=""):
        rows.append({"code": code, "severity": severity, "title": title, "detail": detail,
                     "section": section, "block_id": block_id, "item_id": item_id})
    blocks = payload.get("body_blocks", [])
    _, problems = body_payload(blocks, public=True)
    for problem in problems:
        add("source_unavailable", "blocking", "原文或关联资料暂不可公开", problem["detail"], block_id=problem.get("block_id") or "")
    if not payload.get("title", "").strip():
        add("title_missing", "blocking", "文章标题未填写", "填写读者可以识别的文章标题。", "identity")
    if not payload.get("items") and not any(row.get("text", "").strip() or row.get("type") == "image" or block_references(row) for row in blocks):
        add("empty_article", "blocking", "尚无可发布内容", "至少需要一段正式文章内容或一项阅读推荐。")
    edition_ids = [row.get("edition_id") for row in payload.get("items", []) if row.get("kind") == "catalog"]
    editions = {str(row.pk): str(row.work_id) for row in public_editions().filter(pk__in=edition_ids)}
    for item in payload.get("items", []):
        if item.get("kind") == "catalog" and editions.get(item.get("edition_id")) != item.get("work_id"):
            add("item_unavailable", "blocking", "推荐馆藏不可公开", f"{item.get('title') or '这项资料'}尚未公开、已撤回或不属于所选作品。", "items", item_id=item["id"])
        elif item.get("kind") == "planned":
            add("planned_item", "notice", "计划书目尚需核对馆藏链接", f"{item.get('title') or '计划书目'}将按实际馆藏关联状态展示。", "items", item_id=item["id"])
    media = []
    if payload.get("cover_rendition_id"):
        media.append((payload["cover_rendition_id"], "主图", "cover", ""))
    if (payload.get("article_metadata") or {}).get("curator_portrait_id"):
        media.append((payload["article_metadata"]["curator_portrait_id"], "公开署名头像", "identity", ""))
    for index, block in enumerate(blocks):
        if block["type"] == "analysis" and block.get("style", "paragraph") == "paragraph" and block.get("text", "").strip() and not block.get("references"):
            add("analysis_source_missing", "blocking", "缺少分析所依据的资料", f"第{index+1}块来源分析尚未关联依据；请添加真实材料或改为人工导读。", block_id=block.get("id", ""))
        if block["type"] == "image":
            if block.get("image_rendition_id"):
                media.append((block["image_rendition_id"], f"第{index+1}块图像", "body", block.get("id", "")))
            else:
                add("image_missing", "warning", "图像资料尚缺图片", f"第{index+1}块仅有图题和来源说明。", block_id=block.get("id", ""))
        if block["type"] == "quote" and not block.get("source", "").strip():
            add("quote_source_missing", "blocking", "缺少引文出处", f"第{index+1}块引文尚未填写真实出处。", block_id=block.get("id", ""))
        if block["type"] == "comparison" and any(not cell.get("evidence") for row in block.get("rows", []) for cell in row.get("cells", [])):
            add("comparison_gap", "warning", "比较内容仍有材料缺口", f"第{index+1}块部分比较维度无直接原文，请核对其缺口说明。", block_id=block.get("id", ""))
    renditions = {str(row.pk): row for row in MediaRendition.objects.filter(pk__in=[row[0] for row in media])}
    for key, title, section, block_id in media:
        rendition = renditions.get(key)
        if not rendition:
            add("media_unavailable", "blocking", f"{title}不可用", "所选图片版本已不存在，请重新选择。", section, block_id)
        elif not any(str(rendition.metadata_snapshot.get(field) or "").strip() for field in ("rights", "license")):
            add("media_rights_missing", "warning", f"{title}版权信息待核对", "所选图片版本尚无权利或许可说明，请在素材中补充并重新选择确认的版本。", section, block_id)
    if payload.get("cover_url") and not payload.get("cover_rendition_id"):
        add("legacy_cover_rights", "warning", "旧主图版权信息待核对", "旧链接没有可核对的素材权利记录，可重新选择带出处的图片。", "cover")
    return rows


def review(issue, actor):
    from catalog.services import editorial_issues as ledger
    from catalog.services.public_editorial import public_metadata, directory_related
    from common.capabilities import Capability, has_capability
    version = ledger.edit_version("recommendation_issue", issue.pk)
    latest = ledger._latest("recommendation_issue", issue.pk)
    current = ledger.public_issue_revision(issue)
    if current and (current.status != "published" or issue.display_from and issue.display_from > timezone.now() and current.pk == issue.active_revision_id):
        current = None
    draft = ledger.issue_draft_payload(issue)
    before = current.materialized_preview if current else {}
    issues = checks(draft)
    changed = []
    def display(value):
        if isinstance(value, dict) and "text" in value:
            return "\n".join(part for part in [value.get("text", ""), value.get("source", ""), value.get("alt_text", ""), value.get("url", ""),
                f"{value['heading_level']}级标题" if value.get("heading_level") else "",
                f"{len(block_references(value))}项准确来源" if block_references(value) else "",
                *[f"{cell['dimension']}：{cell['text']}" for row in value.get("rows", []) for cell in row.get("cells", [])]] if part)
        if isinstance(value, dict) and "kind" in value and "title" in value:
            return "\n".join(str(value.get(key) or "") for key in ("title", "authors", "version_note", "note", "isbn", "doi"))
        if isinstance(value, (dict, list)):
            return "已填写资料" if value else "未填写"
        return str(value or "")
    def diff(field, label, old, new):
        old_text, new_text = display(old), display(new)
        if field in {"cover_rendition_id", "cover_url"}:
            old_text, new_text = ("已选主图" if old else "未选择"), ("已选主图" if new else "未选择")
        if field.endswith(".order"):
            old_text, new_text = f"{len(old)}项", f"{len(new)}项，按草稿顺序展示"
        if old != new and old_text == new_text:
            new_text += "\n内容关联、格式或图片版本有调整，请结合页面预览核对。"
        changed.append({"field": field, "label": label, "before": old, "after": new, "before_display": old_text, "after_display": new_text,
                        "change": "unchanged" if old == new else "added" if old is None else "removed" if new is None else "changed"})
    for field, label in (("title", "标题"), ("introduction", "导语"), ("issue_label", "期名"), ("public_byline", "公开署名"),
                         ("cover_rendition_id", "主图版本"), ("cover_url", "主图链接"), ("display_from", "展示时间"), ("article_metadata", "文章资料")):
        diff(field, label, before.get(field), draft.get(field))
    for key, label in (("body_blocks", "正文块"), ("items", "相关书目")):
        old = {row.get("id") or f"legacy-{index}": row for index, row in enumerate(before.get(key, []))}
        new = {row.get("id") or f"legacy-{index}": row for index, row in enumerate(draft.get(key, []))}
        old_order, new_order = list(old), list(new)
        if old_order != new_order:
            diff(f"{key}.order", f"{label}顺序", old_order, new_order)
        for position, identity in enumerate(dict.fromkeys([*new, *old])):
            diff(f"{key}.{identity}", f"{label} {position+1}", old.get(identity), new.get(identity))
    preview = ledger.issue_payload(issue)
    preview.pop("selection_workspace", None)
    preview["body_blocks"], _ = body_payload(draft.get("body_blocks", []), public=True)
    # Draft media is available only through authenticated media endpoints.
    for block in preview["body_blocks"]:
        if block.get("type") == "image" and block.get("image_rendition_id"):
            block["image_url"] = f"/api/catalog/admin/media/renditions/{block['image_rendition_id']}/file/" if block.get("source_status") == "available" else ""
    preview["article_metadata"], preview["curator"] = public_metadata(draft, public=True)
    portrait = preview["article_metadata"].get("curator_portrait_id")
    if portrait and preview["curator"]["portrait_url"]:
        preview["curator"]["portrait_url"] = f"/api/catalog/admin/media/renditions/{portrait}/file/"
    preview["related"] = directory_related([{"id": str(issue.pk), "article_metadata": preview["article_metadata"], "href": f"/recommendations/{issue.slug}"}])
    preview["published_at"] = latest.published_at.isoformat() if latest and latest.published_at else None
    length = sum(len(row.get("text", "")) for row in preview["body_blocks"])
    preview["reading_minutes"] = max(1, ceil(length/400)) if length else None
    for item in preview["items"]:
        for key in ("cataloging_session_id", "workbench_url", "match_candidates"):
            item.pop(key, None)
    ledger._check_version("recommendation_issue", issue.pk, version)
    blocking = sum(row["severity"] == "blocking" for row in issues)
    return {"edit_version": version, "checked_at": timezone.now(), "draft_revision_id": str(latest.pk) if latest else None,
            "current_revision_id": str(current.pk) if current else None, "draft_at": latest.created_at if latest else None,
            "current_at": current.published_at if current else None, "checks": issues, "changes": changed,
            "blocking_count": blocking, "warning_count": sum(row["severity"] != "blocking" for row in issues),
            "has_draft": bool(latest and latest.status == "draft"),
            "can_publish": bool(latest and latest.status == "draft" and not blocking and has_capability(actor, Capability.PUBLISH_AUTHORITY)),
            "actor_label": actor.display_name or actor.get_username(), "public_url": f"/recommendations/{issue.slug}",
            "reader_preview": preview}
