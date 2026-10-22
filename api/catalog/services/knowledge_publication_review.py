"""Read-only M17 projection over existing knowledge previews and revision rules."""
from copy import copy
from uuid import UUID

from django.core.exceptions import ValidationError
from django.utils import timezone

from common.capabilities import Capability, has_capability
from catalog.models import CanonicalObjectRevision, EditorialRevision, KnowledgeNode, MediaRendition, ScholarProfile
from catalog.services.editorial_revision import (
    SPECIAL_FIELDS, TARGET_POLICIES, EditorialRevisionError,
    _validated_patch, _validate_knowledge_node_relations,
)
from catalog.services.knowledge_studio import KnowledgeObjectEditorAdapter, PUBLIC_MODULE_FIELDS


def knowledge_publication_review(*, object_type, object_id, payload, actor):
    target_type = KnowledgeObjectEditorAdapter.TARGET_TYPES.get(object_type)
    policy = TARGET_POLICIES.get(target_type)
    if policy is None or object_type == "work":
        raise ValueError("此对象请使用专门的发布检查页。")
    target = policy.model.objects.filter(pk=object_id).first()
    if target is None:
        return None
    draft = EditorialRevision.objects.filter(target_type=target_type, target_id=object_id, status="draft").order_by("-revision").first()
    canonical = CanonicalObjectRevision.objects.filter(object_type=target_type, object_id=object_id).values_list("current_revision", flat=True).first() or 0
    status_field = "editorial_status" if hasattr(target, "editorial_status") else "status"
    has_draft = draft is not None or getattr(target, status_field) != "published"
    # First publication uses the canonical editor; existing drafts retain their
    # exact status, including withdrawal. No target/revision is saved here.
    patch = dict(draft.patch or {}) if draft else {status_field: "published"}
    withdrawing = bool(draft and patch.get(status_field, getattr(target, status_field)) != "published")
    checks = []
    def add(code, severity, title, detail, section):
        checks.append(dict(code=code, severity=severity, title=title, detail=detail, section=section))
    if not has_capability(actor, Capability.PUBLISH_AUTHORITY):
        add("permission", "blocking", "当前账户没有发布权限", "可核对预览与内容，由有权限的编辑确认发布。", "publication")
    if draft and draft.base_revision != canonical:
        add("revision_conflict", "blocking", "正式版本已变化", "本草稿基于较早的正式内容，请返回版本记录处理冲突。", "versions")
    if not payload["perspective"].get("available"):
        add("preview_missing", "blocking", "已保存内容暂不能预览", "请返回编辑页核对对象身份与当前保存状态。", "identity")
    if isinstance(target, ScholarProfile) and not withdrawing:
        from catalog.services.scholar_publication import PUBLICATION_REVIEWABLE_STATUSES
        if target.person.authority_status not in PUBLICATION_REVIEWABLE_STATUSES:
            add("person_unavailable", "blocking", "人物身份需要处理", "权威记录已拒绝、合并或归档，请先处理身份再公开学者页面。", "identity")
    try:
        candidate = copy(target)
        candidate._state = copy(target._state)
        clean = _validated_patch(target_type, candidate, policy, patch)
        if isinstance(candidate, KnowledgeNode):
            _validate_knowledge_node_relations(candidate, clean)
        for name, value in clean.items():
            if name not in SPECIAL_FIELDS:
                field = candidate._meta.get_field(name)
                setattr(candidate, field.attname if field.many_to_one else name, field.clean(value, candidate))
        candidate.full_clean()
    except (EditorialRevisionError, ValidationError) as exc:
        detail = "；".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
        add("saved_content_invalid", "blocking", "保存内容需要修正", detail, "identity")
    unsupported = payload.get("content_completeness", {}).get("unsupported_preview_fields", [])
    if unsupported:
        add("partial_preview", "warning", "部分保存内容尚不能完整预览", "请返回编辑器核对这些内容：" + "、".join(unsupported), "content")

    if isinstance(target, ScholarProfile):
        from catalog.services.scholar_media import portrait_selection
        selection = patch.get("portrait_selection", portrait_selection(target))
    else:
        from catalog.services.knowledge_media import image_selection
        selection = patch.get("image_selection", image_selection(target))
    rendition_id = selection.get("rendition_id") if isinstance(selection, dict) else None
    if rendition_id:
        try:
            rendition_id = UUID(str(rendition_id))
        except (ValueError, TypeError, AttributeError):
            add("image_identity", "blocking", "图片版本标识无效", "请返回图片编辑重新选择。", "media")
            rendition_id = None
    if rendition_id:
        media = MediaRendition.objects.select_related("media").filter(pk=rendition_id).first()
        if media is None:
            add("image_missing", "blocking", "所选图片版本不存在", "请重新选择已有图片版本。", "media")
        else:
            try:
                if not media.file or not media.file.storage.exists(media.file.name):
                    add("image_file_missing", "blocking", "所选图片文件不可用", "媒体记录仍保留，请在图片编辑中检查原文件与所选版本。", "media")
            except OSError:
                add("image_storage_unavailable", "blocking", "暂时无法核对图片文件", "请先检查文件存储连接，再重新进行发布检查。", "media")
            # Public rendering uses immutable rendition metadata, not later
            # edits to MediaAsset. Inspect that same snapshot.
            metadata = media.metadata_snapshot or {}
            missing = []
            if not (metadata.get("source_label") or metadata.get("source_url")): missing.append("出处")
            if not (metadata.get("rights") or metadata.get("license")): missing.append("许可说明")
            if not metadata.get("credit"): missing.append("署名")
            if missing:
                add("image_rights", "warning", "图片来源信息待补充", "本次图片版本尚缺" + "、".join(missing) + "，请在图片编辑中核对并保存新版本。", "media")
    elif isinstance(selection, dict) and selection.get("legacy_path"):
        add("legacy_image", "warning", "旧图片的来源信息需人工核对", "当前图片没有可核对的媒体版本元数据，请在图片编辑中确认出处与使用权限。", "media")
    source_section = "publication" if object_type in {"discipline", "subdiscipline", "reading_path"} else "passages"
    add("source_review", "notice", "原文与关联内容需人工核对", "预览只展示原公开服务允许展示的资料。请核对引用、归因与使用权限；此检查未对全部原文进行自动授权审查。", source_section)

    before = payload["perspectives"]["published"].get("data") or {}
    after = payload["perspective"].get("data") or {}
    groups = list(PUBLIC_MODULE_FIELDS[object_type])
    covered = {name for _, names in groups for name in names}
    # Compare all remaining public fields too; never silently drop a change
    # merely because a newly added public field lacks a named module.
    remaining = sorted((set(before) | set(after)) - covered - {"id", "created_at", "updated_at"})
    groups.insert(0, ("页面基本信息", remaining))
    changes = []
    for index, (label, names) in enumerate(groups):
        left = {name: before[name] for name in names if name in before}
        right = {name: after[name] for name in names if name in after}
        changes.append({"key": str(index), "label": label, "before": left, "after": right,
                        "changed": left != right})
    blocking = sum(row["severity"] == "blocking" for row in checks)
    return {
        "checked_at": timezone.now(), "saved_at": draft.updated_at if draft else target.updated_at,
        "current_revision": canonical, "draft_revision_id": str(draft.pk) if draft else None,
        "has_draft": has_draft, "withdrawing": withdrawing,
        "actor_label": getattr(actor, "display_name", "") or actor.get_username(),
        "blocking_count": blocking, "warning_count": sum(row["severity"] == "warning" for row in checks),
        "can_publish": has_draft and not blocking, "checks": checks, "changes": changes,
    }
