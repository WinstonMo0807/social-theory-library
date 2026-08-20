"""Policy and source registries for the in-context research suggestion layer.

The registry is deliberately a presentation/orchestration contract.  It does
not introduce another candidate table and it never grants a canonical
mutation.  Existing FieldPolicy entries remain the authority for accepting a
persisted EnrichmentCandidate.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from catalog.models import EnrichmentCandidate, EnrichmentSourceClass


WORKFLOW_SUGGESTION_POLICY_VERSION = "workflow-suggestion-policy-v1"
SOURCE_PROFILE_VERSION = "social-science-source-profile-v1"


@dataclass(frozen=True)
class SourceProfile:
    key: str
    label: str
    tier: str
    source_classes: tuple[str, ...] = ()
    is_evidence: bool = True
    description: str = ""


class SourceProfileRegistry:
    def __init__(self):
        self._profiles: dict[str, SourceProfile] = {}

    def register(self, profile: SourceProfile) -> SourceProfile:
        if profile.key in self._profiles:
            raise RuntimeError(f"重复的来源画像：{profile.key}")
        self._profiles[profile.key] = profile
        return profile

    def get(self, key: str) -> SourceProfile:
        return self._profiles[key]

    def all(self) -> tuple[SourceProfile, ...]:
        return tuple(self._profiles.values())

    def for_source_class(self, source_class: str) -> SourceProfile:
        value = str(source_class or "unknown")
        # More specific academic profiles must win over the broad structured
        # profile registered for authority and bibliographic providers.
        ordered = ["syllabus", "academic", "structured", "general_web"]
        for key in ordered:
            profile = self._profiles.get(key)
            if profile is None:
                continue
            if value in profile.source_classes:
                return profile
        return self._profiles["general_web"]


SOURCE_PROFILES = SourceProfileRegistry()
SOURCE_PROFILES.register(
    SourceProfile(
        "library",
        "本馆正式条目",
        "in_library",
        is_evidence=True,
        description="已有 Work、Edition、Person 和关系记录。",
    )
)
SOURCE_PROFILES.register(
    SourceProfile(
        "query_lexicon",
        "QueryLexicon 匹配",
        "query_lexicon",
        is_evidence=False,
        description="规范实体的 canonical、alias、translation 和历史词。",
    )
)
SOURCE_PROFILES.register(
    SourceProfile(
        "pdf",
        "当前 PDF / OCR",
        "pdf_evidence",
        is_evidence=True,
        description="当前馆藏文本、SemanticChunk 和 PDF candidate。",
    )
)
for _key, _label, _tier, _classes in (
    (
        "structured",
        "结构化书目或 authority",
        "structured_source",
        (
            EnrichmentSourceClass.IDENTIFIER_REGISTRY,
            EnrichmentSourceClass.NATIONAL_LIBRARY,
            EnrichmentSourceClass.LIBRARY_CATALOG,
            EnrichmentSourceClass.PUBLISHER,
        ),
    ),
    (
        "academic",
        "学术专业来源",
        "web_evidence",
        (
            EnrichmentSourceClass.ACADEMIC_JOURNAL,
            EnrichmentSourceClass.SCHOLARLY_ENCYCLOPEDIA,
            EnrichmentSourceClass.UNIVERSITY,
            EnrichmentSourceClass.RESEARCH_INSTITUTE,
            EnrichmentSourceClass.PROFESSIONAL_ASSOCIATION,
            EnrichmentSourceClass.SCHOLAR_HOMEPAGE,
        ),
    ),
    (
        "syllabus",
        "大学课程大纲",
        "web_evidence",
        (EnrichmentSourceClass.SYLLABUS,),
    ),
):
    SOURCE_PROFILES.register(
        SourceProfile(
            _key,
            _label,
            _tier,
            source_classes=_classes,
            is_evidence=True,
        )
    )
SOURCE_PROFILES.register(
    SourceProfile(
        "general_web",
        "一般网页研究线索",
        "research_lead",
        source_classes=(EnrichmentSourceClass.GENERAL_WEB, EnrichmentSourceClass.UNKNOWN),
        is_evidence=False,
        description="只能作为线索。搜索摘要不会成为 Evidence。",
    )
)


@dataclass(frozen=True)
class WorkflowSuggestionPolicy:
    step: str
    field: str
    target_type: str | None
    candidate_kind: str
    local_entity_types: tuple[str, ...] = ()
    query_lexicon_entity_types: tuple[str, ...] = ()
    corpus_enabled: bool = False
    structured_enabled: bool = False
    web_enabled: bool = False
    human_confirmation: bool = True
    lexicon_effect: str = "none"
    enrichment_field: str = ""
    source_priority: MappingProxyType = MappingProxyType({})


class WorkflowSuggestionPolicyRegistry:
    def __init__(self):
        self._policies: dict[tuple[str, str], WorkflowSuggestionPolicy] = {}

    def register(self, policy: WorkflowSuggestionPolicy) -> WorkflowSuggestionPolicy:
        key = (policy.step, policy.field)
        if key in self._policies:
            raise RuntimeError(f"重复的 workflow suggestion policy：{policy.step}.{policy.field}")
        self._policies[key] = policy
        return policy

    def get(self, step: str, field: str) -> WorkflowSuggestionPolicy:
        try:
            return self._policies[(str(step).strip(), str(field).strip())]
        except KeyError as exc:
            raise ValueError(f"没有为 {step}.{field} 配置候选策略。") from exc

    def for_step(self, step: str) -> tuple[WorkflowSuggestionPolicy, ...]:
        return tuple(policy for (registered_step, _field), policy in self._policies.items() if registered_step == step)

    def all(self) -> tuple[WorkflowSuggestionPolicy, ...]:
        return tuple(self._policies.values())


WORKFLOW_SUGGESTION_POLICIES = WorkflowSuggestionPolicyRegistry()


def _register(
    step: str,
    field: str,
    target_type: str | None,
    kind: str,
    *,
    local: tuple[str, ...] = (),
    lexicon: tuple[str, ...] = (),
    corpus: bool = False,
    structured: bool = False,
    web: bool = False,
    lexicon_effect: str = "none",
    enrichment_field: str = "",
) -> None:
    WORKFLOW_SUGGESTION_POLICIES.register(
        WorkflowSuggestionPolicy(
            step=step,
            field=field,
            target_type=target_type,
            candidate_kind=kind,
            local_entity_types=local,
            query_lexicon_entity_types=lexicon,
            corpus_enabled=corpus,
            structured_enabled=structured,
            web_enabled=web,
            lexicon_effect=lexicon_effect,
            enrichment_field=enrichment_field,
        )
    )


FACTUAL = EnrichmentCandidate.CandidateKind.FACTUAL
CLASSIFICATION = EnrichmentCandidate.CandidateKind.CLASSIFICATION
INTERPRETIVE = EnrichmentCandidate.CandidateKind.INTERPRETIVE

for _field in ("title", "subtitle", "original_title", "uniform_title", "language", "original_language", "abstract"):
    _register("work", _field, "work", FACTUAL, local=("work",), corpus=True, structured=True, web=True, enrichment_field=_field)
_register("work", "first_publication_date", "work", FACTUAL, local=("work",), corpus=True, structured=True, web=True, enrichment_field="first_publication_date")

for _field in (
    "version_label", "publication_year", "publisher", "publication_place", "isbn10", "isbn13",
    "series", "extent", "responsibility_statement", "journal_title", "volume", "issue", "page_range", "doi",
    "degree_institution", "degree_type", "report_institution",
):
    _register("bibliography", _field, "edition", FACTUAL, local=("edition",), corpus=True, structured=True, web=True, enrichment_field=_field)

_register("contributors", "contributors", "person", FACTUAL, local=("person",), lexicon=("person",), corpus=True, web=True)
for _field in ("primary_disciplines", "related_disciplines"):
    _register("classification", _field, "work", CLASSIFICATION, local=("discipline",), lexicon=("discipline",), corpus=True, web=True, lexicon_effect="search_expansion", enrichment_field="discipline")
_register("classification", "subdisciplines", "work", CLASSIFICATION, local=("subdiscipline",), lexicon=("subdiscipline", "knowledge_node"), corpus=True, web=True, lexicon_effect="search_expansion", enrichment_field="subdiscipline")
_register("knowledge", "relations", "work", INTERPRETIVE, local=("knowledge_node", "topic", "theory_school"), lexicon=("knowledge_node", "topic", "theory_school"), corpus=True, web=True)
_register("reader", "reader_rendition_policy", None, FACTUAL, local=("asset",), corpus=False, web=False)
_register("curation", "reading_path_placements", "reading_path", INTERPRETIVE, local=("reading_path",), corpus=True, web=True)
_register("curation", "recommendation_reason", "work", INTERPRETIVE, corpus=True, web=True)
_register("publication", "preflight", None, FACTUAL, local=("publication",), corpus=False, web=False)


def source_profile_payload() -> list[dict]:
    return [
        {
            "key": profile.key,
            "label": profile.label,
            "tier": profile.tier,
            "source_classes": list(profile.source_classes),
            "is_evidence": profile.is_evidence,
            "description": profile.description,
        }
        for profile in SOURCE_PROFILES.all()
    ]


def policy_payload(step: str | None = None) -> list[dict]:
    policies = WORKFLOW_SUGGESTION_POLICIES.for_step(step) if step else WORKFLOW_SUGGESTION_POLICIES.all()
    return [
        {
            "step": policy.step,
            "field": policy.field,
            "target_type": policy.target_type,
            "candidate_kind": policy.candidate_kind,
            "local_entity_types": list(policy.local_entity_types),
            "query_lexicon_entity_types": list(policy.query_lexicon_entity_types),
            "corpus_enabled": policy.corpus_enabled,
            "structured_enabled": policy.structured_enabled,
            "web_enabled": policy.web_enabled,
            "human_confirmation": policy.human_confirmation,
            "lexicon_effect": policy.lexicon_effect,
            "enrichment_field": policy.enrichment_field,
        }
        for policy in policies
    ]
