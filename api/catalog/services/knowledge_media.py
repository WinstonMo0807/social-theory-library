"""Knowledge-node and reading-path images use shared media and editorial drafts."""
from hashlib import sha256
import json
from uuid import UUID

from django.db import transaction

from catalog.models import Discipline, Subdiscipline, EditorialRevision, KnowledgeNode, MediaRendition, ReadingPath
from catalog.services.editorial_drafts import save_object_editorial_patch
from catalog.services.media import RENDITION_WIDTHS, build_rendition, media_rendition_snapshot, protect_editorial_renditions

TARGETS = {"knowledge_node": KnowledgeNode, "reading_path": ReadingPath, "discipline": Discipline, "subdiscipline": Subdiscipline}


def image_fields(target):
    return ("hero_rendition", "hero_image") if isinstance(target, (Discipline, Subdiscipline)) else ("cover_rendition", "cover_asset")


def image_legacy_file(target):
    return getattr(target, image_fields(target)[1])


def image_status(target):
    return getattr(target, "editorial_status", getattr(target, "status", ""))


def image_target_type(target):
    return next(name for name, model in TARGETS.items() if isinstance(target, model))


def image_selection(target):
    identifier = getattr(target, f"{image_fields(target)[0]}_id")
    return {"object_type": image_target_type(target), "object_id": str(target.pk),
            "rendition_id": str(identifier) if identifier else None, "legacy_path": image_legacy_file(target).name or ""}


def image_fingerprint(target, draft):
    state = {"canonical": image_selection(target), "status": image_status(target),
             "draft": str(draft.pk) if draft else None, "selection": draft.materialized_preview.get("image_selection") if draft else None}
    return sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


def validate_image_selection(target, value):
    from catalog.services.editorial_revision import EditorialRevisionError

    if not isinstance(value, dict) or set(value) != {"object_type", "object_id", "rendition_id", "legacy_path"}:
        raise EditorialRevisionError("图片选择缺少完整对象信息。")
    if value["object_type"] != image_target_type(target) or value["object_id"] != str(target.pk):
        raise EditorialRevisionError("图片不属于当前编辑对象。")
    identifier = value["rendition_id"]
    if identifier is not None:
        try:
            identifier = str(UUID(str(identifier)))
        except (ValueError, TypeError, AttributeError) as error:
            raise EditorialRevisionError("图片版本编号无效。") from error
        rendition = MediaRendition.objects.filter(pk=identifier, kind="hero").first()
        if rendition is None or not rendition.file.storage.exists(rendition.file.name):
            raise EditorialRevisionError("所选横幅图片不存在或不能读取。")
    path = value["legacy_path"]
    if not isinstance(path, str) or path not in {"", image_legacy_file(target).name or ""}:
        raise EditorialRevisionError("不能使用任意路径替换图片。")
    return {**value, "rendition_id": identifier}


def image_media(target, *, selection=None, private=False):
    identifier = selection["rendition_id"] if selection is not None else image_selection(target)["rendition_id"]
    if not identifier:
        return None
    primary = MediaRendition.objects.select_related("media").get(pk=identifier, kind="hero")
    object_type = image_target_type(target)
    return media_rendition_snapshot(primary, lambda row: f"/api/catalog/admin/media/renditions/{row.pk}/file/" if private else f"/api/catalog/knowledge-media/{object_type}/{target.pk}/file/?rendition={row.pk}")


def protect_image_references(revision, target):
    identifiers = [image_selection(target)["rendition_id"], (revision.materialized_preview.get("image_selection") or {}).get("rendition_id")]
    protect_editorial_renditions(revision, identifiers)


def apply_image_selection(target, value, *, actor):
    from ingestion.models import AuditEvent

    before = image_selection(target)
    value = validate_image_selection(target, value)
    rendition_field, file_field = image_fields(target)
    setattr(target, f"{rendition_field}_id", value["rendition_id"])
    setattr(target, file_field, value["legacy_path"])
    target.save(update_fields=[rendition_field, file_field, "updated_at"])
    AuditEvent.objects.create(actor=actor, action="knowledge.image_publish", object_type=image_target_type(target), object_id=str(target.pk), before=before, after=value)


def select_knowledge_image(object_type, object_id, media_id, *, actor, fingerprint):
    from catalog.services.editorial_revision import EditorialRevisionError

    model = TARGETS[object_type]
    with transaction.atomic():
        variants = {width: build_rendition(media_id, width=width, kind="hero") for width in RENDITION_WIDTHS} if media_id else {}
    with transaction.atomic():
        target = model.objects.select_for_update().get(pk=object_id)
        draft = EditorialRevision.objects.filter(target_type=object_type, target_id=target.pk, status="draft").order_by("-revision").first()
        if fingerprint != image_fingerprint(target, draft):
            raise EditorialRevisionError("对象或图片草稿已变化，请重新读取后选择。")
        selection = image_selection(target)
        selection["rendition_id"] = str(variants[640].pk) if variants else None
        if not variants:
            selection["legacy_path"] = ""
        return save_object_editorial_patch(object_type, target.pk, {"image_selection": selection}, actor=actor, change_note="更新页面图片，等待人工发布")


def stage_legacy_image_upload(target, uploaded, *, actor):
    from catalog.services.media import ingest_image

    object_type = image_target_type(target)
    draft = EditorialRevision.objects.filter(target_type=object_type, target_id=target.pk, status="draft").order_by("-revision").first()
    fingerprint = image_fingerprint(target, draft)
    media, _ = ingest_image(uploaded, actor=actor)
    return select_knowledge_image(object_type, target.pk, media.pk, actor=actor, fingerprint=fingerprint)
