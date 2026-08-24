from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from django.db import OperationalError, ProgrammingError, transaction

from catalog.models import ResearchTaskProfile


RESEARCH_TASK_PROFILE_REGISTRY_VERSION = "research-task-profiles-v1"


@dataclass(frozen=True, slots=True)
class TaskProfileSpec:
    key: str
    name: str
    required_context: tuple[str, ...]
    retrieval_profile: str
    preferred_evidence_sources: tuple[str, ...]
    minimum_evidence_policy: dict[str, Any]
    prompt_key: str
    output_schema: dict[str, Any]
    ranking_policy: dict[str, Any]
    human_review_policy: dict[str, Any]
    required_capability: str
    version: int = 1

    def payload(self) -> dict[str, Any]:
        value = asdict(self)
        value["required_context"] = list(self.required_context)
        value["preferred_evidence_sources"] = list(self.preferred_evidence_sources)
        return value


def _profile(
    key: str,
    name: str,
    *,
    context: tuple[str, ...],
    retrieval: str,
    sources: tuple[str, ...],
    minimum: dict[str, Any],
    capability: str,
    schema: dict[str, Any],
    ranking: dict[str, Any] | None = None,
    review: dict[str, Any] | None = None,
) -> TaskProfileSpec:
    return TaskProfileSpec(
        key=key,
        name=name,
        required_context=context,
        retrieval_profile=retrieval,
        preferred_evidence_sources=sources,
        minimum_evidence_policy=minimum,
        prompt_key=f"research.{key}",
        output_schema=schema,
        ranking_policy=ranking or {"order": ["evidence_quality", "corroboration", "confidence"]},
        human_review_policy=review or {"canonical_write": "human_only", "publication_blocking": False},
        required_capability=capability,
    )


LOCAL_AND_AUTHORITY = ("collection", "authority", "library_catalog", "safe_web_page")
COLLECTION_FIRST = ("collection", "authority", "safe_web_page")


BUILTIN_TASK_PROFILES: dict[str, TaskProfileSpec] = {
    spec.key: spec
    for spec in (
        _profile(
            "person_identity",
            "责任者身份",
            context=("person.name", "work.title", "edition.identifiers"),
            retrieval="entity_discovery",
            sources=LOCAL_AND_AUTHORITY,
            minimum={"evidence_count": 1, "authority_or_library": 1, "snippet_is_lead_only": True},
            capability="entity_reasoning",
            schema={"type": "object", "required": ["candidates", "evidence"]},
        ),
        _profile(
            "bibliographic_identity",
            "书目身份",
            context=("work.title", "edition.identifiers", "contributors"),
            retrieval="research_evidence",
            sources=LOCAL_AND_AUTHORITY,
            minimum={"evidence_count": 1, "identifier_preferred": True, "snippet_is_lead_only": True},
            capability="entity_reasoning",
            schema={"type": "object", "required": ["identity", "evidence"]},
        ),
        _profile(
            "theory_classification",
            "理论分类",
            context=("work", "contributors", "collection_evidence", "knowledge"),
            retrieval="curation",
            sources=COLLECTION_FIRST,
            minimum={"collection_evidence_count": 1, "independent_source_count": 1},
            capability="theory_reasoning",
            schema={"type": "object", "required": ["node_candidates", "reasons", "evidence"]},
        ),
        _profile(
            "theory_development_position",
            "理论发展位置",
            context=("work", "theory_node", "collection_evidence"),
            retrieval="curation",
            sources=COLLECTION_FIRST,
            minimum={"collection_evidence_count": 1},
            capability="knowledge_relation_reasoning",
            schema={"type": "object", "required": ["relation", "reason", "evidence"]},
        ),
        _profile(
            "concept_importance",
            "概念重要性",
            context=("work", "concept_candidates", "collection_evidence"),
            retrieval="curation",
            sources=COLLECTION_FIRST,
            minimum={"collection_evidence_count": 1},
            capability="theory_reasoning",
            schema={"type": "object", "required": ["concepts", "importance", "evidence"]},
        ),
        _profile(
            "claim_extraction",
            "命题抽取",
            context=("document_revision", "evidence_spans"),
            retrieval="research_evidence",
            sources=("collection",),
            minimum={"collection_evidence_count": 1, "locator_required": True},
            capability="claim_extraction",
            schema={"type": "array", "items": {"type": "object", "required": ["proposition", "claim_type"]}},
        ),
        _profile(
            "claim_attribution",
            "命题归因",
            context=("claim", "evidence_span", "surrounding_text"),
            retrieval="research_evidence",
            sources=("collection",),
            minimum={"collection_evidence_count": 1, "locator_required": True},
            capability="claim_attribution",
            schema={"type": "object", "required": ["attribution", "confidence", "evidence"]},
        ),
        _profile(
            "claim_stance",
            "命题立场",
            context=("query_claim", "candidate_claim", "evidence_span"),
            retrieval="viewpoint",
            sources=("collection",),
            minimum={"collection_evidence_count": 1, "explicit_polarity_check": True},
            capability="claim_stance",
            schema={"type": "object", "required": ["relation", "confidence", "rationale"]},
        ),
        _profile(
            "core_viewpoint",
            "核心观点候选",
            context=("work", "claim_clusters", "collection_evidence"),
            retrieval="curation",
            sources=("collection",),
            minimum={"collection_evidence_count": 1, "locator_required": True},
            capability="curation_reasoning",
            schema={"type": "array", "maxItems": 5, "items": {"type": "object"}},
            ranking={"order": ["importance", "quality", "cross_section_support"], "max_active_decisions": 5},
        ),
        _profile(
            "major_criticism",
            "主要批评候选",
            context=("work", "criticism_claims", "collection_evidence"),
            retrieval="curation",
            sources=COLLECTION_FIRST,
            minimum={"collection_evidence_count": 1},
            capability="curation_reasoning",
            schema={"type": "array", "maxItems": 5, "items": {"type": "object"}},
            ranking={"order": ["directness", "quality", "cross_source_corroboration"], "max_active_decisions": 5},
        ),
        _profile(
            "major_response",
            "主要回应候选",
            context=("work", "response_claims", "collection_evidence"),
            retrieval="curation",
            sources=COLLECTION_FIRST,
            minimum={"collection_evidence_count": 1},
            capability="curation_reasoning",
            schema={"type": "array", "maxItems": 5, "items": {"type": "object"}},
            ranking={"order": ["directness", "quality", "cross_source_corroboration"], "max_active_decisions": 5},
        ),
        _profile(
            "debate_discovery",
            "争论发现",
            context=("claim_clusters", "knowledge", "works"),
            retrieval="curation",
            sources=COLLECTION_FIRST,
            minimum={"support_count": 1, "oppose_or_qualify_count": 1, "work_count": 2},
            capability="debate_discovery",
            schema={"type": "object", "required": ["canonical_question", "positions", "evidence"]},
        ),
        _profile(
            "reading_path_generation",
            "阅读路径生成",
            context=("learning_goal", "target_audience", "knowledge", "works"),
            retrieval="curation",
            sources=COLLECTION_FIRST,
            minimum={"work_count": 2, "published_or_draft_holdings_only": True},
            capability="reading_path_generation",
            schema={"type": "object", "required": ["target_audience", "learning_goal", "stages"]},
        ),
        _profile(
            "reading_path_placement",
            "阅读路径定位",
            context=("reading_path", "work", "knowledge", "prerequisites"),
            retrieval="curation",
            sources=COLLECTION_FIRST,
            minimum={"collection_evidence_count": 1},
            capability="curation_reasoning",
            schema={"type": "object", "required": ["stage", "order", "reason", "prerequisite"]},
        ),
    )
}


def builtin_task_profile(key: str) -> TaskProfileSpec:
    try:
        return BUILTIN_TASK_PROFILES[str(key or "").strip()]
    except KeyError as exc:
        raise ValueError(f"未知 ResearchTaskProfile：{key}") from exc


def resolve_task_profile(key: str) -> dict[str, Any]:
    """Return the active DB revision, with a deterministic code fallback."""

    fallback = builtin_task_profile(key).payload()
    try:
        stored = ResearchTaskProfile.objects.filter(key=key, is_active=True).order_by("-version").first()
    except (OperationalError, ProgrammingError):
        stored = None
    if stored is None:
        return {**fallback, "source": "builtin", "registry_version": RESEARCH_TASK_PROFILE_REGISTRY_VERSION}
    return {
        "key": stored.key,
        "version": stored.version,
        "name": stored.name,
        "required_context": stored.required_context,
        "retrieval_profile": stored.retrieval_profile,
        "preferred_evidence_sources": stored.preferred_evidence_sources,
        "minimum_evidence_policy": stored.minimum_evidence_policy,
        "prompt_key": stored.prompt_key,
        "output_schema": stored.output_schema,
        "ranking_policy": stored.ranking_policy,
        "human_review_policy": stored.human_review_policy,
        "required_capability": stored.required_capability,
        "source": "database",
        "registry_version": RESEARCH_TASK_PROFILE_REGISTRY_VERSION,
    }


def profile_key_for_contract(*, step: str, field: str, implementation: str) -> str:
    normalized_step = str(step or "").casefold()
    normalized_field = str(field or "").casefold()
    if normalized_step == "contributors":
        return "person_identity"
    if normalized_step in {"work", "bibliography", "files"}:
        return "bibliographic_identity"
    if normalized_step == "knowledge" and any(token in normalized_field for token in ("relation", "position")):
        return "theory_development_position"
    if normalized_step == "knowledge" and any(token in normalized_field for token in ("concept", "topic")):
        return "concept_importance"
    if normalized_step == "knowledge" or implementation in {"editorial_discovery", "evidence_only"}:
        return "theory_classification"
    return "bibliographic_identity"


@transaction.atomic
def seed_builtin_task_profiles(*, actor=None) -> dict[str, int]:
    created = 0
    unchanged = 0
    for spec in BUILTIN_TASK_PROFILES.values():
        payload = spec.payload()
        ResearchTaskProfile.objects.filter(key=spec.key, is_active=True).exclude(version=spec.version).update(
            is_active=False
        )
        _, was_created = ResearchTaskProfile.objects.update_or_create(
            key=spec.key,
            version=spec.version,
            defaults={
                "name": spec.name,
                "required_context": payload["required_context"],
                "retrieval_profile": spec.retrieval_profile,
                "preferred_evidence_sources": payload["preferred_evidence_sources"],
                "minimum_evidence_policy": spec.minimum_evidence_policy,
                "prompt_key": spec.prompt_key,
                "output_schema": spec.output_schema,
                "ranking_policy": spec.ranking_policy,
                "human_review_policy": spec.human_review_policy,
                "required_capability": spec.required_capability,
                "is_active": True,
                "created_by": actor,
            },
        )
        created += int(was_created)
        unchanged += int(not was_created)
    return {"created": created, "updated_or_unchanged": unchanged, "total": len(BUILTIN_TASK_PROFILES)}
