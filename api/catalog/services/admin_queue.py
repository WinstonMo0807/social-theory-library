"""Request-scoped catalog read model, shared by queues and library lists.

No process, snapshot, file or external service is mutated by this module.
Classification runs over the complete source set before pagination. Relations
are batch-loaded so the result does not build a heavy workspace per row.
"""
from collections import defaultdict

from django.db.models import Prefetch, Q, prefetch_related_objects

from catalog.models import CatalogPublicationRevision, Edition, EditorialRevision, LegacyKnowledgeMapping
from catalog.services.cataloging_sessions import OPEN_STATUSES
from catalog.services.catalog_availability import batch_catalog_availability
from catalog.services.field_decisions import field_readiness, publication_field_check
from catalog.services.publication_commands import catalog_health, catalog_publication_state, editorial_draft_applies_to_edition
from common.capabilities import Capability, has_capability
from ingestion.models import MetadataCandidate, UploadItem


CATEGORIES = ("all", "continue", "attention", "exception", "publication_ready")
UPLOAD_TERMINAL = {"published", "withdrawn", "deleted"}


def load_admin_editions(queryset):
    editions = list(queryset.select_related("work", "active_catalog_revision", "active_catalog_revision__reader_asset"))
    if not editions:
        return editions
    prefetch_related_objects(
        editions, "assets", "contributions__person", "field_decisions", "field_locks", "journal_articles",
        "cataloging_sessions", "uploaditem_set__batch", "processing_jobs",
        "work__discipline_relations", "work__subdiscipline_relations", "work__topic_relations",
        "work__knowledge_relations", "work__node_relations", "work__reading_path_items",
        "work__recommendationoverride_set__policy",
        Prefetch("catalog_revisions", queryset=CatalogPublicationRevision.objects.only(
            "id", "edition_id", "revision", "status", "updated_at", "failure_code", "failure_message",
        )),
    )
    drafts = {}
    for draft in EditorialRevision.objects.filter(
        Q(target_type="work", target_id__in={row.work_id for row in editions}) |
        Q(target_type="edition", target_id__in={row.pk for row in editions}), status="draft",
    ).order_by("-revision", "id"):
        drafts.setdefault((draft.target_type, draft.target_id), draft)
    legacy_ids = {identifier for edition in editions for row in edition.work.knowledge_relations.all()
                  for identifier in (row.theory_school_id, row.concept_id) if identifier}
    legacy_mapping = {(row.legacy_model, row.legacy_id): row.node_id for row in LegacyKnowledgeMapping.objects.filter(
        legacy_id__in=legacy_ids, migration_status=LegacyKnowledgeMapping.MigrationStatus.MAPPED,
    )} if legacy_ids else {}
    conflicts = defaultdict(list)
    edition_ids = {row.pk for row in editions}
    for candidate in MetadataCandidate.objects.filter(
        Q(upload_item__edition_id__in=edition_ids) | Q(cataloging_session__edition_id__in=edition_ids),
        lifecycle=MetadataCandidate.Lifecycle.PROPOSED,
    ).exclude(conflict_group="").values("id", "field_name", "upload_item__edition_id", "cataloging_session__edition_id"):
        for identifier in {candidate["upload_item__edition_id"], candidate["cataloging_session__edition_id"]} - {None}:
            conflicts[identifier].append({"candidate_id": str(candidate["id"]), "field": candidate["field_name"],
                                         "code": "metadata_candidate_conflict", "message": "候选来源存在分歧，需人工核对；不覆盖已确认值。"})
    availability = batch_catalog_availability(editions)
    for edition in editions:
        edition._admin_availability = availability[edition.pk]
        edition.work._admin_editorial_draft = drafts.get(("work", edition.work_id))
        edition._admin_editorial_draft = drafts.get(("edition", edition.pk))
        edition.work._admin_legacy_mapping = legacy_mapping
        edition._admin_candidate_conflicts = conflicts[edition.pk]
        edition._admin_journal_contents = [
            {"id": str(row.pk), "article_work_id": str(row.article_work_id) if row.article_work_id else None,
             "title": row.title, "author_display": row.author_display, "page_range": row.page_range, "position": row.position}
            for row in sorted(edition.journal_articles.all(), key=lambda row: (row.position, row.created_at, str(row.pk)))
        ]
    return editions


def asset_row(asset):
    return {"id": str(asset.pk), "kind": asset.kind, "version": asset.version, "status": asset.status,
            "validation_status": asset.validation_status, "is_current": asset.is_current,
            "original_filename": asset.original_filename, "updated_at": asset.updated_at,
            "page_count": asset.page_count, "mime_type": asset.mime_type,
            "source_asset_id": str(asset.source_asset_id) if asset.source_asset_id else None}


def edition_summary(edition, *, user=None):
    fields = field_readiness(edition)
    publication = catalog_publication_state(edition)
    health = catalog_health(edition, field_state=fields)
    checks = publication_field_check(edition, field_state=fields)
    assets = sorted(edition.assets.all(), key=lambda row: (row.version, row.created_at, str(row.pk)), reverse=True)
    active_reader = edition.active_catalog_revision.reader_asset if publication["catalog_revision_active"] else None
    reader = active_reader or next((row for row in assets if row.is_current and row.kind == "normalized"), None)
    current_assets = [row for row in assets if row.is_current]
    requires_document = edition.publication_mode != "bibliographic" or bool(assets)
    file_problems = []
    if requires_document:
        for kind, label in (("original", "原始文件"), ("normalized", "阅读文件")):
            asset = next((row for row in current_assets if row.kind == kind), None)
            if asset is None or asset.status != "ready":
                file_problems.append({"field": "file", "code": f"{kind}_not_ready", "message": f"{label}尚未就绪"})
            elif asset.validation_status != "valid":
                file_problems.append({"field": "file", "code": f"{kind}_{asset.validation_status}",
                                      "message": f"{label}等待验证" if asset.validation_status == "pending" else f"{label}验证失败"})
    sessions = sorted(edition.cataloging_sessions.all(), key=lambda row: (row.updated_at, str(row.pk)), reverse=True)
    session = next((row for row in sessions if row.status in OPEN_STATUSES), None)
    uploads = sorted(edition.uploaditem_set.all(), key=lambda row: (row.updated_at, str(row.pk)), reverse=True)
    pending_uploads = [row for row in uploads if row.status not in UPLOAD_TERMINAL]
    item = next((row for row in uploads if session and row.pk == session.upload_item_id), None)
    item = item or next(iter(pending_uploads), None)
    provenance_session = session or next(iter(sessions), None)
    historical_item = item or next(iter(uploads), None)
    source = provenance_session.source_type if provenance_session else "upload" if historical_item else "existing"
    if session:
        workbench = f"/admin/cataloging/{session.pk}"
    elif item:
        workbench = f"/admin/intake/{item.pk}"
    else:
        workbench = f"/admin/library/works/{edition.work_id}?edition={edition.pk}"
    field_blockers = list(checks["blockers"])
    blockers = [*field_blockers, *file_problems]
    warnings = [*checks["warnings"], *edition._admin_candidate_conflicts]
    failures = [row for row in pending_uploads if row.status == "failed"]
    jobs = sorted(edition.processing_jobs.all(), key=lambda row: (row.updated_at, str(row.pk)), reverse=True)
    failed_jobs = [row for row in jobs if row.status == "failed"]
    serving_number = edition.active_catalog_revision.revision if publication["catalog_revision_active"] else 0
    pending_revisions = [row for row in edition.catalog_revisions.all()
                         if row.status in {"preparing", "failed"} and row.revision > serving_number]
    publication_failure = any(row.status == "failed" for row in pending_revisions)
    if failures:
        blockers.extend({"field": "file", "code": row.error_code or "upload_failed", "message": "文件处理失败，可重试原任务。"} for row in failures)
    attention = bool(blockers or warnings or session or health["publication"] in {"publishing", "changes_pending"}
                     or health["processing"] in {"failed", "processing"} or failed_jobs or pending_revisions)
    actionable = bool(edition.state != "withdrawn" and (
        not publication["catalog_revision_active"] or attention or pending_uploads
    ))
    exception = bool(blockers or failures or failed_jobs or publication_failure)
    # These are saved-value checks, not a claim that NAS or publication bundle
    # execution has passed. The workspace runs the complete publication check.
    ready_for_check = not blockers and health["publication"] not in {"published", "publishing", "withdrawn"}
    if file_problems or failures:
        step, step_label = "file", "文件与阅读"
    elif field_blockers:
        from catalog.contracts.fields import FIELD_CONTRACTS

        contract = FIELD_CONTRACTS.get(field_blockers[0].get("field"))
        step = contract.section if contract else "work"
        step_label = "书目信息待核对"
    else:
        step, step_label = "publication", "预览与发布"
    draft = next((row for row in (edition.work._admin_editorial_draft, edition._admin_editorial_draft)
                  if editorial_draft_applies_to_edition(row, edition)), None)
    updated = max([edition.updated_at, edition.work.updated_at,
                   *([session.updated_at] if session else []), *([draft.updated_at] if draft else []),
                   *[row.updated_at for row in pending_uploads], *[row.updated_at for row in pending_revisions]])
    return {
        "id": f"edition:{edition.pk}", "work_id": str(edition.work_id), "edition_id": str(edition.pk),
        "item_id": str(item.pk) if item else None, "session_id": str(session.pk) if session else None,
        "source_type": source, "title": edition.work.title, "source_filename": item.source_filename if item else "",
        "document_type": edition.work.document_type, "workbench_url": workbench, "return_href": "/admin/review",
        "publication": publication, "health": health, "current_step": step, "current_step_label": step_label,
        "availability": edition._admin_availability,
        "overall_status": "attention" if exception or attention else "draft" if actionable else "complete",
        "blockers_count": len(blockers), "warnings_count": len(warnings), "unresolved_count": len(blockers) + len(warnings),
        "issues": blockers, "warnings": warnings, "candidate_conflicts": edition._admin_candidate_conflicts,
        "preflight_required": True, "checks_scope": "saved_catalog_values_and_file_records",
        "categories": ["all", *(["continue"] if actionable else []), *(["attention"] if attention else []),
                       *(["exception"] if exception else []), *(["publication_ready"] if ready_for_check else [])],
        "actionable": actionable, "updated_at": updated, "priority": max((row.priority for row in pending_uploads), default=0),
        "assets": [asset_row(row) for row in assets], "current_reader_asset": asset_row(reader) if reader else None,
        "reader_source": "active_public_revision" if active_reader else "current_file_record",
        "editing": {"draft_revision_id": str(draft.pk) if draft else None,
                    "base_public_revision_id": str(session.base_public_revision_id) if session and session.base_public_revision_id else None,
                    "has_unpublished_changes": health["publication"] == "changes_pending", "saved_at": updated},
        "processing": [{"id": str(row.pk), "status": row.status, "job_type": row.job_type, "updated_at": row.updated_at,
                        "error_code": row.error_code, "settings_version": row.settings_version,
                        "source": {key: row.stats[key] for key in ("catalog_revision_id", "document_revision_id", "text_revision", "source_asset_id") if key in (row.stats or {})}}
                       for row in jobs],
        "permissions": {"can_publish": has_capability(user, Capability.PUBLISH_WORK),
                        "can_withdraw": has_capability(user, Capability.WITHDRAW_WORK)},
        "sources": {"session_ids": [str(row.pk) for row in sessions], "upload_item_ids": [str(row.pk) for row in uploads]},
    }


def unbound_upload_row(item):
    failed = item.status == "failed"
    return {"id": f"upload:{item.pk}", "item_id": str(item.pk), "work_id": None, "edition_id": None, "session_id": None,
            "source_type": "upload", "title": item.source_filename, "source_filename": item.source_filename,
            "document_type": item.document_type_hint, "workbench_url": f"/admin/uploads?item={item.pk}", "return_href": "/admin/review",
            "publication": {"editorial_state": None, "public_state": "unpublished", "catalog_revision_active": False,
                            "publicly_visible": False, "listed_publicly": False, "public_url": "", "active_revision_id": None,
                            "detail": "上传来源尚未建立出版版本；请先完成导入或处理失败。"},
            "health": {"editorial": "draft", "processing": "failed" if failed else "processing", "publication": "unpublished"},
            "current_step": "file", "current_step_label": "文件导入", "overall_status": "attention" if failed else "working",
            "blockers_count": int(failed), "warnings_count": 0, "unresolved_count": int(failed),
            "categories": ["all", "continue", *(["attention", "exception"] if failed else [])],
            "actionable": True, "updated_at": item.updated_at, "priority": item.priority, "preflight_required": True}


def workflow_rows(*, user=None, publication_scope=False):
    rows = [edition_summary(edition, user=user) for edition in load_admin_editions(Edition.objects.all())]
    if not publication_scope:
        rows = [row for row in rows if row["actionable"]]
    rows.extend(unbound_upload_row(item) for item in UploadItem.objects.filter(edition__isnull=True).exclude(status__in=UPLOAD_TERMINAL))
    # Oldest work first within explicit priority; stable identity is the final
    # tie-breaker, so older failures never disappear behind recent arrivals.
    return sorted(rows, key=lambda row: (-row["priority"], row["updated_at"], row["id"]))


def attach_library_editions(works):
    grouped = defaultdict(list)
    for edition in load_admin_editions(Edition.objects.filter(work_id__in=[work.pk for work in works])):
        grouped[edition.work_id].append(edition)
    for work in works:
        work._admin_editions = grouped[work.pk]
    return works


def serialize_edition_library_row(edition, *, user=None):
    row = edition_summary(edition, user=user)
    contributors = [entry.person.preferred_name for entry in sorted(edition.contributions.all(), key=lambda entry: entry.order) if entry.approved]
    return {**row, "row_type": "edition", "id": str(edition.pk), "is_primary": edition.is_primary,
            "label": edition.version_label or str(edition.publication_year or "出版信息待补"),
            "version_label": edition.version_label, "publication_year": edition.publication_year,
            "publisher": edition.publisher, "publication_place": edition.publication_place,
            "isbn": edition.isbn, "doi": edition.doi, "language": edition.work.language,
            "publication_mode": edition.publication_mode, "contributors": contributors,
            "publication_state": row["publication"]["public_state"], "edition_count": 1,
            "asset_state": row["current_reader_asset"]["status"] if row["current_reader_asset"] else "not_applicable" if not row["assets"] and edition.publication_mode == "bibliographic" else "pending",
            "primary_edition": {"id": str(edition.pk), "label": edition.version_label or str(edition.publication_year or "当前版本")}}
