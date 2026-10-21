"""Explicit responsibility ranges within one edition; never infer a chapter author."""
from uuid import UUID

from catalog.models import Asset, DocumentOutlineRevision, DocumentRevision, Page


class ContributionScopeError(ValueError):
    pass


def normalize_contribution_scope(value):
    if value == {} or value is None:
        return {"kind": "edition"}
    if not isinstance(value, dict) or value.get("kind") not in {"edition", "chapter"}:
        raise ContributionScopeError("责任范围须为整版或明确章节。")
    if value["kind"] == "edition":
        if value.get("chapters") is not None and value.get("chapters") != []:
            raise ContributionScopeError("整版责任不能同时指定章节。")
        return {"kind": "edition"}
    chapters = value.get("chapters")
    if not isinstance(chapters, list) or not 1 <= len(chapters) <= 100:
        raise ContributionScopeError("章节责任须明确选择1至100个章节。")
    output, identities = [], set()
    for row in chapters:
        if not isinstance(row, dict):
            raise ContributionScopeError("章节责任格式无效。")
        try:
            ids = {key: str(UUID(str(row.get(key)))) for key in (
                "asset_id", "document_revision_id", "outline_revision_id", "outline_node_id")}
        except (ValueError, TypeError, AttributeError) as exc:
            raise ContributionScopeError("章节须绑定准确文件、正文修订、目录修订与目录条目。") from exc
        title = row.get("title")
        if not isinstance(title, str) or not title.strip() or len(title) > 600:
            raise ContributionScopeError("章节名称须为1至600字。")
        start, end = row.get("page_start"), row.get("page_end")
        if type(start) is not int or type(end) is not int or not 1 <= start <= end:
            raise ContributionScopeError("章节范围须为有效的文件起止页。")
        identity = (ids["asset_id"], ids["document_revision_id"], ids["outline_revision_id"], ids["outline_node_id"])
        if identity in identities:
            raise ContributionScopeError("同一责任者的同一章节不能重复。")
        identities.add(identity)
        output.append({**ids, "title": title.strip(), "page_start": start, "page_end": end})
    return {"kind": "chapter", "chapters": output}


def validate_contribution_scope(edition, value, *, public=False, allowed_access_statuses=None):
    scope = normalize_contribution_scope(value)
    if scope["kind"] == "edition":
        return scope
    chapters = scope["chapters"]
    assets = {str(row.pk): row for row in Asset.objects.filter(pk__in={row["asset_id"] for row in chapters})}
    documents = {str(row.pk): row for row in DocumentRevision.objects.filter(pk__in={row["document_revision_id"] for row in chapters})}
    outlines = {str(row.pk): row for row in DocumentOutlineRevision.objects.filter(pk__in={row["outline_revision_id"] for row in chapters})}
    pages = set(Page.objects.filter(asset_id__in=assets, index__in={row[key] for row in chapters for key in ("page_start", "page_end")}).values_list("asset_id", "index"))
    active = edition.active_catalog_revision if public else None
    allowed_access = {"public", "inherit"} if allowed_access_statuses is None else set(allowed_access_statuses)
    for row in chapters:
        asset, document, outline = assets.get(row["asset_id"]), documents.get(row["document_revision_id"]), outlines.get(row["outline_revision_id"])
        if (not asset or not document or not outline or asset.edition_id != edition.pk
                or document.asset_id != asset.pk or outline.asset_id != asset.pk
                or outline.document_revision_id != document.pk or not asset.sha256 or document.source_checksum != asset.sha256 or not document.is_active
                or outline.source_checksum != asset.sha256 or not outline.is_active
                or asset.kind != "normalized" or asset.status != "ready" or asset.validation_status != "valid"
                or row["page_end"] > (asset.page_count or 0) or (asset.pk, row["page_start"]) not in pages
                or (asset.pk, row["page_end"]) not in pages):
            raise ContributionScopeError("章节的文件或目录修订已变化，请核对当前准确来源。")
        if public:
            if (not active or edition.state != "published" or active.edition_id != edition.pk
                    or active.status != "active" or not active.metadata_ready or not active.fulltext_ready
                    or active.reader_asset_id != asset.pk or active.document_revision_id != document.pk
                    or asset.access_status not in allowed_access or not asset.file):
                raise ContributionScopeError("章节原文当前不可公开访问。")
        elif not document.is_active:
            raise ContributionScopeError("章节须选择当前正文修订。")
        else:
            from catalog.services.document_outline import OutlineConflict, _source_current
            try:
                _source_current(asset)
            except OutlineConflict as error:
                raise ContributionScopeError(str(error)) from error
        node = next((item for item in outline.nodes if str(item.get("id")) == row["outline_node_id"]), None)
        if not node or node.get("pdf_page") != row["page_start"] or str(node.get("title") or "").strip() != row["title"]:
            raise ContributionScopeError("章节名称和起页须与明确选择的目录条目一致。")
    return scope


def public_contribution_scope(edition, value):
    """Hide stale chapter identities and labels; never broaden them to whole-book authorship."""
    try:
        scope = validate_contribution_scope(edition, value, public=True)
    except ContributionScopeError:
        return {"kind": "chapter", "status": "unavailable", "chapters": [], "notice": "章节责任的准确来源当前不可用，请核对版本。"}
    return {**scope, "chapters": [{**row, "reader_href": f"/reader/{row['asset_id']}?page={row['page_start']}&revision={row['document_revision_id']}"}
                                 for row in scope.get("chapters", [])], "status": "available", "notice": ""}


def whole_edition_contribution(row):
    """Only these people can label or cite an entire edition as its authors."""
    scope = row.get("scope") if isinstance(row, dict) else row.scope
    return scope is None or scope == {} or (isinstance(scope, dict) and scope.get("kind") == "edition" and (scope.get("chapters") is None or scope.get("chapters") == []))
