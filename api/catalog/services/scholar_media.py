"""Scholar portrait selections over shared immutable media and editorial drafts."""
from copy import deepcopy
from hashlib import sha256
import json
from uuid import UUID, uuid4

from django.db import transaction

from catalog.models import CanonicalObjectRevision, EditorialRevision, EditorialRevisionMedia, MediaRendition, Person, ScholarProfile
from catalog.services.media import PUBLIC_METADATA_FIELDS, RENDITION_WIDTHS, build_rendition


def portrait_selection(profile):
    return {"person_id": str(profile.person_id), "rendition_id": str(profile.person.portrait_rendition_id) if profile.person.portrait_rendition_id else None,
            "legacy_path": profile.person.portrait.name or ""}


_READ_LATEST = object()


def portrait_selection_fingerprint(profile, *, draft=_READ_LATEST):
    latest = EditorialRevision.objects.filter(target_type="scholar_profile", target_id=profile.pk, status="draft").order_by("-revision").first() if draft is _READ_LATEST else draft
    value = {"canonical": portrait_selection(profile), "revision": str(latest.pk) if latest else None,
             "selection": latest.materialized_preview.get("portrait_selection") if latest else None}
    return sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def validate_portrait_selection(profile, value):
    from catalog.services.editorial_revision import EditorialRevisionError

    if not isinstance(value, dict) or set(value) != {"person_id", "rendition_id", "legacy_path"}:
        raise EditorialRevisionError("肖像选择必须包含人物、媒体版本和原图片路径。")
    if str(value["person_id"]) != str(profile.person_id):
        raise EditorialRevisionError("学者对应人物已变化，请重新选择肖像。")
    identifier = value["rendition_id"]
    if identifier is not None:
        try:
            identifier = str(UUID(str(identifier)))
        except (ValueError, TypeError, AttributeError) as error:
            raise EditorialRevisionError("肖像媒体版本编号无效。") from error
        rendition = MediaRendition.objects.filter(pk=identifier, kind="portrait").first()
        if rendition is None or not rendition.file.storage.exists(rendition.file.name):
            raise EditorialRevisionError("所选肖像媒体版本不存在或不能读取。")
    path = value["legacy_path"]
    if not isinstance(path, str) or path not in {"", profile.person.portrait.name or ""}:
        raise EditorialRevisionError("不能用任意文件路径替换学者肖像。")
    return {"person_id": str(profile.person_id), "rendition_id": identifier, "legacy_path": path}


def _portrait_variants(primary):
    if not primary:
        return []
    variants = list(primary.media.renditions.filter(group_key=primary.group_key, kind="portrait").order_by("requested_width")) if primary.group_key else [primary]
    by_width = {row.width: row for row in variants}
    by_width[primary.width] = primary
    return sorted(by_width.values(), key=lambda row: row.width)


def portrait_media(person, *, selection=None, private=False):
    identifier = selection.get("rendition_id") if selection is not None else person.portrait_rendition_id
    if not identifier:
        return None
    primary = MediaRendition.objects.select_related("media").get(pk=identifier, kind="portrait")
    return {"media_id": str(primary.media_id), "primary_rendition_id": str(primary.pk),
            **{field: primary.metadata_snapshot.get(field, "") for field in PUBLIC_METADATA_FIELDS},
            "renditions": [{"id": str(row.pk), "width": row.width, "height": row.height,
                            "url": f"/api/catalog/admin/media/renditions/{row.pk}/file/" if private else f"/api/catalog/people/{person.pk}/portrait/?rendition={row.pk}"}
                           for row in _portrait_variants(primary)]}


def protect_portrait_references(revision, profile):
    identifiers = {profile.person.portrait_rendition_id, (revision.materialized_preview.get("portrait_selection") or {}).get("rendition_id")}
    rows = {}
    for primary in MediaRendition.objects.select_related("media").filter(pk__in=[value for value in identifiers if value]):
        rows.update({row.pk: row for row in _portrait_variants(primary)})
    EditorialRevisionMedia.objects.bulk_create([
        EditorialRevisionMedia(editorial_revision=revision, rendition=row) for row in rows.values()
    ])


def apply_portrait_selection(profile, value, *, actor):
    from ingestion.models import AuditEvent

    person = Person.objects.select_for_update().get(pk=profile.person_id)
    profile.person = person
    selection = validate_portrait_selection(profile, value)
    before = portrait_selection(profile)
    person.portrait_rendition_id = selection["rendition_id"]
    person.portrait = selection["legacy_path"]
    person.save(update_fields=["portrait_rendition", "portrait", "updated_at"])
    AuditEvent.objects.create(actor=actor, action="scholar.portrait_publish", object_type="ScholarProfile", object_id=str(profile.pk), before=before, after=selection)


@transaction.atomic
def save_scholar_editorial_patch(profile_id, patch, *, actor, change_note="更新学者草稿", request_key=""):
    """Keep portrait and metadata edits in one current Scholar draft."""
    from catalog.services.editorial_revision import EditorialRevisionConflict, changed_editorial_patch, create_editorial_revision

    profile = ScholarProfile.objects.select_for_update().select_related("person").get(pk=profile_id)
    canonical, _ = CanonicalObjectRevision.objects.select_for_update().get_or_create(object_type="scholar_profile", object_id=profile.pk, defaults={"current_revision": 0})
    drafts = list(EditorialRevision.objects.select_for_update().filter(target_type="scholar_profile", target_id=profile.pk, status="draft").order_by("revision"))
    if any(row.base_revision != canonical.current_revision for row in drafts):
        raise EditorialRevisionConflict("正式学者资料已变化，请先处理旧草稿。")
    combined = {}
    for section in [*(row.patch for row in drafts), patch]:
        for field, value in section.items():
            combined[field] = {**combined.get(field, {}), **deepcopy(value)} if field == "person" else deepcopy(value)
    clean = changed_editorial_patch(target_type="scholar_profile", target=profile, patch=combined)
    if not clean:
        for row in drafts:
            row.status = "superseded"
            row.save(update_fields=["status", "updated_at"])
        return None
    if drafts and drafts[-1].patch == clean:
        return drafts[-1]
    revision = create_editorial_revision(target_type="scholar_profile", target_id=profile.pk, patch=clean, actor=actor,
                                         idempotency_key=request_key or f"scholar-edit:{uuid4()}", change_note=change_note)
    if revision.status != "draft":
        raise EditorialRevisionConflict("该请求对应的学者草稿已经结束，请重新核对。")
    for row in drafts:
        if row.pk != revision.pk:
            row.status = "superseded"
            row.save(update_fields=["status", "updated_at"])
    return revision


def select_scholar_portrait(profile_id, media_id, *, actor, expected_person_id, fingerprint=None):
    from catalog.services.editorial_revision import EditorialRevisionError

    with transaction.atomic():
        variants = {width: build_rendition(media_id, kind="portrait", width=width) for width in RENDITION_WIDTHS} if media_id else {}
    with transaction.atomic():
        profile = ScholarProfile.objects.select_for_update().select_related("person").get(pk=profile_id)
        if str(expected_person_id) != str(profile.person_id):
            raise EditorialRevisionError("学者对应人物已变化，请重新打开学者页面。")
        if fingerprint is not None and fingerprint != portrait_selection_fingerprint(profile):
            raise EditorialRevisionError("肖像或学者草稿已变化，请重新读取后选择。")
        selection = portrait_selection(profile)
        selection["rendition_id"] = str(variants[640].pk) if variants else None
        # Clearing removes the old selection, never its original file.
        if not variants:
            selection["legacy_path"] = ""
        return save_scholar_editorial_patch(profile.pk, {"portrait_selection": selection}, actor=actor, change_note="更新学者肖像，等待人工发布")
