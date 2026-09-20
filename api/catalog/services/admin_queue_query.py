"""Database inventory for the work queue; hydrate only a bounded page.

Queue categories describe saved operational records. Publication itself still
runs the full field/file/identity preflight in the existing domain command.
"""
from django.core.paginator import Paginator
from django.db.models import BooleanField, Case, CharField, Exists, F, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Cast, Coalesce, Concat, Greatest

from catalog.models import Asset, CatalogFieldDecision, CatalogingSession, CatalogPublicationRevision, Contribution, Edition, EditorialRevision, RecommendationIssueItem
from catalog.contracts.fields import FIELD_CONTRACTS, required_fields
from catalog.services.cataloging_sessions import OPEN_STATUSES
from ingestion.models import FieldLock, ProcessingJob, UploadItem

TERMINAL_UPLOAD = ("published", "withdrawn", "deleted")
CATEGORY_FIELDS = {"all": None, "continue": "actionable", "attention": "attention", "exception": "exception", "publication_ready": "ready"}
QUEUE_ORDERING = {"priority": ("-queue_priority", "queue_updated", "queue_id"),
                  "-updated_at": ("-queue_updated", "queue_id"), "updated_at": ("queue_updated", "queue_id")}


def _flag(condition):
    return Case(When(condition, then=Value(True)), default=Value(False), output_field=BooleanField())


def edition_inventory():
    sessions = CatalogingSession.objects.filter(edition_id=OuterRef("pk")).order_by("-updated_at", "id")
    uploads = UploadItem.objects.filter(edition_id=OuterRef("pk"))
    pending = uploads.exclude(status__in=TERMINAL_UPLOAD)
    newer_jobs = ProcessingJob.objects.annotate(q_job_source=Coalesce(Cast("asset_id", CharField()), Value(""))).filter(
        edition_id=OuterRef("edition_id"), job_type=OuterRef("job_type"), q_job_source=OuterRef("q_job_source")
    ).filter(Q(created_at__gt=OuterRef("created_at")) | Q(created_at=OuterRef("created_at"), pk__gt=OuterRef("pk")))
    jobs = ProcessingJob.objects.filter(edition_id=OuterRef("pk")).filter(Q(asset__isnull=True) | Q(asset__is_current=True)).annotate(
        q_job_source=Coalesce(Cast("asset_id", CharField()), Value("")), q_newer_job=Exists(newer_jobs)
    ).filter(q_newer_job=False)
    revisions = CatalogPublicationRevision.objects.filter(edition_id=OuterRef("pk"))
    drafts = EditorialRevision.objects.filter(status="draft").filter(
        Q(target_type="edition", target_id=OuterRef("pk")) | Q(target_type="work", target_id=OuterRef("work_id"))
    )
    assets = Asset.objects.filter(edition_id=OuterRef("pk"))
    decisions = CatalogFieldDecision.objects.filter(edition_id=OuterRef("pk"))
    active = Q(state="published", active_catalog_revision__edition_id=F("pk"), active_catalog_revision__status="active", active_catalog_revision__metadata_ready=True)
    queryset = Edition.objects.annotate(
        q_active=_flag(active), q_has_assets=Exists(assets), q_has_upload=Exists(uploads),
        q_pending_upload=Exists(pending), q_failed_upload=Exists(pending.filter(status="failed")),
        q_failed_job=Exists(jobs.filter(status="failed")),
        q_open_session=Exists(sessions.filter(status__in=OPEN_STATUSES)),
        q_draft=Exists(drafts),
        q_preparing=Exists(revisions.filter(status="preparing")),
        q_failed_publication=Exists(revisions.filter(status="failed").filter(Q(revision__gt=OuterRef("active_catalog_revision__revision")) | Q(edition__active_catalog_revision__isnull=True))),
        q_review_fields=Exists(decisions.filter(status__in=("needs_review", "stale", "conflict", "suggested"))),
        q_conflict=Exists(decisions.filter(status="conflict")),
        q_original_ready=Exists(assets.filter(kind="original", is_current=True, status="ready", validation_status="valid")),
        q_reader_ready=Exists(assets.filter(kind="normalized", is_current=True, status="ready", validation_status="valid")),
        q_source=Coalesce(Subquery(sessions.values("source_type")[:1]), Case(When(q_has_upload=True, then=Value("upload")), default=Value("existing"), output_field=CharField())),
        q_priority=Coalesce(Subquery(pending.order_by("-priority").values("priority")[:1]), Value(0)),
        q_updated=Greatest(F("updated_at"), F("work__updated_at"), Coalesce(Subquery(sessions.values("updated_at")[:1]), F("updated_at")), Coalesce(Subquery(drafts.order_by("-updated_at").values("updated_at")[:1]), F("updated_at")), Coalesce(Subquery(pending.order_by("-updated_at").values("updated_at")[:1]), F("updated_at"))),
    ).annotate(
        q_publication=Case(When(state="withdrawn", then=Value("withdrawn")), When(q_active=True, then=Value("published")), When(state="published", active_catalog_revision__isnull=True, q_preparing=True, then=Value("publishing")), default=Value("unpublished"), output_field=CharField()),
        q_file_problem=_flag((~Q(publication_mode="bibliographic") | Q(q_has_assets=True)) & (~Q(q_original_ready=True) | ~Q(q_reader_ready=True))),
    )
    # Required-field confirmation is queried from the existing decisions, not a
    # copied workflow status table. Missing author decisions can use approved
    # canonical contributions, exactly as the existing field reader does.
    contributors = Contribution.objects.filter(edition_id=OuterRef("pk"), role="author", approved=True)
    queryset = queryset.annotate(q_authors=Exists(contributors))
    incomplete = Q(q_conflict=True)
    for document_type in ("book", "journal_article", "journal_issue", "thesis", "report"):
        for field in required_fields(document_type, has_document=False):
            if field == "file":
                continue
            alias = f"q_confirmed_{field}"
            if alias not in queryset.query.annotations:
                queryset = queryset.annotate(**{
                    alias: Exists(decisions.filter(field_name=field, status__in=("confirmed", "stale"))),
                    f"q_decision_{field}": Exists(decisions.filter(field_name=field)),
                    f"q_locked_{field}": Exists(FieldLock.objects.filter(edition_id=OuterRef("pk"), field_name=field)),
                })
            condition = Q(work__document_type=document_type) & Q(**{alias: False})
            if field == "authors":
                condition &= Q(q_authors=False)
            else:
                column = f"work__{field}" if FIELD_CONTRACTS[field].domain_object == "work" else field
                present = Q(**{f"{column}__isnull": False})
                if FIELD_CONTRACTS[field].data_type not in {"integer", "date"}:
                    present &= ~Q(**{column: ""})
                formal = (~Q(**{f"q_decision_{field}": True}) & (Q(state="published") | Q(active_catalog_revision__isnull=False) | Q(**{f"q_locked_{field}": True})) & present)
                condition &= ~formal
                incomplete |= Q(work__document_type=document_type) & ~present
            incomplete |= condition
    queryset = queryset.annotate(q_incomplete=_flag(incomplete)).annotate(
        q_exception=_flag(Q(q_failed_upload=True) | Q(q_failed_job=True) | Q(q_failed_publication=True) | Q(intelligence_status="failed")),
        q_attention=_flag(Q(q_incomplete=True) | Q(q_file_problem=True) | Q(q_review_fields=True) | Q(q_open_session=True) | Q(q_draft=True) | Q(q_preparing=True) | Q(intelligence_status__in=("processing", "failed")) | Q(q_failed_job=True) | Q(q_failed_upload=True) | Q(q_failed_publication=True)),
    ).annotate(
        q_actionable=_flag(~Q(state="withdrawn") & (~Q(q_active=True) | Q(q_attention=True) | Q(q_pending_upload=True))),
        q_ready=_flag(~Q(state="withdrawn") & ~Q(q_incomplete=True) & ~Q(q_file_problem=True) & ~Q(q_exception=True) & ~Q(q_preparing=True) & (~Q(q_active=True) | Q(q_draft=True))),
    )
    return queryset


def inventory(*, source="", publication="", query="", publication_scope=False, exclude_edition=None, exclude_item=None):
    editions = edition_inventory()
    uploads = UploadItem.objects.filter(edition__isnull=True).exclude(status__in=TERMINAL_UPLOAD)
    if exclude_edition:
        editions = editions.exclude(pk=exclude_edition)
    if exclude_item:
        uploads = uploads.exclude(pk=exclude_item)
    if not publication_scope:
        editions = editions.filter(q_actionable=True)
    if source:
        editions = editions.filter(q_source=source)
        if source != "upload":
            uploads = uploads.none()
    if publication:
        editions = editions.filter(q_publication=publication)
        if publication != "unpublished":
            uploads = uploads.none()
    if query:
        editions = editions.filter(Q(work__title__icontains=query) | Q(work__original_title__icontains=query) | Q(uploaditem__source_filename__icontains=query)).distinct()
        uploads = uploads.filter(source_filename__icontains=query)
    return editions, uploads


def _keys(editions, uploads, category="all", ordering="priority"):
    field = CATEGORY_FIELDS[category]
    if field:
        editions = editions.filter(**{f"q_{field}": True})
    if category in ("attention", "exception"):
        uploads = uploads.filter(status="failed")
    if category == "publication_ready":
        uploads = uploads.none()
    left = editions.order_by().annotate(queue_id=Concat(Value("edition:"), Cast("id", CharField())), queue_priority=F("q_priority"), queue_updated=F("q_updated")).values("queue_id", "queue_priority", "queue_updated")
    right = uploads.order_by().annotate(queue_id=Concat(Value("upload:"), Cast("id", CharField())), queue_priority=F("priority"), queue_updated=F("updated_at")).values("queue_id", "queue_priority", "queue_updated")
    return left.union(right, all=True).order_by(*QUEUE_ORDERING[ordering])


def _hydrate(keys, *, user=None):
    from catalog.services.admin_queue import edition_summary, load_admin_editions, unbound_upload_row

    keys = list(keys)
    edition_ids = [row["queue_id"].split(":", 1)[1] for row in keys if row["queue_id"].startswith("edition:")]
    item_ids = [row["queue_id"].split(":", 1)[1] for row in keys if row["queue_id"].startswith("upload:")]
    by_id = {f"edition:{edition.pk}": edition_summary(edition, user=user) for edition in load_admin_editions(Edition.objects.filter(pk__in=edition_ids))}
    for item in RecommendationIssueItem.objects.filter(cataloging_session__edition_id__in=edition_ids).select_related("issue", "cataloging_session"):
        row = by_id.get(f"edition:{item.cataloging_session.edition_id}")
        if row is not None:
            row.setdefault("recommendation_sources", []).append({"id": str(item.issue_id), "title": item.issue.title, "url": f"/admin/recommendations/issues/{item.issue_id}"})
    by_id.update({f"upload:{item.pk}": unbound_upload_row(item) for item in UploadItem.objects.filter(pk__in=item_ids)})
    return [by_id[row["queue_id"]] for row in keys if row["queue_id"] in by_id]


def queue_page(*, user=None, category="all", page=1, ordering="priority", **filters):
    editions, uploads = inventory(**filters)
    keys = _keys(editions, uploads, category, ordering)
    paginator = Paginator(keys, 30)
    result = paginator.get_page(page)
    counts = {name: _keys(editions, uploads, name).count() for name in CATEGORY_FIELDS}
    # Old consumers receive bounded compatibility lists; totals always come from SQL.
    preview_keys = {name: list(_keys(editions, uploads, name)[:12]) for name in ("continue", "attention", "exception", "publication_ready")}
    page_keys = list(result.object_list)
    all_keys = {row["queue_id"]: row for rows in [page_keys, *preview_keys.values()] for row in rows}
    hydrated = {row["id"]: row for row in _hydrate(all_keys.values(), user=user)}
    previews = {name: [hydrated[row["queue_id"]] for row in rows if row["queue_id"] in hydrated] for name, rows in preview_keys.items()}
    return result, counts, [hydrated[row["queue_id"]] for row in page_keys if row["queue_id"] in hydrated], previews


def next_queue_item(*, user=None, exclude_edition=None, exclude_item=None):
    editions, uploads = inventory(exclude_edition=exclude_edition, exclude_item=exclude_item)
    keys = _keys(editions, uploads)
    count = keys.count()
    first = _hydrate(keys[:1], user=user)
    return (first[0] if first else {}), count
