"""Fixed-template issue and site editing on the existing revision ledger.

No draft write mutates the public payload. Scheduling only selects a revision
which an authorized editor has already explicitly published.
"""
from copy import deepcopy
from uuid import UUID, uuid4
from urllib.parse import unquote, urlsplit

from django.db import transaction
from django.db.models import Case, DateTimeField, F, Max, Q, When
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify
from rest_framework.exceptions import ValidationError

from catalog.models import (AboutPageBlock, EditorialRevision, EditorialRevisionMedia,
                            MediaRendition, RecommendationIssue, RecommendationIssueItem,
                            SiteSetting, Edition, DocumentType)
from catalog.services.cataloging_sessions import open_cataloging_session
from catalog.services.publication_eligibility import public_editions
from ingestion.models import AuditEvent


class EditConflict(ValueError):
    pass


def safe_image_url(value):
    value = str(value or "").strip()
    if not value:
        return ""
    parsed = urlsplit(value)
    decoded_path = unquote(parsed.path)
    if parsed.scheme or parsed.netloc or not value.startswith("/") or value.startswith("//") or "\\" in value:
        raise ValidationError({"image": "请从媒体选择器选择图片，或使用本站图片路径。"})
    if "\\" in decoded_path or any(part in {".", ".."} for part in decoded_path.split("/")) or decoded_path.startswith(("/api/catalog/admin/", "/api/reading/")):
        raise ValidationError({"image": "不能将受保护的管理或私人文件链接公开。"})
    if not parsed.path.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".svg", ".avif")):
        raise ValidationError({"image": "图片路径须指向受支持的本站图片。"})
    return value


def _rendition(value):
    if not value:
        return None
    try:
        return MediaRendition.objects.get(pk=UUID(str(value)))
    except (ValueError, MediaRendition.DoesNotExist):
        raise ValidationError({"image": "所选媒体版本不存在。"})


def _latest(kind, identifier):
    return EditorialRevision.objects.filter(target_type=kind, target_id=identifier).order_by("-revision").first()


def edit_version(kind, identifier):
    latest = _latest(kind, identifier)
    if latest and kind == "recommendation_issue":
        modified = RecommendationIssueItem.objects.filter(issue_id=identifier).aggregate(value=Max("updated_at"))["value"]
        return f"{latest.pk}:{modified.isoformat() if modified else ''}"
    return str(latest.pk) if latest else "0"


def _check_version(kind, identifier, expected):
    if str(expected) != edit_version(kind, identifier):
        raise EditConflict("另一位管理员已修改此内容。当前输入已保留，请读取新版本并比较后保存。")


def _save_revision(kind, identifier, payload, actor):
    latest = _latest(kind, identifier)
    draft = EditorialRevision.objects.create(
        target_type=kind, target_id=identifier, base_revision=latest.revision if latest else 0,
        revision=(latest.revision if latest else 0) + 1, patch=payload, materialized_preview=payload,
        changed_fields=list(payload), created_by=actor, idempotency_key=f"v307:{kind}:{uuid4()}",
    )
    EditorialRevision.objects.filter(target_type=kind, target_id=identifier, status="draft").exclude(pk=draft.pk).update(status="superseded")
    rendition_ids = [payload.get("cover_rendition_id"), payload.get("config", {}).get("home_hero_rendition_id"),
                     *[row.get("cover_rendition_id") for row in payload.get("items", [])]]
    for identifier in filter(None, rendition_ids):
        rendition = _rendition(identifier)
        EditorialRevisionMedia.objects.get_or_create(editorial_revision=draft, rendition=rendition)
    AuditEvent.objects.create(actor=actor, action=f"{kind}.save_draft", object_type=kind,
                              object_id=str(draft.target_id), after={"revision": draft.revision})
    return draft


def _publish_revision(revision, actor):
    revision.status = "published"
    revision.published_by = actor
    revision.published_at = timezone.now()
    revision.save(update_fields=["status", "published_by", "published_at", "updated_at"])
    AuditEvent.objects.create(actor=actor, action=f"{revision.target_type}.publish", object_type=revision.target_type,
                              object_id=str(revision.target_id), after={"revision": revision.revision})


def _text(value, maximum=30000):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValidationError("内容必须为长度适当的文字。")
    return value.strip()


def _body(value):
    if not isinstance(value, list) or len(value) > 150:
        raise ValidationError({"body_blocks": "正文最多150个固定段落。"})
    blocks = []
    for row in value:
        if not isinstance(row, dict) or row.get("type") not in {"paragraph", "heading", "quote", "link"}:
            raise ValidationError({"body_blocks": "仅支持段落、小标题、带出处引文及链接。"})
        block = {"type": row["type"], "text": _text(row.get("text", ""))}
        if row["type"] == "quote":
            block["source"] = _text(row.get("source", ""), 1000)
            if not block["source"]:
                raise ValidationError({"body_blocks": "引文必须填写真实出处。"})
        if row["type"] == "link":
            link = _text(row.get("url", ""), 1500)
            parsed = urlsplit(link)
            if not ((parsed.scheme in {"http", "https"} and parsed.netloc) or (link.startswith("/") and not link.startswith("//"))) or "\\" in link:
                raise ValidationError({"body_blocks": "链接地址无效。"})
            block["url"] = link
        blocks.append(block)
    return blocks


def issue_draft_payload(issue):
    revision = _latest("recommendation_issue", issue.pk)
    if revision:
        return deepcopy(revision.materialized_preview)
    return {"slug": issue.slug, "title": issue.title, "issue_label": "", "introduction": "", "body_blocks": [],
            "public_byline": "", "cover_url": "", "cover_rendition_id": None, "display_from": None, "items": []}


@transaction.atomic
def create_issue(data, actor):
    title = _text(data.get("title") or "新一期书库推荐", 600)
    slug = slugify(str(data.get("slug") or ""))[:140] or f"issue-{timezone.now():%Y%m%d}-{uuid4().hex[:8]}"
    if RecommendationIssue.objects.filter(slug=slug).exists():
        raise ValidationError({"slug": "此期地址已存在。"})
    issue = RecommendationIssue.objects.create(title=title, slug=slug, created_by=actor)
    save_issue(issue.pk, {**issue_draft_payload(issue), **data, "edit_version": "0"}, actor)
    return issue


@transaction.atomic
def save_issue(identifier, data, actor):
    issue = RecommendationIssue.objects.select_for_update().get(pk=identifier)
    _check_version("recommendation_issue", issue.pk, data.get("edit_version"))
    previous = issue_draft_payload(issue)
    values = {**previous, **data}
    payload = {name: _text(values.get(name) or "", limit) for name, limit in (
        ("title", 600), ("issue_label", 120), ("introduction", 3000), ("public_byline", 240))}
    if not payload["title"]:
        raise ValidationError({"title": "请填写本期标题。"})
    # Once a URL exists its identity remains stable across corrections.
    payload["slug"] = issue.slug
    payload["body_blocks"] = _body(values.get("body_blocks", []))
    rendition = _rendition(values.get("cover_rendition_id"))
    payload["cover_rendition_id"] = str(rendition.pk) if rendition else None
    payload["cover_url"] = "" if rendition else safe_image_url(values.get("cover_url"))
    display = values.get("display_from")
    parsed = parse_datetime(str(display)) if display else None
    if display and parsed is None:
        raise ValidationError({"display_from": "展示时间格式无效。"})
    if parsed and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    payload["display_from"] = parsed.isoformat() if parsed else None
    incoming = values.get("items", [])
    if not isinstance(incoming, list) or len(incoming) > 100:
        raise ValidationError({"items": "每期最多100项推荐。"})
    payload["items"] = []
    seen = set()
    existing = {str(row.pk): row for row in issue.items.all()}
    for position, item in enumerate(incoming):
        if not isinstance(item, dict) or item.get("kind", "catalog") not in {"planned", "catalog"}:
            raise ValidationError({"items": "推荐项类型无效。"})
        item_id = str(item.get("id") or uuid4())
        try:
            UUID(item_id)
        except ValueError:
            raise ValidationError({"items": "推荐项标识无效。"})
        if item_id in seen:
            raise ValidationError({"items": "不能重复同一推荐项。"})
        seen.add(item_id)
        record = existing.get(item_id)
        if record is None:
            if RecommendationIssueItem.objects.filter(pk=item_id).exists():
                raise ValidationError({"items": "推荐项不属于本期。"})
            record = RecommendationIssueItem.objects.create(id=item_id, issue=issue)
        row = {name: _text(item.get(name) or "", limit) for name, limit in (
            ("title", 600), ("authors", 1000), ("version_note", 1500), ("isbn", 40), ("doi", 255), ("note", 6000))}
        row.update(id=item_id, kind=item.get("kind", "catalog"), position=position)
        work_id, edition_id = item.get("work_id"), item.get("edition_id")
        if row["kind"] == "catalog":
            editions = public_editions().filter(work_id=work_id)
            edition = editions.filter(pk=edition_id).first() if edition_id else editions.order_by("-is_primary", "id").first()
            if not edition:
                raise ValidationError({"items": "已有馆藏推荐须选择准确的已公开作品与版本。"})
            snapshot = edition.active_catalog_revision.snapshot or {}
            work_snapshot = snapshot.get("work", {})
            row["title"] = str(work_snapshot.get("title") or snapshot.get("title") or row["title"])
            row["authors"] = "、".join(str(person.get("name") or person.get("person", {}).get("preferred_name") or "")
                                      for person in snapshot.get("contributions", []) if person.get("role") == "author")
            row["cover_rendition_id"] = (work_snapshot.get("cover_media") or {}).get("primary_rendition_id")
            row["cover_path"] = work_snapshot.get("cover", "")
            row["version_note"] = row["version_note"] or str(snapshot.get("edition", {}).get("version_label") or "")
            row.update(work_id=str(edition.work_id), edition_id=str(edition.pk))
        else:
            if not row["title"]:
                raise ValidationError({"items": "计划项至少须填写已确认的题名。"})
            if record.cataloging_session_id and ((work_id and str(work_id) != str(record.planned_work_id)) or
                    (edition_id and str(edition_id) != str(record.cataloging_session.edition_id))):
                raise ValidationError({"items": "既有计划项的草稿身份不能替换；请新建计划项，或显式关联已公开的准确版本。"})
            if not record.cataloging_session_id:
                if edition_id or work_id:
                    selected = Edition.objects.filter(pk=edition_id, work_id=work_id, state__in=["draft", "ready"], active_catalog_revision__isnull=True).first()
                    if not selected:
                        raise ValidationError({"items": "所选计划项须为同一作品的非公开草稿版本。"})
                    session, _ = open_cataloging_session(actor=actor, edition_id=selected.pk, source_type="existing")
                else:
                    document_type = item.get("document_type", DocumentType.BOOK)
                    if document_type not in DocumentType.values:
                        raise ValidationError({"items": "计划项文献类型无效。"})
                    session, _ = open_cataloging_session(actor=actor, source_type="manual", title=row["title"],
                        document_type=document_type, request_key=uuid4())
                # Keep confirmed version clues in the real bibliographic
                # draft as well as the public item snapshot. No person is
                # guessed from a name and no existing draft is overwritten.
                from catalog.contracts.identifiers import normalize_doi, normalize_isbn, valid_doi, valid_isbn
                isbn, doi = normalize_isbn(row["isbn"]), normalize_doi(row["doi"])
                if isbn and not valid_isbn(isbn):
                    raise ValidationError({"items": "计划项ISBN校验未通过。"})
                if doi and not valid_doi(doi):
                    raise ValidationError({"items": "计划项DOI格式无效。"})
                draft_edition = session.edition
                if not (edition_id or work_id):
                    draft_edition.isbn = isbn
                    draft_edition.doi = doi
                    draft_edition.version_label = row["version_note"][:120]
                    draft_edition.responsibility_statement = row["authors"]
                    draft_edition.save(update_fields=["isbn", "doi", "version_label", "responsibility_statement", "updated_at"])
                record.cataloging_session = session
                record.planned_work_id = session.work_id
                record.save(update_fields=["cataloging_session", "planned_work", "updated_at"])
            row.update(work_id=str(record.planned_work_id), edition_id=str(record.cataloging_session.edition_id),
                       cataloging_session_id=str(record.cataloging_session_id))
        payload["items"].append(row)
    _save_revision("recommendation_issue", issue.pk, payload, actor)
    issue.title = payload["title"]
    issue.save(update_fields=["title", "updated_at"])
    return issue


@transaction.atomic
def publish_issue(identifier, expected, actor):
    issue = RecommendationIssue.objects.select_for_update().get(pk=identifier)
    _check_version("recommendation_issue", issue.pk, expected)
    revision = _latest("recommendation_issue", issue.pk)
    if not revision or revision.status != "draft":
        raise ValidationError("没有待发布草稿。")
    payload = revision.materialized_preview
    if not payload.get("items"):
        raise ValidationError("本期至少需要一项阅读推荐。")
    for item in payload["items"]:
        if item["kind"] == "catalog" and not public_editions().filter(pk=item["edition_id"], work_id=item["work_id"]).exists():
            raise ValidationError("推荐馆藏已撤回或尚未公开，请重新核对。")
    _publish_revision(revision, actor)
    due = parse_datetime(payload["display_from"]) if payload.get("display_from") else revision.published_at
    if due > timezone.now():
        if issue.scheduled_revision_id and issue.scheduled_for and issue.scheduled_for <= timezone.now():
            issue.active_revision = issue.scheduled_revision
            issue.display_from = issue.scheduled_for
        issue.scheduled_revision = revision
        issue.scheduled_for = due
    else:
        issue.active_revision = revision
        issue.display_from = due
        issue.scheduled_revision = None
        issue.scheduled_for = None
    issue.published_at = revision.published_at
    issue.save(update_fields=["active_revision", "scheduled_revision", "scheduled_for", "published_at", "display_from", "updated_at"])
    return issue


def published_issues():
    now = timezone.now()
    return RecommendationIssue.objects.filter(Q(active_revision__status="published", display_from__lte=now) |
        Q(scheduled_revision__status="published", scheduled_for__lte=now)).select_related("active_revision", "scheduled_revision").annotate(
            effective_display_from=Case(When(scheduled_revision__status="published", scheduled_for__lte=now, then=F("scheduled_for")),
                                        default=F("display_from"), output_field=DateTimeField()))


def public_issue_revision(issue):
    if issue.scheduled_revision_id and issue.scheduled_for and issue.scheduled_for <= timezone.now():
        return issue.scheduled_revision
    return issue.active_revision


def issue_payload(issue, *, public=False, include_cover_storage=False, revision=None):
    revision = public_issue_revision(issue) if public else revision
    payload = deepcopy(revision.materialized_preview) if revision else issue_draft_payload(issue)
    published_at = revision.published_at if revision else issue.published_at
    payload.update(id=str(issue.pk), slug=issue.slug, published_at=published_at.isoformat() if published_at else None)
    if payload.get("cover_rendition_id"):
        rid = payload["cover_rendition_id"]
        payload["cover_url"] = f"/api/catalog/editorial-media/{rid}/" if public else f"/api/catalog/admin/media/renditions/{rid}/file/"
    records = {str(row.pk): row for row in issue.items.select_related("cataloging_session")}
    edition_ids = {row.get("edition_id") for row in payload.get("items", []) if row.get("edition_id")}
    edition_ids.update(str(row.linked_edition_id) for row in records.values() if row.linked_edition_id)
    editions = {str(row.pk): row for row in public_editions().filter(pk__in=edition_ids)}
    for row in payload.get("items", []):
        record = records.get(row["id"])
        edition_id = row.get("edition_id")
        if row["kind"] == "planned" and record and record.linked_edition_id:
            edition_id = str(record.linked_edition_id)
        edition = editions.get(str(edition_id)) if edition_id else None
        reader = edition.active_catalog_revision.reader_asset if edition else None
        from catalog.services.semantic_search import viewer_access_statuses
        readable = bool(reader and reader.edition_id == edition.pk and reader.kind == "normalized"
            and reader.status == "ready" and reader.validation_status == "valid"
            and reader.access_status in viewer_access_statuses())
        row["status"] = "available" if readable else "bibliographic" if edition else "planned" if row["kind"] == "planned" else "unavailable"
        row["file_status"] = reader.access_status if reader else "no_file"
        row["work_url"] = f"/works/{edition.public_slug}" if edition and edition.public_slug else ""
        row["reader_url"] = f"/reader/{reader.pk}" if readable else ""
        if edition:
            row["available_work_id"] = str(edition.work_id)
            row["available_edition_id"] = str(edition.pk)
            if row["kind"] == "planned":
                snapshot = edition.active_catalog_revision.snapshot or {}
                work_snapshot = snapshot.get("work", {})
                row["cover_rendition_id"] = (work_snapshot.get("cover_media") or {}).get("primary_rendition_id")
                row["cover_path"] = work_snapshot.get("cover", "")
            if row.get("cover_rendition_id") or row.get("cover_path"):
                row["cover_url"] = (f"/api/catalog/recommendation-issues/{issue.slug}/items/{row['id']}/cover/" if public
                                    else f"/api/catalog/admin/recommendation-issues/{issue.pk}/items/{row['id']}/cover/")
        row.setdefault("cover_url", "")
        if public:
            row.pop("cataloging_session_id", None)
            if edition:
                row.update(work_id=str(edition.work_id), edition_id=str(edition.pk))
            else:
                row.pop("work_id", None)
                row.pop("edition_id", None)
        elif record and record.cataloging_session_id:
            row["cataloging_session_id"] = str(record.cataloging_session_id)
            row["workbench_url"] = f"/admin/cataloging/{record.cataloging_session_id}"
            row["linked_edition_id"] = str(record.linked_edition_id) if record.linked_edition_id else None
            identifiers = Q(pk__in=[])
            if row.get("isbn"):
                from catalog.contracts.identifiers import normalize_isbn
                isbn = normalize_isbn(row["isbn"])
                identifiers |= Q(isbn=isbn) | Q(isbn10=isbn) | Q(isbn13=isbn)
            if row.get("doi"):
                from catalog.contracts.identifiers import normalize_doi
                identifiers |= Q(doi=normalize_doi(row["doi"]))
            row["match_candidates"] = [{"work_id": str(match.work_id), "edition_id": str(match.pk),
                "title": str((match.active_catalog_revision.snapshot or {}).get("work", {}).get("title") or ""),
                "version_label": match.version_label, "publication_year": match.publication_year,
                "match_basis": "identifier", "requires_version_confirmation": True}
                for match in public_editions().filter(identifiers).order_by("-updated_at")[:5]]
        if not include_cover_storage:
            row.pop("cover_path", None)
    if not public:
        latest = _latest("recommendation_issue", issue.pk)
        payload.update(edit_version=edit_version("recommendation_issue", issue.pk),
            draft_revision_id=str(latest.pk) if latest and latest.status == "draft" else None,
            has_unpublished_changes=bool(latest and latest.status == "draft"))
    return payload


@transaction.atomic
def link_planned_item(issue_id, item_id, data, actor):
    issue = RecommendationIssue.objects.select_for_update().get(pk=issue_id)
    _check_version("recommendation_issue", issue.pk, data.get("edit_version"))
    item = RecommendationIssueItem.objects.select_for_update().get(pk=item_id, issue=issue)
    if not item.cataloging_session_id:
        raise ValidationError("此项不是计划阅读物。")
    edition = public_editions().filter(pk=data.get("edition_id"), work_id=data.get("work_id")).first()
    if not edition or data.get("confirm_version") is not True:
        raise ValidationError("请明确确认作品和出版版本，再关联已公开馆藏。")
    item.linked_work_id, item.linked_edition_id = edition.work_id, edition.pk
    item.linked_by, item.linked_at = actor, timezone.now()
    item.save(update_fields=["linked_work", "linked_edition", "linked_by", "linked_at", "updated_at"])
    AuditEvent.objects.create(actor=actor, action="recommendation_issue.link_planned", object_type="RecommendationIssueItem", object_id=str(item.pk),
                              after={"work_id": str(edition.work_id), "edition_id": str(edition.pk), "version_confirmed": True})
    return issue


def site_public_payload():
    from catalog.views import current_site_config
    from catalog.serializers import AboutPageBlockSerializer
    return {"config": deepcopy(current_site_config()), "about_blocks": list(AboutPageBlockSerializer(AboutPageBlock.objects.all().order_by("sort_order", "created_at"), many=True).data)}


def site_target(*, lock=False):
    # Called only by authorized editing requests, never by anonymous reads.
    setting, _ = SiteSetting.objects.get_or_create(key="site_config", defaults={"value": {}, "public": True})
    return SiteSetting.objects.select_for_update().get(pk=setting.pk) if lock else setting


def site_payload():
    setting = site_target()
    latest = _latest("site_content", setting.pk)
    payload = deepcopy(latest.materialized_preview) if latest and latest.status == "draft" else site_public_payload()
    rid = payload["config"].get("home_hero_rendition_id")
    if rid:
        payload["config"]["home_hero_image"] = f"/api/catalog/admin/media/renditions/{rid}/file/"
    return {**payload, "edit_version": edit_version("site_content", setting.pk), "has_unpublished_changes": bool(latest and latest.status == "draft")}


@transaction.atomic
def save_site(data, actor):
    from catalog.serializers import SiteConfigSerializer, AboutPageBlockSerializer
    setting = site_target(lock=True)
    _check_version("site_content", setting.pk, data.get("edit_version"))
    config = SiteConfigSerializer(data=data.get("config", {}))
    config.is_valid(raise_exception=True)
    clean_config = dict(config.validated_data)
    rendition = _rendition(clean_config.get("home_hero_rendition_id"))
    clean_config["home_hero_rendition_id"] = str(rendition.pk) if rendition else None
    clean_config["home_hero_image"] = "" if rendition else safe_image_url(clean_config.get("home_hero_image"))
    blocks = data.get("about_blocks", [])
    if not isinstance(blocks, list) or len(blocks) > 100:
        raise ValidationError({"about_blocks": "网站内容最多100项。"})
    clean_blocks, seen = [], set()
    for block in blocks:
        instance = AboutPageBlock.objects.filter(key=block.get("key")).first() if isinstance(block, dict) else None
        serializer = AboutPageBlockSerializer(instance, data=block)
        serializer.is_valid(raise_exception=True)
        clean = dict(serializer.validated_data)
        clean.pop("updated_by", None)
        if clean["key"] in seen:
            raise ValidationError({"about_blocks": "不能重复网站模块。"})
        seen.add(clean["key"])
        link = str(clean.get("action_href") or "")
        if link and (urlsplit(link).scheme not in {"", "http", "https", "mailto"} or link.startswith("//") or "\\" in link):
            raise ValidationError({"about_blocks": "模块链接无效。"})
        clean_blocks.append(clean)
    _save_revision("site_content", setting.pk, {"config": clean_config, "about_blocks": clean_blocks}, actor)
    return site_payload()


@transaction.atomic
def publish_site(expected, actor):
    setting = site_target(lock=True)
    _check_version("site_content", setting.pk, expected)
    revision = _latest("site_content", setting.pk)
    if not revision or revision.status != "draft":
        raise ValidationError("没有待发布的网站草稿。")
    payload = revision.materialized_preview
    config = deepcopy(payload["config"])
    if config.get("home_hero_rendition_id"):
        config["home_hero_image"] = f"/api/catalog/editorial-media/{config['home_hero_rendition_id']}/"
    setting.value, setting.public, setting.updated_by = config, True, actor
    setting.save(update_fields=["value", "public", "updated_by", "updated_at"])
    keys = []
    for block in payload["about_blocks"]:
        values = dict(block)
        key = values.pop("key")
        keys.append(key)
        AboutPageBlock.objects.update_or_create(key=key, defaults={**values, "updated_by": actor})
    # Removed blocks are retained for history and are simply no longer shown.
    AboutPageBlock.objects.exclude(key__in=keys).update(visible=False)
    _publish_revision(revision, actor)
    return site_payload()
