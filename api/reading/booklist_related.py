"""Owner-only booklist links over original plans, notes and published identities."""
from collections import Counter
from uuid import UUID

from rest_framework.exceptions import NotFound, ValidationError

from catalog.models import Topic
from catalog.services.public_scholars import scholar_follow_summary
from catalog.services.public_topics import topic_identity
from catalog.services.scoped_search import public_scholar_queryset
from . import booklists, notebook, reader_center, research

PAGE_SIZE = 20


def identifier(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def bounds(count, page):
    start = (page - 1) * PAGE_SIZE
    if page > 1 and start >= count:
        raise NotFound("这一页已没有关联内容，请返回第一页。")
    return start, start + PAGE_SIZE


def plan_rows(user):
    return reader_center.collection(user, "plans").order_by("-material_updated_at", "-id")


def plans(user, row, page):
    rows = plan_rows(user)
    # ponytail: encrypted origins require an owner-only scan, bounded like the
    # existing reader directory; an indexed source identity is needed above this limit.
    if rows.count() > reader_center.SEARCH_LIMIT:
        raise ValidationError("本人计划超过5000份，此关联视图无法完整核对。请到我的阅读计划查看，没有截断结果。")
    count, output, versions = 0, [], {}
    for plan in rows.iterator(chunk_size=100):
        origin = research.unpack(plan).get("origin") or {}
        if origin.get("type") != "booklist_copy" or origin.get("booklist_id") != str(row.pk):
            continue
        if (page - 1) * PAGE_SIZE <= count < page * PAGE_SIZE:
            value = reader_center.material(user, "plans", plan)
            output.append({key: value[key] for key in ("id", "title", "status", "href", "updated_at")})
            versions[str(plan.pk)] = reader_center.command_revision(plan, "plans")
        count += 1
    bounds(count, page)
    if versions != {str(plan.pk): reader_center.command_revision(plan, "plans") for plan in plan_rows(user).filter(pk__in=versions)}:
        raise research.ResearchConflict("关联计划在读取时发生变化，请重新读取。")
    return {"count": count, "plans": output,
        "notice": "这里只列出由本书单生成的本人计划，包括已归档计划。计划是独立副本，书单修改不会改写已有计划。"}


def source_counts(row):
    works = row.items.filter(removed_at__isnull=True).values("work_id")
    topics, people, versions = Counter(), Counter(), {}
    for pk, revision, topic_rows, contributions in booklists.public_editions().filter(work_id__in=works).values_list(
            "pk", "active_catalog_revision_id", "active_catalog_revision__snapshot__knowledge__topics",
            "active_catalog_revision__snapshot__contributions").iterator(chunk_size=100):
        versions[str(pk)] = str(revision)
        topic_ids, person_ids = set(), set()
        for value in topic_rows if isinstance(topic_rows, list) else []:
            key = identifier(value.get("id")) if isinstance(value, dict) else None
            if key:
                topic_ids.add(key)
        for value in contributions if isinstance(contributions, list) else []:
            if not isinstance(value, dict):
                continue
            person = value.get("person") if isinstance(value.get("person"), dict) else {}
            key = identifier(value.get("person_id") or person.get("id"))
            if key:
                person_ids.add(key)
        topics.update(topic_ids)
        people.update(person_ids)
    return topics, people, versions


def public_links(row, section, page):
    topics, people, versions = source_counts(row)
    if section == "topics":
        rows = [(str(pk), topics[str(pk)]) for pk in Topic.objects.filter(pk__in=topics, editorial_status="published").values_list("pk", flat=True)]
    else:
        rows = [(str(pk), people[str(person)]) for pk, person in public_scholar_queryset().filter(person_id__in=people).values_list("pk", "person_id")]
    rows.sort(key=lambda value: (-value[1], value[0]))
    start, stop = bounds(len(rows), page)
    output = []
    for pk, count in rows[start:stop]:
        current = topic_identity(pk) if section == "topics" else scholar_follow_summary(pk)
        if current is None:
            raise research.ResearchConflict("公开关联内容已变化，请重新读取。")
        output.append({"id": pk, "title": current["name"], "href": current.get("href") or f"/scholars/{current['slug']}",
            "description": current.get("description", ""), "source_count": count,
            "portrait_url": current.get("portrait_url"), "portrait_media": current.get("portrait_media")})
    current = booklists.public_editions().filter(work_id__in=row.items.filter(removed_at__isnull=True).values("work_id"))
    if versions != {str(pk): str(revision) for pk, revision in current.values_list("pk", "active_catalog_revision_id")}:
        raise research.ResearchConflict("书单公开版本在读取时已变化，请重新读取。")
    return {"count": len(rows), section: output,
        "notice": "关联来自本书单当前公开主版本的正式主题或署名，按关联作品数量排列；不推断影响关系。"}


def related(request, pk, query):
    row = booklists.owned(request.user, pk)
    if booklists.version(row) != query["expected_version"]:
        raise research.ResearchConflict("书单已变化，请重新读取当前书单。")
    section, page = query["section"], query["page"]
    if section == "plans":
        data = plans(request.user, row, page)
    elif section == "notes":
        notes = notebook.listing(request.user, {"page": page, "q": "", "kind": "all", "order": "newest", "booklist": row.pk})
        data = {"count": notes["count"], "notes": notes["results"],
            "notice": "这里只显示本人在书单当前作品下的笔记、摘录与书签。移除作品不删除记录；失效原文与本人保存的文字分开显示。"}
    else:
        data = public_links(row, section, page)
    if booklists.version(booklists.owned(request.user, pk)) != query["expected_version"]:
        raise research.ResearchConflict("书单在读取时已变化，请重新读取。")
    return {"owner_id": str(request.user.pk), "list_id": str(row.pk), "version": booklists.version(row),
        "section": section, "page": page, "total_pages": max(1, (data["count"] + PAGE_SIZE - 1) // PAGE_SIZE),
        "plans": [], "notes": [], "topics": [], "scholars": [], **data}
