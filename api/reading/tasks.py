"""Durable private jobs. Queue messages contain IDs, never manuscript contents."""
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4
import logging

from celery import shared_task
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import CitationAudit, ResearchTurn
from .research import (ACTIVE, access_for, analyze_references, compact_reference,
                       pack, reference_identity, resolve_reference, save_data, unpack)
from .document_preview import render_document_preview  # noqa: F401; register the isolated preview task.
from .source_follow import refresh_source_follows  # noqa: F401; bounded public-status checks only.

logger = logging.getLogger(__name__)


@shared_task(soft_time_limit=240, time_limit=270)
def purge_expired_booklist_items():
    from django.contrib.auth import get_user_model
    from .booklists import purge_expired_owner
    from .models import ReadingListItem
    owners = list(ReadingListItem.objects.filter(removed_at__lte=timezone.now() - timedelta(days=30))
        .order_by().values_list("reading_list__user_id", flat=True).distinct()[:100])
    removed = 0
    for user in get_user_model().objects.filter(pk__in=owners).order_by("pk"):
        removed += purge_expired_owner(user)
    return {"expired_memberships_removed": removed}


@shared_task(soft_time_limit=480, time_limit=540)
def run_reader_data_operation(operation_id, generation, task_id):
    from .privacy import run_operation
    run_operation(operation_id, generation, task_id)


def enqueue_research_turn(turn_id, generation, task_id, countdown=0):
    try:
        collect_research_turn.apply_async(args=[str(turn_id), generation, task_id], task_id=task_id, countdown=countdown)
    except Exception as exc:
        logger.warning("Private research dispatch failed (%s)", type(exc).__name__)
        ResearchTurn.objects.filter(pk=turn_id, generation=generation, task_id=task_id, status__in=ACTIVE).update(
            status="failed", error_code="queue_unavailable", finished_at=timezone.now())


@shared_task(soft_time_limit=240, time_limit=270)
def collect_research_turn(turn_id, generation, task_id):
    claimed = ResearchTurn.objects.filter(pk=turn_id, generation=generation, task_id=task_id, status="queued").update(
        status="running", updated_at=timezone.now())
    if not claimed:
        return
    turn = ResearchTurn.objects.select_related("project__user").filter(pk=turn_id, generation=generation, task_id=task_id).first()
    if turn is None:
        return
    try:
        user = turn.project.user
        payload = unpack(turn)
        if "comparison_draft" in payload:
            from .research_comparison import process_draft
            process_draft(turn, generation, task_id)
            return
        warnings = []
        if payload["scope"]["kind"] == "passages":
            refs = payload["scope"]["references"]
            status = "completed"
        else:
            from catalog.discovery_models import DiscoverySearchSession
            from catalog.services.discovery_sessions import _public_row, create_session, rehydrate_passages
            if turn.discovery_session_id is None:
                search_question = payload.get("search_question", payload["question"])
                query_plan = {"query": search_question, "method": "explicit_subclaim" if payload.get("active_subclaim_id") else "original_question"}
                if payload.get("mode") == "counterargument":
                    from .research import counterargument_query
                    query_plan = counterargument_query(payload.get("analysis_statement", payload["statement"]), search_question)
                elif turn.parent_id or payload.get("selected_refs"):
                    from .local_analysis import plan_followup
                    history, parent = [], turn.parent
                    for _ in range(3):
                        if parent is None or parent.project_id != turn.project_id:
                            break
                        history.insert(0, {"question": unpack(parent)["question"]})
                        parent = parent.parent
                    context_limit = 20 if payload.get("context_explicit") else 5
                    selected = [resolve_reference(ref, user) for ref in payload.get("selected_refs", [])[:context_limit]]
                    from .research import plan_memory_rows, search_memories
                    # Search only notes currently authorized by this owner for this research project.
                    context = {"kind": "project", "id": str(turn.project_id)}
                    notes = search_memories(user, search_question, context=context) if plan_memory_rows(user, unpack(turn.project)) else {"results": []}
                    query_plan = plan_followup(search_question, history,
                        [{"quote": row["quote"], "title": row["title"]} for row in selected if row["source_status"] == "available"],
                        memories=[{"id": row["id"], "body": row["data"].get("body", "")}
                                  for row in notes["results"][:5]])
                with transaction.atomic():
                    current = ResearchTurn.objects.select_for_update().filter(pk=turn.id, generation=generation, task_id=task_id, status="running").first()
                    if current is None:
                        return
                    if current.discovery_session_id is None:
                        session, _token = create_session(SimpleNamespace(user=user), query_plan["query"], payload["scope"]["filters"])
                        current.discovery_session_id = session.id
                        payload["query_plan"] = query_plan
                        save_data(current, payload, fields=["discovery_session_id"])
                    turn.discovery_session_id = current.discovery_session_id
            session = DiscoverySearchSession.objects.filter(pk=turn.discovery_session_id, owner=user).first()
            if session is None:
                raise LookupError("discovery_expired")
            visible = rehydrate_passages(session, sorted(set(session.access_statuses) & set(access_for(user))))
            refs = []
            for candidate in visible:
                row = _public_row(candidate)
                raw = {key: row.get(key) for key in ("evidence_span_id", "asset_id", "document_revision_id", "pdf_page")}
                if not raw["evidence_span_id"] and not all(raw.get(key) for key in ("asset_id", "document_revision_id", "pdf_page")):
                    warnings.append({"code": "missing_locator", "message": "一项候选缺少完整原文定位，未保存为证据。"})
                    continue
                ref = resolve_reference(raw, user)
                if ref["source_status"] == "available":
                    refs.append(compact_reference(ref))
            status, warnings = session.status, [*warnings, *session.warnings]
        # Adopt Discovery's current order without dropping earlier material on retry,
        # scope expansion or withdrawal. Stored identities are revalidated on every read.
        old_refs = payload.get("result_refs", [])
        merged = {reference_identity(ref): ref for ref in refs}
        for ref in old_refs:
            merged.setdefault(reference_identity(ref), ref)
        payload["result_refs"] = list(merged.values())
        payload["warnings"] = warnings
        timed_out = timezone.now() - turn.created_at > timedelta(minutes=30)
        if status in ACTIVE and timed_out:
            status = "partial" if merged else "failed"
            payload["warnings"].append({"code": "task_timeout", "message": "本轮超时，已保留得到的材料。"})
        with transaction.atomic():
            checkpoint = ResearchTurn.objects.select_for_update().filter(pk=turn_id, generation=generation, task_id=task_id, status="running").first()
            if checkpoint is None:
                return
            save_data(checkpoint, payload)
        if status not in ACTIVE and payload.get("mode") == "counterargument":
            payload["analysis"] = analyze_references(payload["statement"], payload["result_refs"], user)
            from .local_analysis import analyze_local_relations
            candidates = []
            for row in payload["analysis"][:20]:
                current_ref = resolve_reference(row["reference"], user)
                if current_ref["source_status"] == "available":
                    candidates.append({"reference_id": row["id"], "quote": current_ref["quote"],
                                       "claim": row["candidate_statement"]})
            suggestions, model = analyze_local_relations(payload["statement"], candidates) if candidates else ([], {"status": "no_evidence"})
            by_id = {row["reference_id"]: row for row in suggestions}
            for row in payload["analysis"]:
                if row["id"] in by_id:
                    row["model_suggestion"] = by_id[row["id"]]
                    row["model"] = model
            payload["analysis_model"] = model
            payload["analysis_model_limit"] = 20
            payload["analysis_notice"] = "结果是待核对候选；规则信号、相似度和归因都不证明学术反证。"
        with transaction.atomic():
            current = ResearchTurn.objects.select_for_update().filter(pk=turn_id, generation=generation, task_id=task_id, status="running").first()
            if current is None:
                return
            current.status = "queued" if status in ACTIVE else status
            next_task_id = str(uuid4()) if status in ACTIVE else task_id
            current.task_id = next_task_id
            current.finished_at = None if status in ACTIVE else timezone.now()
            save_data(current, payload, fields=["status", "finished_at", "task_id"])
        if status in ACTIVE:
            enqueue_research_turn(turn_id, generation, next_task_id, countdown=3)
        elif payload.get("plan_id"):
            from .models import PersonalReadingPlan
            from .research import generate_plan
            plan = PersonalReadingPlan.objects.filter(pk=payload["plan_id"], user=user).first()
            if plan:
                plan_data = unpack(plan)
                try:
                    generate_plan(user, {**plan_data, "project_id": str(turn.project_id), "turn_id": str(turn.id)}, existing=plan)
                except Exception as exc:
                    logger.warning("Private plan generation failed (%s)", type(exc).__name__)
                    with transaction.atomic():
                        current_plan = PersonalReadingPlan.objects.select_for_update().filter(pk=plan.id, user=user).first()
                        if current_plan and unpack(current_plan).get("generation_status") == "queued":
                            current_data = unpack(current_plan)
                            current_data["generation_status"] = "failed"
                            current_data["error_code"] = "no_readable_materials_or_generation_failed"
                            save_data(current_plan, current_data)
    except Exception as exc:
        # Do not write exception text: providers/parsers can echo private inputs.
        logger.warning("Private research failed (%s)", type(exc).__name__)
        ResearchTurn.objects.filter(pk=turn_id, generation=generation, task_id=task_id, status__in=ACTIVE).update(
            status="failed", error_code="research_processing_failed", finished_at=timezone.now())


def enqueue_citation_audit(audit_id, generation, task_id):
    try:
        run_citation_audit.apply_async(args=[str(audit_id), generation, task_id], task_id=task_id)
    except Exception as exc:
        logger.warning("Private audit dispatch failed (%s)", type(exc).__name__)
        CitationAudit.objects.filter(pk=audit_id, generation=generation, task_id=task_id, status__in=ACTIVE).update(
            status="failed", error_code="queue_unavailable", finished_at=timezone.now())


@shared_task(soft_time_limit=840, time_limit=900)
def run_citation_audit(audit_id, generation, task_id):
    from .citation_audit import process_audit
    try:
        process_audit(audit_id, generation, task_id)
    except Exception as exc:
        logger.warning("Private citation audit failed (%s)", type(exc).__name__)
        CitationAudit.objects.filter(pk=audit_id, generation=generation, task_id=task_id, status__in=ACTIVE).update(
            status="failed", error_code="audit_processing_failed", finished_at=timezone.now())


def enqueue_plan_enhancement(plan_id, revision):
    try:
        enhance_reading_plan.delay(str(plan_id), revision)
    except Exception as exc:
        logger.warning("Private plan enhancement dispatch failed (%s)", type(exc).__name__)
        from .models import PersonalReadingPlan
        with transaction.atomic():
            plan = PersonalReadingPlan.objects.select_for_update().filter(pk=plan_id, revision=revision).first()
            if plan:
                payload = unpack(plan)
                payload["enhancement_status"] = "queue_unavailable"
                save_data(plan, payload)


@shared_task(soft_time_limit=240, time_limit=270)
def enhance_reading_plan(plan_id, revision):
    from .models import PersonalReadingPlan
    from .research import (invalidate_plan_suggestions, plan_memory_rows, plan_suggestions_current, serialize_record)
    from .local_analysis import propose_plan_labels
    with transaction.atomic():
        plan = PersonalReadingPlan.objects.select_for_update().select_related("user").filter(pk=plan_id, revision=revision).first()
        if plan is None:
            return
        payload = unpack(plan)
        if payload.get("enhancement_status") != "queued":
            return
        payload["enhancement_status"] = "running"
        save_data(plan, payload)
        revision = plan.revision
    try:
        # A scope may be revoked while the queued job is starting. Do not decrypt
        # reminders from the stale snapshot after that explicit authorization change.
        current = PersonalReadingPlan.objects.filter(pk=plan_id, user=plan.user, revision=revision).first()
        if current is None or unpack(current).get("enhancement_status") != "running":
            return
        payload = unpack(current)
        invalidate_plan_suggestions(payload, "running")
        reminders = plan_memory_rows(plan.user, payload)
        memory_data = [{"id": str(row.id), "body": unpack(row)["body"]} for row in reminders]
        current_data = serialize_record(current, plan.user)["data"]
        current_data["items"] = [row for row in current_data.get("items", []) if row.get("available") and row.get("status") != "completed"]
        suggestions, model = propose_plan_labels(current_data, memory_data)
        by_id = {row["item_id"]: row for row in suggestions}
        for item in payload["items"]:
            if item["id"] in by_id and item.get("status") != "completed":
                item["model_suggestion"] = by_id[item["id"]]
        payload["enhancement_status"] = model["status"]
        payload["enhancement_model"] = model
        payload["memory_reminder_ids"] = [row["id"] for row in memory_data]
        payload["memory_reminder_revisions"] = {str(row.id): row.revision for row in reminders}
    except Exception as exc:
        logger.warning("Private plan enhancement failed (%s)", type(exc).__name__)
        payload = unpack(plan)
        invalidate_plan_suggestions(payload, "unavailable")
    with transaction.atomic():
        current = PersonalReadingPlan.objects.select_for_update().filter(pk=plan_id, revision=revision).first()
        if current and unpack(current).get("enhancement_status") == "running":
            if not plan_suggestions_current(plan.user, payload, lock=True):
                invalidate_plan_suggestions(payload, "authorization_changed")
            save_data(current, payload)


@shared_task(soft_time_limit=110, time_limit=120)
def recover_private_research_tasks():
    """Recover bounded stale leases after broker loss or a killed worker, without private text in messages."""
    from .models import PersonalReadingPlan
    now = timezone.now()
    summary = {"research": 0, "audits": 0, "plans": 0, "exhausted": 0}
    for model, key, minutes, enqueue in (
        (ResearchTurn, "research", 6, enqueue_research_turn),
        (CitationAudit, "audits", 16, enqueue_citation_audit),
    ):
        eligible = Q(status__in=ACTIVE) | Q(status="failed", error_code__in=["queue_unavailable", "task_timeout"])
        cutoff = now - timedelta(minutes=minutes)
        ids = list(model.objects.filter(eligible, updated_at__lt=cutoff).order_by("updated_at").values_list("pk", flat=True)[:50])
        for record_id in ids:
            with transaction.atomic():
                if model is CitationAudit:
                    from django.contrib.auth import get_user_model
                    from .citation_audit import MAX_ACTIVE_AUDITS_PER_OWNER
                    owner_id = CitationAudit.objects.filter(pk=record_id).values_list("user_id", flat=True).first()
                    if owner_id is None or get_user_model().objects.select_for_update().filter(pk=owner_id).first() is None:
                        continue
                record = model.objects.select_for_update().filter(eligible, pk=record_id, updated_at__lt=cutoff).first()
                if record is None:
                    continue
                if (model is CitationAudit and record.status not in ACTIVE
                        and CitationAudit.objects.filter(user_id=record.user_id, status__in=ACTIVE).count() >= MAX_ACTIVE_AUDITS_PER_OWNER):
                    # Keep the failed record, attempt budget and lease untouched until capacity returns.
                    continue
                payload = unpack(record)
                attempts = int(payload.get("recovery_attempts", 0))
                if attempts >= 3:
                    record.status, record.error_code, record.finished_at = "failed", "recovery_exhausted", now
                    save_data(record, payload, fields=["status", "error_code", "finished_at"])
                    summary["exhausted"] += 1
                    continue
                if model is CitationAudit and payload.get("parsed"):
                    target_ids = payload.get("rerun_occurrence_ids")
                    payload["rerun_occurrence_ids"] = [row["id"] for row in payload.get("occurrences", [])
                        if (target_ids is None or row["id"] in target_ids) and row.get("checked_generation") != record.generation]
                payload["recovery_attempts"] = attempts + 1
                payload.setdefault("recovery_history", []).append({"at": now.isoformat(), "generation": record.generation,
                    "reason": record.error_code or "worker_lease_expired"})
                record.generation += 1
                record.task_id = str(uuid4())
                record.status, record.error_code, record.finished_at = "queued", "", None
                fields = ["generation", "task_id", "status", "error_code", "finished_at"]
                if model is CitationAudit:
                    payload["stage"] = "queued"
                    record.completed_units = 0
                    selected = payload.get("rerun_occurrence_ids")
                    record.total_units = len(selected) if selected is not None else len(payload.get("occurrences", []))
                    fields.extend(["completed_units", "total_units"])
                save_data(record, payload, fields=fields)
                transaction.on_commit(lambda pk=record.id, generation=record.generation, token=record.task_id, send=enqueue:
                    send(pk, generation, token))
                summary[key] += 1
    # Null markers are old encrypted rows. Classifying them lazily avoids a data migration that needs private keys.
    plan_cutoff = now - timedelta(minutes=10)
    ids = list(PersonalReadingPlan.objects.filter(Q(task_pending=True) | Q(task_pending__isnull=True),
        updated_at__lt=plan_cutoff).order_by("updated_at").values_list("pk", flat=True)[:50])
    for plan_id in ids:
        if _recover_plan(plan_id, plan_cutoff):
            summary["plans"] += 1
    return summary


def _recover_plan(plan_id, cutoff):
    from django.contrib.auth import get_user_model
    from .models import PersonalReadingPlan
    from .research import generate_plan
    candidate = PersonalReadingPlan.objects.filter(pk=plan_id).first()
    if candidate is None:
        return False
    with transaction.atomic():
        # All plan-generating commands take the owner lock before the plan lock.
        get_user_model().objects.select_for_update().get(pk=candidate.user_id)
        if candidate.project_id:
            from .models import ResearchProject
            ResearchProject.objects.select_for_update().filter(pk=candidate.project_id, user_id=candidate.user_id).first()
        plan = PersonalReadingPlan.objects.select_for_update().select_related("user").filter(pk=plan_id, updated_at__lt=cutoff).first()
        if plan is None:
            return False
        payload = unpack(plan)
        if payload.get("generation_status") in ACTIVE:
            source = ResearchTurn.objects.filter(pk=payload.get("origin", {}).get("turn_id"), project__user=plan.user).first()
            if source and source.status in ACTIVE:
                # Its separate lease recovery will resume the search. Do not repeatedly decrypt this row.
                save_data(plan, payload)
                return False
            if source and source.status in {"completed", "partial"} and unpack(source).get("result_refs"):
                try:
                    generate_plan(plan.user, {**payload, "project_id": str(source.project_id), "turn_id": str(source.id)}, existing=plan)
                    return True
                except Exception as exc:
                    logger.warning("Private plan recovery failed (%s)", type(exc).__name__)
            payload.update(generation_status="failed", error_code="source_research_incomplete")
        elif payload.get("enhancement_status") in ACTIVE | {"queue_unavailable"}:
            attempts = int(payload.get("recovery_attempts", 0))
            if attempts >= 3:
                payload.update(enhancement_status="unavailable", error_code="recovery_exhausted")
            else:
                payload.update(enhancement_status="queued", recovery_attempts=attempts + 1)
                save_data(plan, payload)
                transaction.on_commit(lambda: enqueue_plan_enhancement(plan.id, plan.revision))
                return True
        save_data(plan, payload)
        return True
