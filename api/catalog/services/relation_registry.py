from __future__ import annotations

from dataclasses import asdict, dataclass

from catalog.models import KnowledgeRelation


@dataclass(frozen=True, slots=True)
class RelationPolicy:
    predicate: str
    allowed_subject_types: tuple[str, ...]
    allowed_object_types: tuple[str, ...]
    directed: bool
    symmetric: bool = False
    inverse_predicate: str = ""
    requires_evidence: bool = True
    requires_review: bool = True
    allow_duplicates: bool = False
    hierarchical: bool = False

    def serialize(self) -> dict:
        value = asdict(self)
        value["allowed_subject_types"] = list(self.allowed_subject_types)
        value["allowed_object_types"] = list(self.allowed_object_types)
        return value


_NODE_TYPES = tuple(value for value, _label in KnowledgeRelation._meta.get_field("source_node").related_model.NodeType.choices)


RELATION_POLICIES = {
    KnowledgeRelation.RelationType.INHERITED_FROM: RelationPolicy(
        predicate=KnowledgeRelation.RelationType.INHERITED_FROM,
        allowed_subject_types=_NODE_TYPES,
        allowed_object_types=_NODE_TYPES,
        directed=True,
        inverse_predicate="develops_into",
        hierarchical=True,
    ),
    KnowledgeRelation.RelationType.REVISES: RelationPolicy(
        predicate=KnowledgeRelation.RelationType.REVISES,
        allowed_subject_types=_NODE_TYPES,
        allowed_object_types=_NODE_TYPES,
        directed=True,
        inverse_predicate="revised_by",
    ),
    KnowledgeRelation.RelationType.EXTENDS: RelationPolicy(
        predicate=KnowledgeRelation.RelationType.EXTENDS,
        allowed_subject_types=_NODE_TYPES,
        allowed_object_types=_NODE_TYPES,
        directed=True,
        inverse_predicate="extended_by",
    ),
    KnowledgeRelation.RelationType.CRITICIZES: RelationPolicy(
        predicate=KnowledgeRelation.RelationType.CRITICIZES,
        allowed_subject_types=_NODE_TYPES,
        allowed_object_types=_NODE_TYPES,
        directed=True,
        inverse_predicate="criticized_by",
    ),
    KnowledgeRelation.RelationType.RESPONDS_TO: RelationPolicy(
        predicate=KnowledgeRelation.RelationType.RESPONDS_TO,
        allowed_subject_types=_NODE_TYPES,
        allowed_object_types=_NODE_TYPES,
        directed=True,
        inverse_predicate="receives_response_from",
    ),
    KnowledgeRelation.RelationType.COMPETES_WITH: RelationPolicy(
        predicate=KnowledgeRelation.RelationType.COMPETES_WITH,
        allowed_subject_types=_NODE_TYPES,
        allowed_object_types=_NODE_TYPES,
        directed=False,
        symmetric=True,
    ),
    KnowledgeRelation.RelationType.SYNTHESIZES: RelationPolicy(
        predicate=KnowledgeRelation.RelationType.SYNTHESIZES,
        allowed_subject_types=_NODE_TYPES,
        allowed_object_types=_NODE_TYPES,
        directed=True,
        inverse_predicate="synthesized_by",
    ),
    KnowledgeRelation.RelationType.BRANCHES_FROM: RelationPolicy(
        predicate=KnowledgeRelation.RelationType.BRANCHES_FROM,
        allowed_subject_types=_NODE_TYPES,
        allowed_object_types=_NODE_TYPES,
        directed=True,
        inverse_predicate="branches_into",
        hierarchical=True,
    ),
    KnowledgeRelation.RelationType.BORROWS_CONCEPT_FROM: RelationPolicy(
        predicate=KnowledgeRelation.RelationType.BORROWS_CONCEPT_FROM,
        allowed_subject_types=_NODE_TYPES,
        allowed_object_types=_NODE_TYPES,
        directed=True,
        inverse_predicate="lends_concept_to",
    ),
    KnowledgeRelation.RelationType.TRANSFERRED_TO: RelationPolicy(
        predicate=KnowledgeRelation.RelationType.TRANSFERRED_TO,
        allowed_subject_types=_NODE_TYPES,
        allowed_object_types=_NODE_TYPES,
        directed=True,
        inverse_predicate="receives_transfer_from",
    ),
    KnowledgeRelation.RelationType.INFLUENCED_BY: RelationPolicy(
        predicate=KnowledgeRelation.RelationType.INFLUENCED_BY,
        allowed_subject_types=_NODE_TYPES,
        allowed_object_types=_NODE_TYPES,
        directed=True,
        inverse_predicate="influences",
    ),
    KnowledgeRelation.RelationType.OVERLAPS_WITH: RelationPolicy(
        predicate=KnowledgeRelation.RelationType.OVERLAPS_WITH,
        allowed_subject_types=_NODE_TYPES,
        allowed_object_types=_NODE_TYPES,
        directed=False,
        symmetric=True,
    ),
}


def relation_policy(predicate: str) -> RelationPolicy:
    try:
        return RELATION_POLICIES[predicate]
    except KeyError as exc:
        raise ValueError(f"未注册的理论关系类型：{predicate}") from exc


def relation_would_create_cycle(
    *,
    source_node_id,
    target_node_id,
    predicate: str,
    exclude_relation_id=None,
) -> bool:
    """Return whether a hierarchical edge would make its directed graph cyclic."""

    policy = relation_policy(predicate)
    if not policy.hierarchical:
        return False
    if source_node_id == target_node_id:
        return True

    queryset = KnowledgeRelation.objects.filter(
        relation_type=predicate,
    )
    if exclude_relation_id:
        queryset = queryset.exclude(pk=exclude_relation_id)

    frontier = {target_node_id}
    visited = set()
    while frontier:
        if source_node_id in frontier:
            return True
        visited.update(frontier)
        next_nodes = set(
            queryset.filter(source_node_id__in=frontier)
            .exclude(target_node_id__in=visited)
            .values_list("target_node_id", flat=True)
        )
        frontier = next_nodes - visited
    return False


def relation_has_evidence(relation: KnowledgeRelation | None, evidence_source: str) -> bool:
    if evidence_source.strip():
        return True
    if relation is None or not relation.pk:
        return False
    return relation.evidence.exists()


def relation_registry_payload() -> list[dict]:
    return [RELATION_POLICIES[key].serialize() for key in sorted(RELATION_POLICIES)]
