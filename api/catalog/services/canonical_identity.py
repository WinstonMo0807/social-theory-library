from __future__ import annotations

from catalog.models import (
    Concept,
    KnowledgeNode,
    LegacyKnowledgeMapping,
    TheorySchool,
    WorkNodeRelation,
)


LEGACY_NODE_MODELS = frozenset({"TheorySchool", "Concept"})
EXPECTED_NODE_TYPE_BY_LEGACY_MODEL = {
    "TheorySchool": KnowledgeNode.NodeType.THEORY_TRADITION,
    "Concept": KnowledgeNode.NodeType.CONCEPT,
}
INDEPENDENT_IDENTITY_NODE_TYPES = frozenset(
    {
        KnowledgeNode.NodeType.DISCIPLINE,
        KnowledgeNode.NodeType.SUBDISCIPLINE,
        KnowledgeNode.NodeType.TOPIC,
    }
)
LEGACY_WORK_ROLE_MAP = {
    "foundational": WorkNodeRelation.Role.FOUNDATIONAL,
    "development": WorkNodeRelation.Role.THEORETICAL_DEVELOPMENT,
    "introduction": WorkNodeRelation.Role.SYSTEMATIC_EXPOSITION,
    "empirical_application": WorkNodeRelation.Role.EMPIRICAL_APPLICATION,
    "method_use": WorkNodeRelation.Role.EMPIRICAL_APPLICATION,
    "criticism": WorkNodeRelation.Role.CRITIQUE,
    "theory_history": WorkNodeRelation.Role.SYSTEMATIC_EXPOSITION,
    "local_mention": WorkNodeRelation.Role.GENERAL_MENTION,
    "": WorkNodeRelation.Role.GENERAL_MENTION,
}


class CanonicalIdentityError(ValueError):
    pass


def _normalized_identity(value: object) -> str:
    return "".join(
        character
        for character in str(value or "").casefold()
        if character.isalnum()
    )


def legacy_mapping_safety(mapping: LegacyKnowledgeMapping) -> tuple[bool, str]:
    """Return whether a legacy mapping is safe for canonical writes/backfill."""

    expected_type = EXPECTED_NODE_TYPE_BY_LEGACY_MODEL.get(mapping.legacy_model)
    if not expected_type:
        return False, "unsupported_legacy_model"
    if mapping.node.node_type != expected_type:
        return False, "node_type_mismatch"
    if mapping.node.status != "published":
        return False, "target_not_published"
    model = {"TheorySchool": TheorySchool, "Concept": Concept}[mapping.legacy_model]
    legacy = model.objects.filter(pk=mapping.legacy_id).only("name").first()
    if legacy is None:
        return False, "legacy_target_missing"
    legacy_identity = _normalized_identity(legacy.name)
    accepted = {
        _normalized_identity(mapping.node.canonical_name_zh),
        _normalized_identity(mapping.node.canonical_name_en),
    }
    accepted.update(
        _normalized_identity(value)
        for value in mapping.node.aliases.filter(is_verified=True).values_list(
            "alias",
            flat=True,
        )
    )
    accepted.discard("")
    if not legacy_identity or legacy_identity not in accepted:
        return False, "identity_mismatch"
    return True, "ready"


def mapped_node_for_legacy(legacy_model: str, legacy_id) -> KnowledgeNode:
    """Resolve an explicitly reviewed legacy mapping without guessing identity."""

    if legacy_model not in LEGACY_NODE_MODELS:
        raise CanonicalIdentityError(f"{legacy_model} 不是 3.0 兼容映射对象。")
    mapping = (
        LegacyKnowledgeMapping.objects.select_related("node")
        .filter(
            legacy_model=legacy_model,
            legacy_id=legacy_id,
            migration_status=LegacyKnowledgeMapping.MigrationStatus.MAPPED,
        )
        .first()
    )
    if mapping is None:
        raise CanonicalIdentityError("旧知识对象尚未建立人工确认的规范映射。")
    safe, reason = legacy_mapping_safety(mapping)
    if reason == "node_type_mismatch":
        expected_type = EXPECTED_NODE_TYPE_BY_LEGACY_MODEL[legacy_model]
        raise CanonicalIdentityError(
            f"旧知识对象的规范映射类型错误，预期 {expected_type}，"
            f"实际为 {mapping.node.node_type}。"
        )
    if not safe:
        raise CanonicalIdentityError(
            "旧知识对象的规范映射尚未达到自动写入条件，"
            f"需要人工核验身份与发布状态（{reason}）。"
        )
    return mapping.node


def validate_canonical_node_type(node_type: str) -> None:
    if node_type in INDEPENDENT_IDENTITY_NODE_TYPES:
        raise CanonicalIdentityError(
            "学科、子学科和主题继续使用独立规范身份，不能新建同名 KnowledgeNode。"
        )


def canonical_work_node_role(legacy_role: str) -> str:
    return LEGACY_WORK_ROLE_MAP.get(legacy_role, WorkNodeRelation.Role.GENERAL_MENTION)
