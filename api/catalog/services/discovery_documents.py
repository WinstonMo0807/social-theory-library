"""Bounded source-query receipts in the existing session; never copied source text."""
from collections import Counter

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from catalog.discovery_models import DiscoverySearchSession
from catalog.discovery_index_models import DiscoveryDocument, DiscoverySourceState
from catalog.services.discovery_sources import (
    iter_edition_metadata_headers, iter_source_headers, source_queryset,
)
from catalog.services.publication_eligibility import public_editions

DOCUMENTS_KEY = "_documents"
EXCLUDED_KEY = "_excluded_editions"
MAX_DOCUMENTS = 200
DOCUMENT_STATUSES = ("queued", "running", "completed", "no_returned", "partial", "failed",
                     "waiting_index", "unreadable", "changed", "canceled")


def effective_filters(session):
    excluded = list((session.results or {}).get(EXCLUDED_KEY) or [])
    return {**session.filters, **({"_excluded_edition_ids": excluded} if excluded else {})}


def allowed_rows(session, rows):
    excluded = set((session.results or {}).get(EXCLUDED_KEY) or [])
    return [row for row in rows if str(row.get("edition_id")) not in excluded]


def begin_document_query(session_id, generation, task_id, scopes, index):
    """Called only when the original passage query has resolved its actual scope.

    A source receipt means its index was included in that query, not that every
    chapter was read or that a top-k miss establishes low relevance.
    """
    from catalog.services.discovery_projection import _matches
    session = DiscoverySearchSession.objects.filter(pk=session_id, generation=generation,
        task_id=task_id, status__in=("queued", "running"), expires_at__gt=timezone.now()).first()
    if session is None:
        return
    filters = effective_filters(session)
    scope_ids = {token.split(":")[1]: token for token in scopes if token.startswith("edition:")}
    receipts = []
    total = 0
    for edition, header in iter_edition_metadata_headers(public_editions().order_by("id")):
        if not _matches(header, filters):
            continue
        total += 1
        if len(receipts) >= MAX_DOCUMENTS:
            break
        receipts.append({"edition_id": str(edition.pk), "work_id": str(edition.work_id),
            "catalog_revision": str(edition.active_catalog_revision_id),
            "source_revision": scope_ids.get(str(edition.pk), "").split(":")[-1],
            "status": "queued" if str(edition.pk) in scope_ids else "unreadable"})
    # Index readiness is a prerequisite, never proof that this query completed.
    states = {str(row.source_id): row for row in DiscoverySourceState.objects.filter(
        generation=index, source_type="edition", source_id__in=[r["edition_id"] for r in receipts])} if index else {}
    indexed = {(str(row["source_id"]), row["source_revision"]): row["count"] for row in DiscoveryDocument.objects.filter(
        generation=index, source_type="edition", source_id__in=states, keyword_ready=True,
        access_status__in=session.access_statuses).values("source_id", "source_revision").annotate(count=Count("pk"))} if index else {}
    for receipt in receipts:
        if receipt["status"] != "queued":
            continue
        state = states.get(receipt["edition_id"])
        ready = bool(state and state.source_revision == receipt["source_revision"] and state.indexed_at
                     and not state.error and state.completed_count == state.expected_count and state.expected_count > 0
                     and indexed.get((receipt["edition_id"], receipt["source_revision"])) == state.expected_count)
        receipt["status"] = "running" if ready else "waiting_index"
    with transaction.atomic():
        current = DiscoverySearchSession.objects.select_for_update().filter(pk=session_id, generation=generation,
            task_id=task_id, status__in=("queued", "running"), expires_at__gt=timezone.now()).first()
        if current is None:
            return
        current.results = {**current.results, DOCUMENTS_KEY: {"generation": generation, "total": total,
            "truncated": total > MAX_DOCUMENTS, "rows": receipts}}
        current.save(update_fields=["results", "updated_at"])


def finish_document_query(session, warnings, *, failed=False):
    """Called under the same task CAS and transaction that materializes results."""
    state = (session.results or {}).get(DOCUMENTS_KEY)
    if not state or state.get("generation") != session.generation:
        return
    codes = {row.get("code") for row in warnings}
    failed = failed or {"keyword_unavailable", "dense_unavailable"} <= codes
    rows = [{**row, "status": ("failed" if failed else "partial" if warnings else "completed")}
            if row.get("status") == "running" else row for row in state.get("rows", [])]
    session.results = {**session.results, DOCUMENTS_KEY: {**state, "rows": rows}}


def document_payload(session, access_statuses, passage_rows):
    state = (session.results or {}).get(DOCUMENTS_KEY) or {}
    excluded = set((session.results or {}).get(EXCLUDED_KEY) or [])
    refs = [r for r in state.get("rows", [])[:MAX_DOCUMENTS] if r.get("edition_id") not in excluded]
    counts = Counter(str(row.get("edition_id")) for row in passage_rows)
    public = {str(row.pk): (row, header) for row, header in iter_edition_metadata_headers(
        public_editions().filter(pk__in=[r["edition_id"] for r in refs]))}
    eligible = {str(row.pk): header for row, header in iter_source_headers("edition", access_statuses,
        queryset=source_queryset("edition", access_statuses).filter(pk__in=public).exclude(active_catalog_revision__reader_asset__file=""))}
    versions = {}
    for row, header in iter_edition_metadata_headers(public_editions().filter(
            work_id__in={r["work_id"] for r in refs}).order_by("-is_primary", "id")):
        work_id = str(row.work_id)
        choices = versions.setdefault(work_id, [])
        if len(choices) < 6:
            choices.append({"id": str(row.pk), "label": header["bibliography"]["version_label"] or header["title"],
                "url": header["url"]})
    output = []
    for ref in refs:
        key = ref["edition_id"]
        edition, header = public.get(key, (None, None))
        status = ref.get("status", "queued")
        if not edition or key not in eligible:
            status = "unreadable"
        elif (str(edition.active_catalog_revision_id) != ref["catalog_revision"]
                or ref.get("source_revision") and eligible[key]["source_revision"] != ref["source_revision"]):
            status = "changed"
        elif status in {"queued", "running"}:
            if session.status == "canceled":
                status = "canceled"
            elif session.status not in {"queued", "running"}:
                status = "failed"
        if status == "completed" and not counts[key]:
            status = "no_returned"
        output.append({"edition_id": key, "work_id": ref["work_id"], "status": status,
            "title": header["title"] if header else "来源暂不可用", "authors": header["authors"] if header else [],
            "bibliography": header["bibliography"] if header else None,
            "material_count": counts[key], "available_versions": versions.get(ref["work_id"], []),
            "url": header["url"] if header else ""})
    return {"items": output, "counts": dict(Counter(row["status"] for row in output)),
        "tracked": len(output), "truncated": bool(state.get("truncated")),
        "excluded_count": len(excluded), "notice": "按出版版本记录本轮索引查询。未返回材料不代表不存在相关讨论；未逐章分析，也不据此判断相关性。"}


def remove_document(session, edition_id, access_statuses, *, expected_generation):
    from catalog.services.discovery_sessions import ACTIVE, _resume_locked, cancel_session
    from common.concurrency import capacity_slot
    from rest_framework.exceptions import Throttled
    key = str(edition_id)
    with capacity_slot("discovery-admission", limit=1, timeout=10) as acquired:
        if not acquired:
            raise Throttled(wait=1, detail="正在更新检索范围，请稍后重试。")
        with transaction.atomic():
            current = DiscoverySearchSession.objects.select_for_update().get(pk=session.pk)
            if current.expires_at <= timezone.now():
                raise NotFound("检索记录已过期。")
            excluded = list((current.results or {}).get(EXCLUDED_KEY) or [])
            if key in excluded:
                return current  # A lost response may safely repeat the same removal.
            if current.generation != expected_generation:
                raise ValidationError({"expected_generation": "检索轮次已改变，请刷新后重试。"})
            roster = ((current.results or {}).get(DOCUMENTS_KEY) or {}).get("rows", [])
            if key not in {r.get("edition_id") for r in roster}:
                raise NotFound("本次检索中不存在该文献记录。")
            if len(excluded) >= MAX_DOCUMENTS:
                raise ValidationError({"edition_id": "移除数量已达本次上限，请调整筛选后重新检索。"})
            active = current.status in ACTIVE
            if active:
                current = cancel_session(current)
            else:
                current.generation += 1
            current.results = {**current.results, EXCLUDED_KEY: [*excluded, key]}
            current.access_statuses = sorted(set(current.access_statuses).intersection(access_statuses))
            current.save(update_fields=["results", "generation", "access_statuses", "updated_at"])
            if active:
                current = _resume_locked(current, access_statuses, expand=False, expected_generation=current.generation)
            return current
