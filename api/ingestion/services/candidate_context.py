"""Scoped compatibility reads while candidates move from intake to sessions."""

from django.db.models import Q

from catalog.models import CatalogingSession, Edition
from ingestion.models import UploadItem


def candidate_scope(candidate):
    if candidate.cataloging_session_id:
        return Q(cataloging_session_id=candidate.cataloging_session_id)
    if candidate.upload_item_id:
        return Q(cataloging_session__isnull=True, upload_item_id=candidate.upload_item_id)
    raise ValueError("候选缺少有效编目上下文。")


def candidate_decision_url(candidate):
    if candidate._meta.model_name == "metadatacandidate":
        if candidate.cataloging_session_id:
            return f"/catalog/admin/cataloging-sessions/{candidate.cataloging_session_id}/metadata/{candidate.pk}/decision/"
        return f"/ingestion/items/{candidate.upload_item_id}/metadata-candidates/{candidate.pk}/decision/"
    if candidate.cataloging_session_id:
        return f"/catalog/admin/cataloging-sessions/{candidate.cataloging_session_id}/candidates/{candidate.pk}/decision/"
    return f"/ingestion/items/{candidate.upload_item_id}/entity-resolution-candidates/{candidate.pk}/decision/"


def candidate_group_scope(candidate):
    scope = candidate_scope(candidate)
    if candidate.target_type == "person":
        role = (candidate.supporting_properties or {}).get("contribution_role") or "author"
        role_scope = Q(supporting_properties__contribution_role=role)
        if role == "author":
            role_scope |= (~Q(supporting_properties__has_key="contribution_role")
                           | Q(supporting_properties__contribution_role__isnull=True)
                           | Q(supporting_properties__contribution_role=""))
        scope &= role_scope
    return scope


def edition_candidate_scope(edition, item=None):
    scope = Q(cataloging_session__edition=edition, cataloging_session__status__in=["drafting", "reviewing", "ready", "publishing"])
    if item is not None:
        scope |= Q(cataloging_session__isnull=True, upload_item=item)
    return scope


def lock_candidate_context(candidate):
    """Lock Edition before the process row; retain the real upload for audit."""
    context_model = CatalogingSession if candidate.cataloging_session_id else UploadItem
    context_id = candidate.cataloging_session_id or candidate.upload_item_id
    context = context_model.objects.get(pk=context_id)
    edition = Edition.objects.select_for_update(of=("self",)).get(pk=context.edition_id) if context.edition_id else None
    locked = context_model.objects.select_for_update(of=("self",)).get(pk=context_id)
    if locked.edition_id != context.edition_id:
        raise ValueError("编目上下文已变化，请刷新后重试。")
    if isinstance(locked, CatalogingSession):
        if locked.status not in {"drafting", "reviewing", "ready"}:
            raise ValueError("该编目会话当前不能修改候选决定。")
        candidate.cataloging_session = locked
        if candidate.upload_item_id and candidate.upload_item.edition_id != locked.edition_id:
            raise ValueError("候选来源与编目会话不一致。")
    else:
        candidate.upload_item = locked
    locked.edition = edition
    return locked
