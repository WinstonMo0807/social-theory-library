"""Read-only source checks for legacy theory projections."""
from django.db.models import F

from catalog.models import Asset
from catalog.services.publication_eligibility import active_document_q
from catalog.services.semantic_search import viewer_access_statuses


def legacy_evidence_fields(record, context):
    fields = {
        "evidence_text": getattr(record, "evidence_text", ""),
        "evidence_page": getattr(record, "evidence_page", None),
        "evidence_printed_label": getattr(record, "evidence_printed_label", ""),
    }
    # This is a server-owned preview context, never a public query parameter.
    # The dedicated Admin serializers continue to preserve the original data.
    if context.get("include_unpublished_items"):
        return fields
    hidden = {"evidence_text": "", "evidence_page": None, "evidence_printed_label": ""}
    asset_id = getattr(record, "evidence_asset_id", None)
    page = fields["evidence_page"]
    if not asset_id or isinstance(page, bool) or not isinstance(page, int) or page < 1:
        # Hierarchy records have no exact file identity. Do not publish their
        # unlocatable evidence text, including text left by a SET_NULL deletion.
        return hidden
    user = getattr(context.get("request"), "user", None)
    authenticated = bool(user and getattr(user, "is_authenticated", False))
    statuses = viewer_access_statuses(
        authenticated=authenticated,
        staff=authenticated and (
            getattr(user, "is_staff", False)
            or getattr(user, "role", "") in {"admin", "editor", "reviewer"}
        ),
    )
    evidence_work_id = getattr(record, "evidence_work_id", None)
    key = (asset_id, page, evidence_work_id, tuple(statuses))
    cache = context.setdefault("_legacy_theory_evidence", {})
    if key not in cache:
        sources = Asset.objects.filter(
            active_document_q(asset_prefix=""),
            pk=asset_id,
            edition__active_catalog_revision__document_revision__asset_id=F("pk"),
            kind=Asset.Kind.NORMALIZED,
            status=Asset.Status.READY,
            validation_status=Asset.ValidationStatus.VALID,
            access_status__in=statuses,
            page_count__gte=page,
            pages__index=page,
        ).exclude(file="")
        if evidence_work_id:
            sources = sources.filter(edition__work_id=evidence_work_id)
        cache[key] = sources.exists()
    return fields if cache[key] else hidden
