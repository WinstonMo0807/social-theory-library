"""One explicit save for an Edition workspace, using existing draft services.

Receipts and review provenance live in the existing audit/field-decision records.
Nothing here exports a training corpus or treats editorial acceptance as truth.
"""
from __future__ import annotations

import hashlib
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q

from catalog.models import CatalogFieldDecision, Edition, EditorialRevision, Work
from catalog.contracts.fields import FIELDS
from catalog.services.field_decisions import formal_field_values, record_edition_field_decision
from catalog.services.work_editor import (
    WorkflowEditConflict, WorkflowEditError,
    save_editorial_workflow_section, save_workflow_section,
)
from ingestion.models import AuditEvent


ASSISTED_FIELDS = {
    **{field.name: (field.name, field.section) for field in FIELDS
       if field.section in {"work", "bibliography"}
       and field.data_type in {"string", "text", "integer", "date", "identifier"}
       and "compatibility_alias" not in field.publication_rules},
    "author": ("authors", "contributors"),
    "translator": ("translators", "contributors"),
}


def _prefill_is_present(row, sections):
    """A removed/replaced person is not an accepted suggestion."""
    field = row["field_name"]
    _canonical, step = ASSISTED_FIELDS[field]
    if step == "contributors":
        if not row.get("selected_entity_id") or "contributors" not in sections.get(step, {}):
            raise WorkflowEditError("请先确认具体人物，并同时保存作者或译者列表。")
        return any(str(item["person_id"]) == str(row["selected_entity_id"]) and item["role"] == field
                   for item in sections[step]["contributors"])
    if field not in sections.get(step, {}):
        raise WorkflowEditError("请同时提交建议所填写字段的最终值。")
    return sections[step][field] not in (None, "")


def _digest(value):
    return hashlib.sha256(json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def workspace_edit_version(edition):
    # Include drafts from other Editions: they share the Work-level editor.
    revisions = list(EditorialRevision.objects.filter(
        Q(target_type="work", target_id=edition.work_id)
        | Q(target_type="edition", target_id=edition.pk),
    ).order_by("-updated_at", "-id").values_list("id", "status", "updated_at")[:1])
    decisions = list(edition.field_decisions.order_by("-updated_at", "-id").values_list("id", "updated_at")[:1])
    locks = list(edition.field_locks.order_by("field_name").values_list("field_name", "locked_value", "updated_at"))
    return _digest([edition.pk, edition.updated_at, edition.work.updated_at, revisions, decisions, locks])


def _save_section(edition, step, values, *, actor, confirm):
    values = dict(values)
    # One version was checked under the transaction lock before any writes.
    values.pop("expected_updated_at", None)
    values.pop("expected_work_updated_at", None)
    note = values.pop("note", "")
    if step != "curation" and edition.work.editions.filter(state="published").exists():
        patch = (values if step == "work" else {step: values} if step in {"classification", "knowledge"}
                 else {step: {"edition_id": str(edition.pk), "values": values}})
        save_editorial_workflow_section(
            edition, step, values, actor=actor, confirm_section=confirm,
            section_patch=patch, change_note=note or "保存本页书目修改",
        )
    else:
        save_workflow_section(edition, step, {**values, "note": note}, actor=actor, confirm_section=confirm)


@transaction.atomic
def save_workspace_edits(*, work_id, edition_id, expected_version, request_id, sections, confirmations, suggestions, actor):
    # Existing enrichment mutations lock a research run before the Edition.
    # Respect that order, including requests containing several suggestions.
    from catalog.models import EnrichmentCandidate, ResearchRun
    from catalog.services.field_assistant import FieldAssistantService

    enrichment_ids = [row["source_id"] for row in suggestions if row["source_type"] == "enrichment"]
    run_ids = {str(ctx["research_run_id"]) for ctx in EnrichmentCandidate.objects.filter(pk__in=enrichment_ids).values_list("request_context", flat=True) if ctx and ctx.get("research_run_id")}
    list(ResearchRun.objects.select_for_update().filter(pk__in=run_ids).order_by("pk"))
    edition = Edition.objects.select_for_update().filter(pk=edition_id, work_id=work_id).first()
    if edition is None:
        raise WorkflowEditError("请选择这部作品的具体出版版本。")
    edition.work = Work.objects.select_for_update().get(pk=work_id)
    fingerprint = _digest([expected_version, sections, sorted(confirmations), suggestions])
    receipt = AuditEvent.objects.filter(
        action="workspace.edits.saved", object_type="edition", object_id=str(edition.pk),
        request_id=request_id, actor=actor,
    ).first()
    if receipt:
        if receipt.after.get("request_fingerprint") != fingerprint:
            raise WorkflowEditConflict("这次保存编号已用于另一组修改，请刷新后重试。")
        return edition, receipt, True
    if workspace_edit_version(edition) != expected_version:
        raise WorkflowEditConflict("其他操作已更新这份书目。你的输入仍保留，请刷新后核对差异再保存。")

    before, _ = formal_field_values(edition)
    from catalog.services.field_assistant.refresh import form_context_for_edits

    lookup_context = form_context_for_edits(edition, sections)
    adopted = []
    seen = set()
    for row in suggestions:
        field_name = row["field_name"]
        key = (field_name, str(row.get("selected_entity_id") or "")) if field_name in {"author", "translator"} else (field_name, "")
        if field_name not in ASSISTED_FIELDS or key in seen:
            raise WorkflowEditError("这项建议不能重复填写，请回到对应字段核对。")
        field, step = ASSISTED_FIELDS[field_name]
        allowed = {"metadata", "enrichment"}
        if step == "contributors":
            allowed |= {"local_person", "entity_resolution"}
        elif field_name == "publisher":
            allowed |= {"local_publisher", "entity_resolution"}
        if row["source_type"] not in allowed:
            raise WorkflowEditError("建议来源与所填写的字段不一致。")
        seen.add(key)
        if not _prefill_is_present(row, sections):
            continue
        result = FieldAssistantService().adopt(edition_id=edition.pk, actor=actor, lookup_context=lookup_context, **row)
        decision = CatalogFieldDecision.objects.get(pk=result["decision_id"])
        edition.refresh_from_db()
        proposed, _ = formal_field_values(edition)
        adopted.append((row, proposed.get(field), dict(decision.provenance), list(decision.evidence_summary)))

    for step, values in sections.items():
        _save_section(edition, step, values, actor=actor, confirm=step in confirmations)
    edition.refresh_from_db()
    after, _ = formal_field_values(edition)
    assistance = []
    for row, proposed, provenance, evidence in adopted:
        field, step = ASSISTED_FIELDS[row["field_name"]]
        final = after.get(field)
        # A person suggestion selects one identity/role, not the whole author list.
        # Accepting another person must not fabricate a manual correction event.
        identity_selection = step == "contributors"
        if identity_selection and str(row["selected_entity_id"]) not in {str(value) for value in final or []}:
            raise WorkflowEditError("最终作者或译者列表未保留所选人物，请重新核对后保存。")
        outcome = "used_unchanged" if identity_selection or final == proposed else "used_after_edit"
        outcome_scope = "selected_identity" if identity_selection else "field_value"
        current = CatalogFieldDecision.objects.filter(edition=edition, field_name=field).first()
        decision = record_edition_field_decision(
            edition, field, actor=actor, value=final,
            status=(CatalogFieldDecision.Status.CONFIRMED if step in confirmations else CatalogFieldDecision.Status.NEEDS_REVIEW),
            candidate_type=row["source_type"], candidate_id=row["source_id"],
            confirmation_method=CatalogFieldDecision.ConfirmationMethod.CANDIDATE,
            provenance={**provenance, **(current.provenance if current else {}), "source": "assisted_form_save", "outcome": outcome,
                        "outcome_scope": outcome_scope, "selected_entity_id": str(row.get("selected_entity_id") or ""),
                        "suggested_value": proposed, "request_id": request_id,
                        "training_eligibility": "not_reviewed", "correctness": "not_evaluated"},
            evidence_summary=evidence, reason="建议填入后保存" if outcome == "used_unchanged" else "建议填入后经人工修改并保存",
        )
        assistance.append({"field": field, "candidate_type": row["source_type"], "candidate_id": str(row["source_id"]),
                           "selected_entity_id": str(row.get("selected_entity_id") or ""), "selected_label": row.get("selected_value", ""),
                           "decision_id": str(decision.pk), "original_value": before.get(field),
                           "suggested_value": proposed, "final_value": final, "outcome": outcome, "outcome_scope": outcome_scope})
    receipt = AuditEvent.objects.create(
        actor=actor, action="workspace.edits.saved", object_type="edition", object_id=str(edition.pk), request_id=request_id,
        before={"edit_version": expected_version},
        after={"request_fingerprint": fingerprint, "work_id": str(work_id), "sections": list(sections),
               "confirmed_sections": sorted(confirmations), "assistance": assistance,
               "training_eligibility": "not_reviewed", "correctness": "not_evaluated"},
    )
    return edition, receipt, False
