"""Project access extends editorial identity without altering public revisions."""
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotFound, PermissionDenied

from catalog.models import CurationProject, RecommendationIssue
from common.capabilities import Capability, has_capability


def visible_projects(actor):
    if not has_capability(actor, Capability.ACCESS_BACK_OFFICE): return CurationProject.objects.none()
    return CurationProject.objects.filter(Q(visibility="staff") | Q(owner=actor) | Q(collaborators=actor)).distinct()


def visible_issues(actor, *, include_recycled=False):
    rows = RecommendationIssue.all_objects if include_recycled else RecommendationIssue.objects
    if not has_capability(actor, Capability.ACCESS_BACK_OFFICE): return rows.none()
    return rows.filter(Q(project__isnull=True) | Q(project_id__in=visible_projects(actor).values("pk")))


def require_issue_access(issue_id, actor, *, include_recycled=False):
    if not visible_issues(actor, include_recycled=include_recycled).filter(pk=issue_id).exists(): raise NotFound("此文章不存在或不在当前项目可见范围。")


def lock_issue(issue_id, actor, *, include_recycled=False, allow_archived=False):
    from django.contrib.auth import get_user_model
    current_actor = get_object_or_404(get_user_model().objects.select_for_update(), pk=actor.pk, is_active=True)
    if current_actor.token_version != actor.token_version or not has_capability(current_actor, Capability.EDIT_METADATA):
        raise PermissionDenied("当前会话不能修改文章，请重新核对编辑身份。")
    actor = current_actor
    rows = RecommendationIssue.all_objects if include_recycled else RecommendationIssue.objects
    issue = get_object_or_404(rows, pk=issue_id)
    if issue.project_id:
        project = get_object_or_404(CurationProject.objects.select_for_update(), pk=issue.project_id)
        require_issue_access(issue_id, actor, include_recycled=include_recycled)
        if project.archived_at and not allow_archived: raise PermissionDenied("项目已归档，请先恢复项目再编辑文章。")
    locked = get_object_or_404(rows.select_for_update(), pk=issue_id)
    if locked.project_id != issue.project_id:
        from catalog.services.editorial_issues import EditConflict
        raise EditConflict("文章所属项目已变化，请重新读取后操作。")
    require_issue_access(issue_id, actor, include_recycled=include_recycled)
    return locked


def protect_related_object(obj, actor, *, lock=False):
    label = obj._meta.label_lower
    issue_id = obj.pk if label == "catalog.recommendationissue" else obj.issue_id if label == "catalog.recommendationissueitem" else None
    if issue_id:
        if lock: lock_issue(issue_id, actor, include_recycled=True)
        else: require_issue_access(issue_id, actor, include_recycled=True)


def filter_related_objects(rows, actor):
    label = rows.model._meta.label_lower
    if label == "catalog.recommendationissue": return rows.filter(pk__in=visible_issues(actor, include_recycled=True).values("pk"))
    if label == "catalog.recommendationissueitem": return rows.filter(issue_id__in=visible_issues(actor, include_recycled=True).values("pk"))
    return rows


def project_version(project):
    import hashlib, json
    from catalog.models import EditorialRevision
    articles = list(project.articles.order_by("pk").values_list("pk", "project_position", "updated_at"))
    from django.db.models import Max, Count
    revisions = list(EditorialRevision.objects.filter(target_type="recommendation_issue", target_id__in=[row[0] for row in articles]).values("target_id", "status").annotate(updated=Max("updated_at"), count=Count("pk")).order_by("target_id", "status"))
    value = [project.pk, project.updated_at, list(project.collaborators.order_by("pk").values_list("pk", flat=True)), articles, revisions]
    return hashlib.sha256(json.dumps(value, default=str).encode()).hexdigest()


def person_label(user):
    return {"id": str(user.pk), "name": user.display_name or f"编辑账户 {user.pk}"}


def project_card(project, actor):
    from catalog.services.editorial_issues import published_issues
    return {"id": str(project.pk), "title": project.title, "question": project.question, "introduction": project.introduction,
            "owner": person_label(project.owner), "collaborators": [person_label(user) for user in project.collaborators.all()],
            "visibility": project.visibility, "cover_rendition_id": str(project.cover_rendition_id) if project.cover_rendition_id else None,
            "cover_url": f"/api/catalog/admin/media/renditions/{project.cover_rendition_id}/file/" if project.cover_rendition_id else "",
            "planned_for": project.planned_for, "archived_at": project.archived_at, "updated_at": project.updated_at,
            "article_count": project.articles.count(), "published_count": published_issues().filter(project=project).count(),
            "can_manage": project.owner_id == actor.pk and has_capability(actor, Capability.EDIT_METADATA),
            "can_edit": not project.archived_at and has_capability(actor, Capability.EDIT_METADATA)}


def project_detail(project, actor, page=1):
    from django.core.paginator import Paginator
    from catalog.services import editorial_issues as ledger
    from ingestion.models import AuditEvent
    articles = project.articles.select_related("active_revision", "created_by").order_by("project_position", "created_at", "pk")
    paging = Paginator(articles, 12).get_page(page)
    public_ids = set(ledger.published_issues().filter(project=project).values_list("pk", flat=True))
    cards, materials, problems = [], [], []
    for article in paging.object_list:
        payload = ledger.issue_payload(article)
        cards.append({key: payload.get(key) for key in ("id", "title", "introduction", "public_byline", "cover_url", "saved_at", "saved_by", "has_unpublished_changes", "edit_version")})
        cards[-1].update(published=article.pk in public_ids, edit_url=f"/admin/recommendations/issues/{article.pk}", position=article.project_position, source_problem_count=len(payload.get("body_source_problems", [])), public_url=f"/recommendations/{article.slug}" if article.pk in public_ids else "")
        for item in payload.get("items", []): materials.append({**item, "article_id": str(article.pk), "article_title": payload["title"]})
        for problem in payload.get("body_source_problems", []): problems.append({"article_id": str(article.pk), "article_title": payload["title"], **problem})
    from django.db.models.functions import Cast
    from django.db.models import CharField
    # UUID text storage differs across SQLite and PostgreSQL; normalize both sides.
    from django.db.models.functions import Replace
    from django.db.models import Value
    article_keys = articles.annotate(log_key=Replace(Cast("pk", output_field=CharField()), Value("-"), Value(""))).values("log_key")
    events = AuditEvent.objects.annotate(target_key=Replace("object_id", Value("-"), Value(""))).filter(
        Q(action="curation.project.command", object_id=str(project.pk)) |
        Q(action__in=["recommendation_issue.save_draft", "recommendation_issue.publish"], target_key__in=article_keys))
    logs = [{"id": str(row.pk), "at": row.created_at, "action": row.after.get("operation") or row.action, "actor": person_label(row.actor)["name"] if row.actor else "编辑账户"}
            for row in events.select_related("actor").order_by("-created_at", "pk")[:20]]
    return {**project_card(project, actor), "version": project_version(project), "articles": cards,
            "articles_page": paging.number, "articles_pages": paging.paginator.num_pages,
            "article_ids": list(map(str, articles.values_list("pk", flat=True))), "materials": materials, "problems": problems, "activity": logs,
            "material_scope": "当前文章分页的已保存引用与来源问题；完整发布检查在各文章中进行。"}
