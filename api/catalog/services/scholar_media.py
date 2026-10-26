"""Scholar portrait selections over shared immutable media and editorial drafts."""
from hashlib import sha256
import json
from uuid import UUID

from django.db import transaction

from catalog.models import EditorialRevision, MediaRendition, Person, ScholarProfile
from catalog.services.media import RENDITION_WIDTHS, build_rendition, media_rendition_snapshot, protect_editorial_renditions


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




def portrait_media(person, *, selection=None, private=False):
    identifier = selection.get("rendition_id") if selection is not None else person.portrait_rendition_id
    if not identifier:
        return None
    primary = MediaRendition.objects.select_related("media").get(pk=identifier, kind="portrait")
    return media_rendition_snapshot(primary, lambda row: f"/api/catalog/admin/media/renditions/{row.pk}/file/" if private else f"/api/catalog/people/{person.pk}/portrait/?rendition={row.pk}")


def protect_portrait_references(revision, profile):
    identifiers = [profile.person.portrait_rendition_id, (revision.materialized_preview.get("portrait_selection") or {}).get("rendition_id")]
    for curation in (profile.curation, revision.materialized_preview.get("curation", {})):
        identifiers.extend(row["rendition_id"] for row in (curation or {}).get("biographical_materials", []))
    protect_editorial_renditions(revision, identifiers)


def validate_biographical_materials(value):
    """Keep an exact immutable media selection for each biographical image."""
    from rest_framework.exceptions import ValidationError

    if not isinstance(value, list) or len(value) > 100:
        raise ValidationError({"biographical_materials": "人物照片与生平资料最多100项。"})
    clean, seen, versions = [], set(), set()
    for row in value:
        if not isinstance(row, dict) or set(row) != {"id", "rendition_id", "caption"}:
            raise ValidationError({"biographical_materials": "每项资料须包含编号、图片版本和说明。"})
        try:
            identifier, rendition_id = str(UUID(str(row["id"]))), str(UUID(str(row["rendition_id"])))
        except (ValueError, TypeError, AttributeError) as error:
            raise ValidationError({"biographical_materials": "资料或图片版本编号无效。"}) from error
        if identifier in seen or rendition_id in versions or not isinstance(row["caption"], str) or len(row["caption"]) > 500:
            raise ValidationError({"biographical_materials": "同一图片版本不能重复添加，说明最多500字。"})
        seen.add(identifier)
        versions.add(rendition_id)
        clean.append({"id": identifier, "rendition_id": rendition_id, "caption": row["caption"].strip()})
    renditions = list(MediaRendition.objects.filter(pk__in=versions, kind="card"))
    if len(renditions) != len(versions) or any(not row.file.name or not row.file.storage.exists(row.file.name) for row in renditions):
        raise ValidationError({"biographical_materials": "所选资料图片不存在或不能读取，请重新选择。"})
    return clean


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


def save_scholar_editorial_patch(profile_id, patch, *, actor, change_note="更新学者草稿", request_key=""):
    from catalog.services.editorial_drafts import save_object_editorial_patch
    return save_object_editorial_patch("scholar_profile", profile_id, patch, actor=actor, change_note=change_note, request_key=request_key)


def select_scholar_portrait(profile_id, media_id, *, actor, expected_person_id, fingerprint=None):
    with transaction.atomic():
        variants = {width: build_rendition(media_id, kind="portrait", width=width) for width in RENDITION_WIDTHS} if media_id else {}
    return select_prepared_scholar_portrait(profile_id, variants.get(640), actor=actor, expected_person_id=expected_person_id, fingerprint=fingerprint)


def select_prepared_scholar_portrait(profile_id, primary, *, actor, expected_person_id, fingerprint):
    from catalog.services.editorial_revision import EditorialRevisionError

    with transaction.atomic():
        profile = ScholarProfile.objects.select_for_update().select_related("person").get(pk=profile_id)
        if profile.editorial_status == "archived" or profile.person.authority_status in {"merged", "rejected"}:
            raise EditorialRevisionError("学者或人物身份已经停用，请先恢复并核对身份，再修改肖像。")
        if str(expected_person_id) != str(profile.person_id):
            raise EditorialRevisionError("学者对应人物已变化，请重新打开学者页面。")
        if fingerprint is not None and fingerprint != portrait_selection_fingerprint(profile):
            raise EditorialRevisionError("肖像或学者草稿已变化，请重新读取后选择。")
        selection = portrait_selection(profile)
        selection["rendition_id"] = str(primary.pk) if primary else None
        # Clearing removes the old selection, never its original file.
        if not primary:
            selection["legacy_path"] = ""
        selection = validate_portrait_selection(profile, selection)
        return save_scholar_editorial_patch(profile.pk, {"portrait_selection": selection}, actor=actor, change_note="更新学者肖像，等待人工发布")
