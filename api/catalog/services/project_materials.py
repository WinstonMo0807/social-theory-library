"""Project-wide attached materials from current issue revisions, never a new library."""
from collections import defaultdict
from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID

from django.core.paginator import Paginator
from django.db.models import OuterRef, Subquery
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from catalog.models import EditorialRevision, RecommendationIssueItem
from catalog.services import editorial_issues as ledger
from catalog.services.publication_eligibility import public_editions, current_retrieval_source_q


def valid_id(value):
    try: return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError): return None


def current_articles(project):
    latest = EditorialRevision.objects.filter(target_type="recommendation_issue", target_id=OuterRef("pk")).order_by("-revision").values("pk")[:1]
    articles = list(project.articles.select_related("project").annotate(latest_id=Subquery(latest)).order_by("project_position", "created_at", "pk"))
    versions = EditorialRevision.objects.filter(pk__in=[row.latest_id for row in articles if row.latest_id])
    return articles, versions


def directory(project, params):
    articles, versions = current_articles(project)
    by_id = {str(row.pk): row for row in articles}
    order = {str(row.pk): index for index, row in enumerate(articles)}
    pointers = []
    # Stream original arrays without retaining every article body or long note.
    for row in versions.values("pk", "target_id", "materialized_preview__title", "materialized_preview__items").iterator(chunk_size=2):
        items = row["materialized_preview__items"] or []
        if not isinstance(items, list): raise ValidationError("文章材料的历史结构不完整，请在原文章中核对；本次没有修改记录。")
        for position, item in enumerate(items):
            if not isinstance(item, dict) or not valid_id(item.get("id")): raise ValidationError("文章材料缺少有效的原始身份，请在原文章中核对；本次没有修改记录。")
            pointers.append({"article_id": str(row["target_id"]), "article_title": row["materialized_preview__title"] or by_id[str(row["target_id"])].title,
                "revision_id": row["pk"], "position": position, "id": str(item.get("id", "")), "kind": item.get("kind", "catalog"),
                "title": str(item.get("title", "")), "authors": str(item.get("authors", "")), "edition_id": valid_id(item.get("edition_id"))})
    links = {str(row.pk): str(row.linked_edition_id) for row in RecommendationIssueItem.objects.filter(issue_id__in=by_id, linked_edition_id__isnull=False).only("pk", "linked_edition_id")}
    for row in pointers:
        if row["kind"] == "planned" and row["id"] in links: row["edition_id"] = links[row["id"]]
    ids = {row["edition_id"] for row in pointers if row["edition_id"]}
    public = public_editions().filter(pk__in=ids)
    eligible = set(map(str, public.values_list("pk", flat=True)))
    readable = set(map(str, public.filter(current_retrieval_source_q(asset_prefix="active_catalog_revision__reader_asset", access_statuses=("public", "inherit"))).values_list("pk", flat=True)))
    for row in pointers:
        row["status"] = "available" if row["edition_id"] in readable else "bibliographic" if row["edition_id"] in eligible else "planned" if row["kind"] == "planned" else "unavailable"
    totals = {"all": len(pointers), "missing": sum(row["status"] != "available" for row in pointers)}
    rows = pointers
    if params.get("scope") == "missing": rows = [row for row in rows if row["status"] != "available"]
    query = str(params.get("q", "")).strip()[:200].casefold()
    if query: rows = [row for row in rows if query in " ".join(str(row[key]) for key in ("title", "authors", "article_title")).casefold()]
    rows.sort(key=lambda row: (order[row["article_id"]], row["position"]))
    page = Paginator(rows, 30).get_page(params.get("page", 1))
    selected = defaultdict(set)
    for row in page.object_list: selected[row["revision_id"]].add(row["id"])
    materialized = {}
    for row in versions.filter(pk__in=selected).values("pk", "target_id", "published_at", "materialized_preview__title", "materialized_preview__items"):
        # Delegate current publication, file and planned-version resolution to the original article presenter.
        items = [deepcopy(item) for item in row["materialized_preview__items"] or [] if item.get("id") in selected[row["pk"]]]
        revision = SimpleNamespace(materialized_preview={"title": row["materialized_preview__title"], "items": items}, published_at=row["published_at"])
        issue = by_id[str(row["target_id"])]
        payload = ledger.issue_payload(issue, revision=revision, include_body=False)
        for item in payload["items"]: materialized[(str(issue.pk), item["id"])] = item
    results = [{**materialized[(row["article_id"], row["id"])], "article_id": row["article_id"], "article_title": row["article_title"]} for row in page.object_list]
    return {"results": results, "count": page.paginator.count, "page": page.number, "pages": page.paginator.num_pages, "page_size": 30,
            "totals": totals, "article_count": len(articles), "checked_at": timezone.now(),
            "scope_notice": "本项目全部文章当前保存的附录材料，按原文章顺序排列。待补按当前公开版本与原文可读状态核对；正文和选材来源可切换到对应清单。"}


def preview_directory(project):
    from django.db.models import Case, Max, When, F
    articles, versions = current_articles(project)
    latest = {str(row['target_id']): row for row in versions.values('pk', 'target_id', 'status', 'created_at',
        'materialized_preview__title', 'materialized_preview__introduction', 'materialized_preview__public_byline')}
    modified = {str(row['issue_id']): row['at'] for row in RecommendationIssueItem.objects.filter(issue__project=project).values('issue_id').annotate(at=Max('updated_at'))}
    due = dict(scheduled_revision__status='published', scheduled_for__lte=timezone.now())
    published = {str(row['pk']): row for row in ledger.published_issues().filter(project=project).annotate(
        public_title=Case(When(**due, then=F('scheduled_revision__materialized_preview__title')), default=F('active_revision__materialized_preview__title')),
        public_introduction=Case(When(**due, then=F('scheduled_revision__materialized_preview__introduction')), default=F('active_revision__materialized_preview__introduction')),
        public_byline=Case(When(**due, then=F('scheduled_revision__materialized_preview__public_byline')), default=F('active_revision__materialized_preview__public_byline')),
    ).values('pk', 'public_title', 'public_introduction', 'public_byline')}
    rows = []
    for article in articles:
        key = str(article.pk)
        revision, live = latest.get(key), published.get(key)
        raw = revision or {}
        at = modified.get(key)
        version = f"{revision['pk']}:{at.isoformat() if at else ''}" if revision else '0'
        rows.append({'id': key, 'title': raw.get('materialized_preview__title') or article.title,
            'introduction': raw.get('materialized_preview__introduction') or '', 'public_byline': raw.get('materialized_preview__public_byline') or '',
            'edit_version': version, 'saved_at': raw.get('created_at'), 'has_unpublished_changes': raw.get('status') == 'draft',
            'public_title': (live or {}).get('public_title') or '', 'public_introduction': (live or {}).get('public_introduction') or '',
            'published_byline': (live or {}).get('public_byline') or '', 'public_url': f'/recommendations/{article.slug}' if live else ''})
    return {'results': rows, 'count': len(rows), 'checked_at': timezone.now()}
