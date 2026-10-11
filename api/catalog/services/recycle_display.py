"""Retained row metadata and images, accessed through an active recycle entry."""
from copy import copy

from django.apps import apps

from catalog.models import Edition, EditorialRevision, MediaRendition, Person, ScholarProfile, Work
from catalog.services.recycle_preview import recycle_entry_data


def _rendition_file(identifier):
    rendition = MediaRendition.objects.filter(pk=identifier).first() if identifier else None
    return rendition.file if rendition else None


def _selected_file(selection, legacy):
    if selection.get("rendition_id"):
        image = _rendition_file(selection["rendition_id"])
        return image, "" if image else "草稿所选图片版本无法读取，请回到编辑区检查。"
    path = selection.get("legacy_path") or ""
    if not path:
        return None, ""
    if path == legacy.name:
        return legacy, ""
    return None, "草稿所选原图片与当前保留文件不符，请回到编辑区检查。"


def retained_display_source(entry):
    model = apps.get_model(entry.model_label)
    obj = model.all_objects.filter(pk=entry.object_id).first()
    if obj is None:
        return None, "", "保留对象无法读取，请检查对应管理记录。"
    work = obj if isinstance(obj, Work) else Work.all_objects.filter(pk=obj.work_id).first() if isinstance(obj, Edition) else None
    edition = obj if isinstance(obj, Edition) else None
    if entry.model_label == "ingestion.uploaditem" and obj.edition_id:
        edition = Edition.all_objects.filter(pk=obj.edition_id).first()
        work = Work.all_objects.filter(pk=edition.work_id).first() if edition else None
    if work:
        edition = edition or Edition.all_objects.filter(work_id=work.pk).order_by("-is_primary", "-created_at", "pk").first()
        details = []
        if edition:
            names = list(edition.contributions.filter(role="author", approved=True).order_by("order", "pk").values_list("person__preferred_name", flat=True)[:8])
            details = ["、".join(names), f"{edition.publication_year}年版" if edition.publication_year else "", edition.publisher]
        subtitle = " · ".join(str(value) for value in details if value)
        from catalog.services.publication_commands import editorial_draft_applies_to_edition
        revision = EditorialRevision.objects.filter(target_type="work", target_id=work.pk, status="draft").order_by("-revision").first()
        if edition and editorial_draft_applies_to_edition(revision, edition):
            saved = revision.materialized_preview or {}
            if "cover_rendition" in saved or "cover" in saved:
                identifier = saved.get("cover_rendition", work.cover_rendition_id)
                if identifier:
                    image = _rendition_file(identifier)
                    return image, subtitle, "" if image else "草稿所选封面版本无法读取，请回到编辑区检查。"
                image = copy(work.cover)
                image.name = saved.get("cover", work.cover.name) or ""
                return image, subtitle, ""
        return _rendition_file(work.cover_rendition_id) or work.cover, subtitle, ""
    if isinstance(obj, (ScholarProfile, Person)):
        person = obj.person if isinstance(obj, ScholarProfile) else obj
        identifier = person.portrait_rendition_id
        if isinstance(obj, ScholarProfile):
            revision = EditorialRevision.objects.filter(target_type="scholar_profile", target_id=obj.pk, status="draft").order_by("-revision").first()
            selection = (revision.materialized_preview or {}).get("portrait_selection") if revision else None
            if selection is not None:
                if selection.get("person_id") != str(person.pk):
                    return None, person.original_name, "草稿肖像所属人物与当前记录不符，请回到编辑区检查。"
                image, warning = _selected_file(selection, person.portrait)
                return image, person.original_name, warning
        return _rendition_file(identifier) or person.portrait, person.original_name, ""
    if entry.model_label == "catalog.recommendationissue":
        from catalog.services.editorial_issues import issue_draft_payload
        payload = issue_draft_payload(obj)
        return _rendition_file(payload.get("cover_rendition_id")), str(payload.get("public_byline") or ""), ""
    from catalog.services.knowledge_media import TARGETS, image_fields
    object_type = next((name for name, target_model in TARGETS.items() if isinstance(obj, target_model)), None)
    subtitle = str(getattr(obj, "canonical_name_en", "") or getattr(obj, "foreign_name", "") or "")
    if object_type:
        revision = EditorialRevision.objects.filter(target_type=object_type, target_id=obj.pk, status="draft").order_by("-revision").first()
        selection = (revision.materialized_preview or {}).get("image_selection") if revision else None
        if selection is not None:
            if selection.get("object_type") != object_type or selection.get("object_id") != str(obj.pk):
                return None, subtitle, "草稿图片所属对象与当前记录不符，请回到编辑区检查。"
            image, warning = _selected_file(selection, getattr(obj, image_fields(obj)[1]))
            return image, subtitle, warning
    # Records without a saved image selection retain their canonical image.
    for relation, field in [("hero_rendition_id", "hero_image"), ("cover_rendition_id", "cover_asset")]:
        if hasattr(obj, field):
            return _rendition_file(getattr(obj, relation, None)) or getattr(obj, field), subtitle, ""
    return None, "", ""


def recycle_display_data(entry):
    image, subtitle, warning = retained_display_source(entry)
    return {**recycle_entry_data(entry), "thumbnail_url": f"/api/catalog/admin/recycle/{entry.pk}/image/" if image else "",
            "subtitle": subtitle, "display_warning": warning}
