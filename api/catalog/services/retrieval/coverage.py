"""SQL readiness receipts; index completion writes them, publication invalidates them.

These derived counters never authorize a result. Every returned passage still
passes the source/version/text checks in discovery_projection.
"""
from django.db.models import Count, F, Q, Subquery, Sum
from django.utils import timezone

from catalog.discovery_index_models import DiscoveryDocument, DiscoverySourceState
from catalog.services.discovery_sources import edition_revision, source_queryset
from catalog.services.publication_eligibility import public_editions

SCOPE_PREFILTER_LIMIT = 400
SQL_FILTERS = {"work_ids", "_asset_id", "_primary_only", "_excluded_edition_ids", "access"}
CONTROL_FILTERS = {"_keyword_only", "_baseline", "search_scope"}


def filter_editions(rows, filters):
    if filters.get("work_ids"):
        rows = rows.filter(work_id__in=filters["work_ids"])
    if filters.get("_asset_id"):
        rows = rows.filter(active_catalog_revision__reader_asset_id=filters["_asset_id"])
    if filters.get("_primary_only"):
        rows = rows.filter(is_primary=True)
    if filters.get("_excluded_edition_ids"):
        rows = rows.exclude(pk__in=filters["_excluded_edition_ids"])
    if filters.get("access"):
        rows = rows.filter(active_catalog_revision__reader_asset__access_status__in=filters["access"])
    return rows


def receipt_values(edition, generation, source_revision):
    """Called after confirmed writes, or by the bounded legacy backfill."""
    revision = edition.active_catalog_revision
    document = revision.document_revision
    access = revision.reader_asset.access_status
    if source_revision != edition_revision(revision.pk, document.pk, document.text_checksum, access):
        return None
    counts = DiscoveryDocument.objects.filter(generation=generation, source_type="edition",
        source_id=edition.pk, source_revision=source_revision, document_revision=document,
        access_status=access, keyword_ready=True).aggregate(
            keyword_count=Count("pk"), vector_count=Count("pk", filter=Q(vector_ready=True)))
    return {**counts, "catalog_revision_id": revision.pk, "document_revision_id": document.pk,
        "indexed_text_checksum": document.text_checksum, "indexed_access_status": access,
        "coverage_verified_at": timezone.now()}


def sql_coverage(access_statuses, filters, generation):
    if any(value for key, value in filters.items() if key not in SQL_FILTERS | CONTROL_FILTERS):
        # Publication-snapshot facets and chapter attribution are checked on
        # bounded candidates. An upper bound is not a filtered coverage count.
        return {"partial": True, "scope_status": "candidate_filtered",
            "notice": "当前组合筛选逐条核验候选，未计算全范围覆盖数量。",
            "generation": str(generation.pk) if generation else None}
    eligible = filter_editions(source_queryset("edition", access_statuses), filters)
    total = eligible.count()
    published = filter_editions(public_editions().filter(
        Q(active_catalog_revision__reader_asset__isnull=True)
        | Q(active_catalog_revision__reader_asset__access_status__in=access_statuses)), filters)
    missing = published.exclude(pk__in=Subquery(eligible.values("pk")))
    bibliography = missing.filter(Q(active_catalog_revision__snapshot__edition__publication_mode="bibliographic")
        | Q(active_catalog_revision__snapshot__edition__publication_mode__isnull=True,
            publication_mode="bibliographic")).count()
    published_count = published.count()
    pending_text = max(0, published_count - total - bibliography)
    verified = DiscoverySourceState.objects.filter(generation=generation, source_type="edition",
        source_id__in=Subquery(eligible.values("pk")), coverage_verified_at__isnull=False,
        catalog_revision__edition_id=F("source_id"),
        catalog_revision_id=F("catalog_revision__edition__active_catalog_revision_id"),
        document_revision_id=F("catalog_revision__document_revision_id"),
        indexed_text_checksum=F("document_revision__text_checksum"),
        indexed_access_status=F("catalog_revision__reader_asset__access_status")) if generation else DiscoverySourceState.objects.none()
    complete = Q(indexed_at__isnull=False, error="", completed_count=F("expected_count"),
        expected_count__gt=0, keyword_count__gte=F("expected_count"))
    counts = verified.aggregate(receipts=Count("pk"), ready=Count("pk", filter=complete),
        vectors=Count("pk", filter=complete & Q(vector_count=F("keyword_count"))),
        passages=Sum("keyword_count", filter=complete))
    ready, vectors = counts["ready"], counts["vectors"]
    return {"published_editions": published_count, "bibliographic_editions": bibliography,
        "text_pending_editions": pending_text, "eligible_editions": total, "indexed_editions": ready,
        "vector_editions": vectors, "projected_editions": ready, "passage_count": counts["passages"] or 0,
        "pending_editions": total-ready, "index_pending_editions": total-ready,
        "verification_pending_editions": total-counts["receipts"],
        "vector_pending_editions": total-vectors, "partial": bool(pending_text or ready<total or vectors<ready),
        "scope_status": "verified_receipts", "generation": str(generation.pk) if generation else None}


def backfill_receipts(*, after=None, batch_size=100, apply=False):
    """One resumable SQL-only batch. No source text, models, or Meili rebuild."""
    rows = DiscoverySourceState.objects.filter(source_type="edition").order_by("pk")
    if after:
        rows = rows.filter(pk__gt=after)
    batch = list(rows[:min(500, max(1, int(batch_size)))])
    editions = {row.pk: row for row in source_queryset("edition").filter(pk__in=[state.source_id for state in batch])}
    updated = skipped = 0
    for state in batch:
        edition = editions.get(state.source_id)
        values = receipt_values(edition, state.generation_id, state.source_revision) if edition else None
        if not values or not state.indexed_at or state.error or state.completed_count != state.expected_count:
            skipped += 1
            continue
        if apply:
            changed = DiscoverySourceState.objects.filter(pk=state.pk, updated_at=state.updated_at,
                source_revision=state.source_revision).update(**values)
            updated += changed
            skipped += int(not changed)
        else:
            updated += 1
    return {"visited": len(batch), "updated" if apply else "eligible": updated, "skipped": skipped,
        "after": str(batch[-1].pk) if batch else after, "applied": apply}
