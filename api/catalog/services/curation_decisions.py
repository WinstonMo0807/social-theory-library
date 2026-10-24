"""Saved field state for recoverable decisions over existing editorial targets."""
from catalog.editorial_read import current_editorial_version
from catalog.models import CuratedClaim
from catalog.services.field_enrichment.targets import current_field_value
from catalog.services.workspace_edits import _digest


def decision_version(target_type, target, field_name):
    version_type, version_id = target_type, target.pk
    if target_type == "person" and getattr(target, "scholar_profile", None):
        version_type, version_id = "scholar_profile", target.scholar_profile.pk
    value = current_field_value(target_type, target, field_name)
    if target_type == "work" and field_name in CuratedClaim.Kind.values:
        value = list(CuratedClaim.objects.filter(work=target, kind=field_name).order_by("pk")
                     .values("id", "status", "updated_at"))
    return _digest({"type": target_type, "id": target.pk, "field": field_name,
        "updated_at": target.updated_at, "version": current_editorial_version(version_type, version_id),
        "current": value})
