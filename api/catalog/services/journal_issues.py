"""Canonical issue contents and read-only published link materialization."""

from catalog.models import DocumentType, JournalIssueArticle, Work


def journal_contents_snapshot(edition):
    return [
        {"id": str(row.pk), "article_work_id": str(row.article_work_id) if row.article_work_id else None,
         "title": row.title, "author_display": row.author_display, "page_range": row.page_range, "position": row.position}
        for row in edition.journal_articles.order_by("position", "created_at", "id")
    ]


def normalize_journal_contents(edition, rows, *, document_type=None):
    if (document_type or edition.work.document_type) != DocumentType.JOURNAL_ISSUE:
        if rows:
            raise ValueError("只有整期期刊可以编辑本期目录。")
        return []
    if not isinstance(rows, list) or len(rows) > 500 or any(not isinstance(row, dict) for row in rows):
        raise ValueError("本期目录必须是最多500项的列表。")
    existing = {str(pk) for pk in edition.journal_articles.values_list("pk", flat=True)}
    article_ids = [str(row.get("article_work_id")) for row in rows if row.get("article_work_id")]
    if len(article_ids) != len(set(article_ids)):
        raise ValueError("同一期目录不能重复关联同一篇论文。")
    articles = {str(row.pk): row for row in Work.objects.filter(pk__in=article_ids, document_type=DocumentType.JOURNAL_ARTICLE)}
    if set(article_ids) != set(articles):
        raise ValueError("目录只能关联馆内已有的期刊论文。")
    output, seen = [], set()
    for position, row in enumerate(rows):
        identifier = str(row.get("id") or "")
        if identifier and (identifier not in existing or identifier in seen):
            raise ValueError("目录条目已变化，请刷新后重试。")
        seen.add(identifier)
        article_id = str(row.get("article_work_id") or "")
        title = str(row.get("title") or "").strip()
        if not title:
            raise ValueError("每项目录都需要论文题名。")
        output.append({"id": identifier or None, "article_work_id": article_id or None, "title": title,
                       "author_display": str(row.get("author_display") or ""), "page_range": str(row.get("page_range") or ""), "position": position})
    return output


def sync_journal_contents(edition, rows):
    rows = normalize_journal_contents(edition, rows)
    existing = {str(row.pk): row for row in edition.journal_articles.select_for_update()}
    kept = {row["id"] for row in rows if row["id"]}
    edition.journal_articles.exclude(pk__in=kept).delete()
    # Release optional associations before reordering/reassigning entries;
    # all calls run in the existing workflow publication transaction.
    edition.journal_articles.update(article_work=None)
    for row in rows:
        entry = existing.get(row["id"]) or JournalIssueArticle(issue=edition)
        for field_name in ("article_work_id", "title", "author_display", "page_range", "position"):
            setattr(entry, field_name, row[field_name])
        entry.save()


def public_journal_contents(rows):
    """A draft or withdrawn article can be listed but never receives a public link."""
    from catalog.services.publication_eligibility import public_editions

    rows = list(rows or [])
    links = {}
    for edition in public_editions().filter(work_id__in=[row.get("article_work_id") for row in rows if row.get("article_work_id")]).order_by("work_id", "-is_primary", "-published_at"):
        links.setdefault(str(edition.work_id), f"/works/{edition.public_slug}" if edition.public_slug else "")
    return [{**row, "article_href": links.get(str(row.get("article_work_id")), "")} for row in rows]
