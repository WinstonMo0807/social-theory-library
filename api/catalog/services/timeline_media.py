"""Exact evidence pictures share the media library, original event and revisions."""
from uuid import UUID

from django.db import transaction
from rest_framework.exceptions import ValidationError

from catalog.models import MediaRendition, TimelineEvidenceImage
from catalog.services.media import media_rendition_snapshot, protect_editorial_renditions


def evidence_image_choices(details):
    details = details or {}
    choices = {"primary": details.get("primary_image_rendition_id")}
    choices.update({row["id"]: row.get("image_rendition_id") for row in details.get("sources", [])})
    return {key: value for key, value in choices.items() if value}


def validate_evidence_images(details):
    rows = [(details, "primary_image_rendition_id"), *[(row, "image_rendition_id") for row in details.get("sources", [])]]
    for row, name in rows:
        value = row.get(name)
        try:
            row[name] = str(UUID(str(value))) if value is not None else None
        except (ValueError, TypeError, AttributeError):
            raise ValidationError("出处图片须选择媒体库中的准确图片版本。") from None
    identifiers = set(evidence_image_choices(details).values())
    renditions = list(MediaRendition.objects.filter(pk__in=identifiers, kind="hero"))
    if len(renditions) != len(identifiers) or any(not row.file.storage.exists(row.file.name) for row in renditions):
        raise ValidationError("出处图片已不可用，请重新选择或明确移除该图片。")
    return details


@transaction.atomic
def sync_evidence_images(event):
    """Canonical drafts also need PROTECT references, before any first revision."""
    choices = evidence_image_choices(event.editorial_details)
    existing = {row.source_key: row for row in event.evidence_images.select_for_update()}
    for key, identifier in choices.items():
        if key not in existing or str(existing[key].rendition_id) != identifier:
            TimelineEvidenceImage.objects.update_or_create(event=event, source_key=key, defaults={"rendition_id": identifier})
    event.evidence_images.exclude(source_key__in=choices).delete()


def protect_evidence_images(revision, target):
    identifiers = [*evidence_image_choices(target.editorial_details).values(),
                   *evidence_image_choices(revision.materialized_preview.get("editorial_details")).values()]
    protect_editorial_renditions(revision, identifiers)


def prepare_primary_images(events, context):
    identifiers = {(event.editorial_details or {}).get("primary_image_rendition_id") for event in events} - {None, ""}
    primary = list(MediaRendition.objects.select_related("media").filter(pk__in=identifiers, kind="hero"))
    groups = {}
    for row in MediaRendition.objects.filter(media_id__in={row.media_id for row in primary}, group_key__in={row.group_key for row in primary if row.group_key}, kind="hero").order_by("requested_width"):
        groups.setdefault((row.media_id, row.group_key), {})[row.width] = row
    cache = context.setdefault("_timeline_primary_images", {})
    for row in primary:
        variants = dict(groups.get((row.media_id, row.group_key), {}))
        variants[row.width] = row
        cache[str(row.pk)] = (row, sorted(variants.values(), key=lambda item: item.width))


def primary_image_media(event, context=None):
    identifier = (event.editorial_details or {}).get("primary_image_rendition_id")
    if not identifier:
        return None
    if context is not None:
        primary, variants = context.get("_timeline_primary_images", {}).get(identifier, (None, None))
    else:
        primary = MediaRendition.objects.select_related("media").filter(pk=identifier, kind="hero").first()
        variants = None
    if primary is None:
        return None
    return media_rendition_snapshot(primary, lambda row: f"/api/catalog/theory-system/timeline/{event.pk}/image/?rendition={row.pk}", variants=variants)
