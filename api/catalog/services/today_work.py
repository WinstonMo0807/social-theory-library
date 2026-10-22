"""Today's work is a read model of existing drafts, intake and processing.

SQL owns filtering, counts and pagination. Only the selected page is projected;
opening this page never schedules a job, publishes content or probes services.
"""
import re
from uuid import UUID

from django.core.paginator import Paginator
from django.db.models import Case, CharField, Exists, F, OuterRef, Q, Subquery, TextField, Value, When
from django.db.models.functions import Cast, Coalesce, Concat
from django.db.models.fields.json import KeyTextTransform
from django.utils import timezone

from catalog import models
from catalog.curation_queue_views import draft_querysets
from catalog.services.admin_queue_query import inventory
from catalog.services.cataloging_sessions import OPEN_STATUSES
from common.capabilities import Capability, has_capability
from ingestion.models import ProcessingJob


FIELDS = ("t_id", "t_object_id", "t_type", "t_title", "t_label", "t_updated", "t_url", "t_state", "t_bucket", "t_kind")
CATEGORIES = {"all": "全部", "editing": "最近编辑", "intake": "待继续收件", "catalog": "待校准目录", "problems": "待处理问题", "publication": "待发布核对"}
KINDS = {"": "全部任务类型", "catalog": "书目处理", "curation": "策划与知识", "processing": "数字化处理"}
STATES = {"": "全部状态", "draft": "已保存 · 未发布", "changes_pending": "已发布 · 有草稿", "pending": "等待处理", "running": "处理中", "paused": "已暂停", "partial": "部分完成", "attention": "待核对", "failed": "处理失败", "ready": "待发布核对", "published": "已发布", "withdrawn": "已撤回", "succeeded": "已完成", "completed": "已完成", "canceled": "已取消", "approved": "已确认", "suggested": "待确认", "rejected": "已否决", "archived": "已归档"}
COMPACT_UUID = re.compile(r"\b[0-9a-fA-F]{32}\b")


def _newer(queryset):
    return queryset.filter(Q(created_at__gt=OuterRef("created_at")) | Q(created_at=OuterRef("created_at"), pk__gt=OuterRef("pk")))


def current_processing_jobs():
    # Nullable identities must compare as a tuple, including global jobs. A
    # successful replacement removes the old failure from this work queue.
    jobs = ProcessingJob.objects.annotate(t_identity=Concat(
        Coalesce(Cast("edition_id", CharField()), Value("")), Value(":"),
        Coalesce(Cast("asset_id", CharField()), Value("")), Value(":"),
        Coalesce(Cast("upload_item_id", CharField()), Value("")), Value(":"),
        Case(When(edition__isnull=True, asset__isnull=True, upload_item__isnull=True, then=Cast("pk", CharField())), default=Value(""), output_field=CharField()), output_field=CharField(),
    ))
    newer = _newer(jobs.filter(t_identity=OuterRef("t_identity"), job_type=OuterRef("job_type")))
    return jobs.annotate(t_newer=Exists(newer)).filter(Q(t_newer=False) | ~Q(status="failed"), status__in=("pending", "running", "paused", "failed")).filter(
        Q(asset__isnull=True) | Q(asset__is_current=True),
    ).exclude(upload_item__status="deleted")


def _search(queryset, query, title, extra=(), condition=None):
    if not query:
        return queryset
    condition = (condition or Q()) | Q(**{f"{title}__icontains": query})
    for key in extra:
        condition |= Q(**{f"{key}__icontains": query})
    try:
        identifier = UUID(query)
    except ValueError:
        pass
    else:
        condition |= Q(pk=identifier)
    return queryset.filter(condition)


def work_querysets(user, *, query="", owner="all", kind="", state="", search_all=False):
    can_catalog = has_capability(user, Capability.EDIT_METADATA)
    can_processing = has_capability(user, Capability.VIEW_SYSTEM_STATUS)
    mine = user.pk if owner == "me" else None
    rows = []
    if can_catalog:
        editions, uploads = inventory(publication_scope=search_all)
        if mine is not None:
            sessions = models.CatalogingSession.objects.filter(edition_id=OuterRef("pk"), created_by_id=mine)
            drafts = models.EditorialRevision.objects.filter(created_by_id=mine).filter(
                Q(target_type="edition", target_id=OuterRef("pk")) | Q(target_type="work", target_id=OuterRef("work_id")))
            editions = editions.annotate(t_my_session=Exists(sessions), t_my_draft=Exists(drafts)).filter(
                Q(t_my_session=True) | Q(t_my_draft=True) | Q(uploaditem__batch__created_by_id=mine)).distinct()
            uploads = uploads.filter(batch__created_by_id=mine)
        from ingestion.services.processing_identity import draft_title_work_ids
        changed_titles = draft_title_work_ids(query) if query else models.Work.objects.none().values("pk")
        editions = _search(editions, query, "work__title", ("work__original_title", "uploaditem__source_filename", "contributions__person__preferred_name"), Q(work_id__in=changed_titles)).distinct()
        uploads = _search(uploads, query, "source_filename")
        open_sessions = models.CatalogingSession.objects.filter(edition_id=OuterRef("pk"), status__in=OPEN_STATUSES).order_by("-updated_at", "pk")
        from ingestion.models import UploadItem
        intake = UploadItem.objects.filter(edition_id=OuterRef("pk")).exclude(status__in=("published", "withdrawn", "deleted")).order_by("-updated_at", "pk")
        rows.append(editions.order_by().annotate(t_session=Subquery(open_sessions.values("pk")[:1]), t_intake=Subquery(intake.values("pk")[:1])).annotate(
            t_id=Concat(Value("edition:"), Cast("pk", CharField())), t_object_id=Cast("pk", CharField()),
            t_type=Value("edition"), t_title=Cast("work__title", TextField()), t_label=Value("书目处理"),
            t_updated=F("q_updated"), t_url=Case(
                When(t_session__isnull=False, then=Concat(Value("/admin/cataloging/"), Cast("t_session", CharField()))),
                When(t_intake__isnull=False, then=Concat(Value("/admin/intake/"), Cast("t_intake", CharField()))),
                default=Concat(Value("/admin/library/works/"), Cast("work_id", CharField()), Value("?edition="), Cast("pk", CharField())), output_field=CharField()),
            t_state=Case(*([When(state="withdrawn", then=Value("withdrawn")), When(q_active=True, q_draft=True, then=Value("changes_pending")), When(q_active=True, then=Value("published"))] if search_all else []), When(q_exception=True, then=Value("failed")), When(q_ready=True, then=Value("ready")), When(q_preparing=True, then=Value("running")), default=Value("attention"), output_field=CharField()),
            t_bucket=Case(When(q_exception=True, then=Value("problems")), When(q_ready=True, then=Value("publication")), When(q_pending_upload=True, then=Value("intake")), default=Value("catalog"), output_field=CharField()),
            t_kind=Value("catalog"),
        ).values(*FIELDS))
        rows.append(uploads.order_by().annotate(
            t_id=Concat(Value("upload:"), Cast("pk", CharField())), t_object_id=Cast("pk", CharField()),
            t_type=Value("upload"), t_title=Cast("source_filename", TextField()), t_label=Value("收件"), t_updated=F("updated_at"),
            t_url=Concat(Value("/admin/uploads?item="), Cast("pk", CharField())),
            t_state=Case(When(status="failed", then=Value("failed")), default=Value("pending"), output_field=CharField()),
            t_bucket=Case(When(status="failed", then=Value("problems")), default=Value("intake"), output_field=CharField()), t_kind=Value("catalog"),
        ).values(*FIELDS))
    for drafts in draft_querysets(user, owner_id=mine, pending_only=not search_all):
        if query:
            drafts = drafts.filter(Q(q_title__icontains=query) | Q(q_object_id__icontains=query.replace("-", "")) | Q(q_object_id__icontains=query))
        rows.append(drafts.annotate(
            t_id=F("q_id"), t_object_id=F("q_object_id"), t_type=F("q_type"), t_title=F("q_title"), t_label=F("q_label"),
            t_updated=F("q_updated"), t_url=F("q_url"), t_state=F("q_state"), t_bucket=Value("editing"), t_kind=Value("curation"),
        ).values(*FIELDS))
    if can_processing:
        jobs = ProcessingJob.objects.all() if search_all else current_processing_jobs()
        semantic = models.SemanticIndexJob.objects.all()
        if not search_all:
            semantic = semantic.filter(Q(asset__is_current=True) | Q(asset__isnull=True), status__in=("queued", "running", "partial", "failed", "paused"))
            newer_semantic = _newer(models.SemanticIndexJob.objects.filter(asset_id=OuterRef("asset_id"), operation=OuterRef("operation")))
            semantic = semantic.annotate(t_newer=Exists(newer_semantic)).filter(Q(t_newer=False) | Q(status__in=("queued", "running", "paused")))
        if mine is not None:
            jobs = jobs.filter(created_by_id=mine)
            semantic = semantic.filter(requested_by_id=mine)
        from ingestion.services.processing_identity import draft_title_work_ids
        changed_titles = draft_title_work_ids(query) if query else models.Work.objects.none().values("pk")
        jobs = _search(jobs, query, "edition__work__title", ("asset__edition__work__title", "upload_item__source_filename", "job_type", "task_id"), Q(edition__work_id__in=changed_titles) | Q(asset__edition__work_id__in=changed_titles) | Q(upload_item__edition__work_id__in=changed_titles))
        semantic = _search(semantic, query, "asset__edition__work__title", ("asset__original_filename", "task_id"), Q(asset__edition__work_id__in=changed_titles))
        for queryset, ordinary in ((jobs, True), (semantic, False)):
            source = "processing_job" if ordinary else "semantic_index_job"
            rows.append(queryset.order_by().annotate(
                t_id=Concat(Value(source + ":"), Cast("pk", CharField())), t_object_id=Cast("pk", CharField()),
                t_type=Value(source), t_title=Coalesce("edition__work__title", "asset__edition__work__title", "upload_item__source_filename", Value("系统处理任务"), output_field=TextField()) if ordinary else Coalesce(Cast("asset__edition__work__title", TextField()), Value("索引维护任务"), output_field=TextField()),
                t_label=Case(*[When(job_type=value, then=Value(label)) for value, label in ProcessingJob.JobType.choices], default=Value("数字化处理"), output_field=CharField()) if ordinary else Value("语义索引"),
                t_updated=F("updated_at"), t_url=Concat(Value(f"/admin/processing?surface=workers&task_source={source}&task_id="), Cast("pk", CharField())),
                t_state=F("status") if ordinary else Case(When(status="queued", then=Value("pending")), default=F("status"), output_field=CharField()),
                t_bucket=Value("problems"), t_kind=Value("processing"),
            ).values(*FIELDS))
    if kind:
        rows = [row.filter(t_kind=kind) for row in rows]
    if state:
        rows = [row.filter(t_state=state) for row in rows]
    return rows


def _union(rows):
    return rows[0].union(*rows[1:], all=True)


def today_work_page(user, options, *, search_all=False):
    rows = work_querysets(user, query=options["q"], owner=options["owner"], kind="" if search_all else options["kind"], state=options["state"], search_all=search_all)
    if search_all and not options["q"]:
        rows = [row.none() for row in rows]
    counts = {key: _union([row.filter(**{("t_kind" if search_all else "t_bucket"): key}) for row in rows]).count() for key in (KINDS if search_all else CATEGORIES) if key not in ("all", "")}
    counts["all"] = sum(counts.values())
    if search_all and options["kind"]:
        rows = [row.filter(t_kind=options["kind"]) for row in rows]
    if not search_all and options["category"] != "all":
        rows = [row.filter(t_bucket=options["category"]) for row in rows]
    paginator = Paginator(_union(rows).order_by("-t_updated" if options["ordering"].startswith("-") else "t_updated", "t_id"), 20)
    page = paginator.get_page(options["page"])
    results = _project_rows(page.object_list, search_all=search_all)
    return {"results": results, "count": paginator.count, "page": page.number, "page_size": paginator.per_page,
            "total_pages": paginator.num_pages, "counts": counts, "checked_at": timezone.now(),
            "restricted": not has_capability(user, Capability.VIEW_SYSTEM_STATUS),
            "owner_basis": "我的工作按发起或编辑记录筛选，未记录处理人的任务只在全部工作中显示。",
            "ordering": options["ordering"], "can_upload": has_capability(user, Capability.UPLOAD), "can_create_issue": has_capability(user, Capability.EDIT_METADATA)}


def work_notices(user):
    rows = [row.filter(t_state__in=("failed", "paused", "partial")) for row in work_querysets(user)]
    records = _union(rows).order_by("-t_updated", "t_id")
    return {"count": records.count(), "checked_at": timezone.now(), "results": _project_rows(records[:5])}


def _project_rows(records, *, search_all=False):
    results = []
    for row in records:
        value = dict(zip(("id", "object_id", "object_type", "title", "label", "updated_at", "url", "state", "category", "kind"), (row[key] for key in FIELDS)))
        for key in ("id", "object_id", "url"):
            value[key] = COMPACT_UUID.sub(lambda match: str(UUID(match.group())), value[key])
        value["state_label"] = STATES.get(value["state"], "状态待核对")
        value["action_label"] = "查看详情" if search_all else "继续编辑" if value["category"] == "editing" else "核对发布" if value["category"] == "publication" else "继续处理" if value["kind"] == "processing" else "查看详情"
        value["summary"] = {
            "editing": "继续已有编辑，保存与发布分别处理。", "intake": "核对来源文件与书目信息，继续收件。",
            "catalog": "核对书目资料、目录和关联信息。", "publication": "检查资料与预览，确认后再发布。",
            "problems": "查看当前处理记录及原因，再决定下一步。",
        }[value["category"]]
        if search_all:
            value["summary"] = "打开对应资料与记录；保存和公开状态以工作页为准。"
        value["thumbnail_url"] = ""
        results.append(value)
    _thumbnails(results)
    return results


def _thumbnails(rows):
    """Reuse protected media renditions; missing images remain an honest blank."""
    ids = {kind: [row["object_id"] for row in rows if row["object_type"] == kind] for kind in {row["object_type"] for row in rows}}
    images = {}
    legacy = {}
    editions = list(models.Edition.objects.filter(pk__in=ids.get("edition", [])).select_related("work"))
    for edition in editions:
        images[("edition", str(edition.pk))] = edition.work.cover_rendition_id
        if edition.work.cover:
            legacy[("edition", str(edition.pk))] = edition.work.cover.url
    for identifier, rendition in models.ScholarProfile.objects.filter(pk__in=ids.get("scholar_profile", [])).values_list("pk", "person__portrait_rendition_id"):
        images[("scholar_profile", str(identifier))] = rendition
    for kind, model in (("knowledge_node", models.KnowledgeNode), ("reading_path", models.ReadingPath)):
        for identifier, rendition in model.objects.filter(pk__in=ids.get(kind, [])).values_list("pk", "cover_rendition_id"):
            images[(kind, str(identifier))] = rendition
    issue_ids = ids.get("recommendation_issue", [])
    latest = models.EditorialRevision.objects.filter(target_type="recommendation_issue", target_id=OuterRef("pk")).order_by("-revision").annotate(image=KeyTextTransform("cover_rendition_id", "materialized_preview"))
    for identifier, image in models.RecommendationIssue.objects.filter(pk__in=issue_ids).annotate(image=Subquery(latest.values("image")[:1])).values_list("pk", "image"):
        key = ("recommendation_issue", str(identifier))
        try:
            images[key] = UUID(str(image or ""))
        except ValueError:
            images[key] = None
    from ingestion.services.processing_identity import edition_titles, task_titles, processing_identity
    jobs = list(ProcessingJob.objects.filter(pk__in=ids.get("processing_job", [])).select_related("edition__work", "asset__edition__work", "upload_item__edition__work"))
    jobs += list(models.SemanticIndexJob.objects.filter(pk__in=ids.get("semantic_index_job", [])).select_related("asset__edition__work"))
    catalog_titles = edition_titles(editions)
    edition_labels = {str(edition.pk): catalog_titles[str(edition.work_id)]["title"] for edition in editions}
    titles = task_titles(jobs)
    job_titles = {( "processing_job" if isinstance(job, ProcessingJob) else "semantic_index_job", str(job.pk)): processing_identity(job, titles)["title"] for job in jobs}
    for row in rows:
        key = (row["object_type"], row["object_id"])
        rendition = images.get(key)
        if row["object_type"] == "edition" and row["object_id"] in edition_labels:
            row["title"] = edition_labels[row["object_id"]]
        if key in job_titles:
            row["title"] = job_titles[key]
        if rendition:
            row["thumbnail_url"] = f"/api/catalog/admin/media/renditions/{rendition}/file/"
        elif key in legacy:
            row["thumbnail_url"] = legacy[key]
