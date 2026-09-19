"""Record a suggestion only when an explicit knowledge form save retains it.

The normal editor owns the write. Candidate evidence, age, identity and context
checks are shared with the existing decision service; no second draft is made.
"""
from uuid import UUID

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from catalog.models import EnrichmentCandidate, ResearchRun
from catalog.services.field_enrichment.mutations import (
    FIELD_MUTATIONS, _create_revision_for_published_target,
    _record_direct_canonical_change, _research_context_stale_reason, _validate_evidence,
)
from catalog.services.field_enrichment.policies import FIELD_POLICIES
from catalog.services.field_enrichment.targets import current_field_value, get_target
from catalog.services.field_enrichment.values import normalize_candidate_value, stable_json
from common.permissions import CanReviewCandidate
from ingestion.models import AuditEvent


FIELDS = {
    ("knowledge_node", "alias"): ("aliases", "alias", "alias"),
    ("knowledge_node", "discipline"): ("discipline_links", "discipline_id", "discipline_id"),
    ("knowledge_node", "subdiscipline"): ("subdiscipline_links", "subdiscipline_id", "subdiscipline_node_id"),
    ("person", "name_variant"): ("aliases", None, "name"),
    ("person", "affiliation"): ("affiliations", None, "name"),
    ("reading_path", "item"): ("stage_groups", None, "work_id"),
}


def prepare_editorial_prefills(request, view, target):
    ids = request.data.get("assisted_candidates", [])
    if not ids:
        return []
    if not isinstance(ids, list) or len(ids) > 32:
        raise ValidationError({"assisted_candidates": "一次最多保存32项填写建议。"})
    if not CanReviewCandidate().has_permission(request, view):
        raise PermissionDenied("当前账户没有采用建议的权限，未保存任何修改。")
    try:
        ids = list(dict.fromkeys(UUID(str(value)) for value in ids))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError({"assisted_candidates": "建议编号无效，请重新选择。"})
    previews = list(EnrichmentCandidate.objects.filter(pk__in=ids).order_by("id"))
    if len(previews) != len(ids):
        raise ValidationError({"assisted_candidates": "部分建议已不存在，请重新读取。"})
    run_ids = {(row.request_context or {}).get("research_run_id") for row in previews} - {None, ""}
    runs = {str(run.pk): run for run in ResearchRun.objects.select_for_update(of=("self",), nowait=True).filter(pk__in=run_ids).order_by("id")}
    candidates = list(EnrichmentCandidate.objects.select_for_update(nowait=True).filter(pk__in=ids).order_by("id"))
    prepared = []
    decisions = request.data.get("assisted_candidate_decisions", {})
    if not isinstance(decisions, dict) or any(value not in {"modified", "removed"} for value in decisions.values()):
        raise ValidationError({"assisted_candidate_decisions": "建议处理方式无效。"})
    for candidate in candidates:
        person = view.editorial_target_type == "scholar_profile"
        kind = "person" if person else view.editorial_target_type
        target_id = target.person_id if person else target.pk
        field = FIELDS.get((kind, candidate.field_name))
        if candidate.target_type != kind or candidate.target_id != target_id or field is None:
            raise ValidationError({"assisted_candidates": "建议不属于当前对象或不适用于此表单。"})
        form_key, row_key, candidate_key = field
        if form_key not in request.data:
            raise ValidationError({"assisted_candidates": "填写建议缺少对应表单内容。"})
        if candidate.status == EnrichmentCandidate.Status.ACCEPTED:
            continue
        try:
            policy = FIELD_POLICIES.get(kind, candidate.field_name)
            value = normalize_candidate_value(policy.mutation_adapter, candidate.proposed_value)
        except ValueError as error:
            raise ValidationError({"assisted_candidates": str(error)}) from error
        proposed = value.get(candidate_key, value.get("alias", "")) if isinstance(value, dict) else value
        final = request.data[form_key]
        if not isinstance(final, list):
            raise ValidationError({form_key: "请保留该字段的列表格式。"})
        if (kind, candidate.field_name) == ("knowledge_node", "discipline") and request.data.get("primary_discipline"):
            final = [*final, {"discipline_id": request.data["primary_discipline"], "relation_type": "primary"}]
        retained = any(str(row.get(row_key, "") if isinstance(row, dict) and row_key else row).strip() == str(proposed).strip() for row in final)
        if kind == "reading_path":
            retained = any(
                str(item.get("work") or "") == str(value.get("work_id") or "")
                and str(item.get("node") or "") == str(value.get("node_id") or "")
                for stage in final if isinstance(stage, dict)
                for item in stage.get("items", []) if isinstance(item, dict)
            )
        obj = get_target(kind, target_id, for_update=True)
        outcome = "accepted" if retained else decisions.get(str(candidate.pk), "changed_or_removed")
        if not retained and outcome != "modified":
            # A suggestion removed from the form must not block a manual save
            # merely because its source expired in the meantime.
            prepared.append((candidate, obj, value, form_key, final, False, outcome))
            continue
        if candidate.status != EnrichmentCandidate.Status.PENDING:
            raise ValidationError({"assisted_candidates": "这项建议已经处理，请重新读取后保存。"})
        try:
            if candidate.candidate_kind != policy.candidate_kind or candidate.policy_version != policy.policy_version:
                raise ValueError("建议规则已变化，请重新查找。")
            if candidate.refresh_after and candidate.refresh_after < timezone.now():
                raise ValueError("建议来源已过期，请重新查找。")
            if candidate.identity_status not in {EnrichmentCandidate.IdentityStatus.CONFIRMED, EnrichmentCandidate.IdentityStatus.NOT_REQUIRED}:
                raise ValueError("请先确认建议对应的人物或资料身份。")
            run_id = str((candidate.request_context or {}).get("research_run_id") or "")
            stale = _research_context_stale_reason(candidate, runs.get(run_id))
            if stale:
                raise ValueError(f"建议已经过期：{stale}")
            _validate_evidence(candidate, policy)
            if getattr(obj, "editorial_status", getattr(obj, "authority_status", getattr(obj, "status", ""))) in {"archived", "merged", "rejected"}:
                raise ValueError("当前资料已下线、合并或拒绝，不能继续采用建议。")
            if stable_json(current_field_value(kind, obj, candidate.field_name)) != stable_json(candidate.current_value):
                raise ValueError("资料已在建议生成后改变，请核对最新建议。")
        except ValueError as error:
            raise ValidationError({"assisted_candidates": str(error)}) from error
        # Removed/rewritten suggestions are not automatically called accepted.
        prepared.append((candidate, obj, value, form_key, final, retained, outcome))
    return prepared


def apply_editorial_prefill_details(prepared, *, actor):
    """Preserve structured name provenance beyond the form's plain alias list.

    Called inside the editor transaction, after its normal save. Published
    identities still go through the existing editorial revision service.
    """
    results = {}
    for candidate, target, value, _field, _final, retained, _outcome in prepared:
        if not retained or (candidate.target_type, candidate.field_name) != ("person", "name_variant"):
            continue
        target.refresh_from_db()
        try:
            result = _create_revision_for_published_target(
                candidate=candidate, target=target, value=value, actor=actor,
                reason="管理员将别名建议填入本页并保存，同时保留名称语言、类型和来源。",
            )
            if result is None:
                result = FIELD_MUTATIONS.mutate("person_name_variant", target=target, value=value, candidate=candidate, actor=actor)
                _record_direct_canonical_change(candidate=candidate, target=target, result=result, actor=actor)
        except ValueError as error:
            raise ValidationError({"assisted_candidates": str(error)}) from error
        results[candidate.pk] = result
    return results


def record_editorial_prefills(prepared, *, actor, response, details):
    for candidate, target, value, field, final, retained, outcome in prepared:
        revision = response.get("editorial_revision") or {}
        revision_id = revision.get("id") if isinstance(revision, dict) else None
        if retained or outcome == "modified":
            candidate.status = EnrichmentCandidate.Status.ACCEPTED
            candidate.reviewed_by = actor
            candidate.reviewed_at = timezone.now()
            candidate.review_reason = "管理员确认修改建议后使用，并显式保存最终填写。" if outcome == "modified" else "建议填入表单后，由管理员显式保存。"
            candidate.normalized_value = value
            detail = details.get(candidate.pk)
            candidate.accepted_authority_model = "catalog.EditorialRevision" if revision_id else detail.authority_model if detail else target._meta.label
            candidate.accepted_authority_id = revision_id or (detail.authority_id if detail else target.pk)
            candidate.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_reason", "normalized_value", "accepted_authority_model", "accepted_authority_id", "updated_at"])
        action = "accept_field_enrichment_candidate" if retained else "field_prefill_modified_adoption" if outcome == "modified" else "field_prefill_removed" if outcome == "removed" else "field_prefill_removed_or_edited"
        AuditEvent.objects.create(
            actor=actor, action=action,
            object_type="catalog.EnrichmentCandidate", object_id=str(candidate.pk), request_id=str(candidate.request_id),
            before={"value": candidate.current_value, "suggestion": candidate.proposed_value},
            after={"status": candidate.status, "saved_field": field, "final_value": final,
                   "authority_model": candidate.accepted_authority_model, "authority_id": str(candidate.accepted_authority_id or ""),
                   "mode": "explicit_form_save", "retained": retained, "outcome": outcome},
        )
